"""Library code for the Kalshi skill.

Holds the RSA-PSS request signer, the thin REST client, and the JSON-shaping
helpers used by `handlers.py`. Non-2xx responses raise `KalshiAPIError` so
callers can decide how to surface failures (e.g. 401 → CredentialRejected).
"""

from __future__ import annotations

import base64
import logging
import time

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

logger = logging.getLogger(__name__)

BASE_URL = "https://api.elections.kalshi.com"
API_PREFIX = "/trade-api/v2"
_TIMEOUT = (10, 15)  # (connect, read) seconds — spec §6.1


class KalshiAPIError(Exception):
    """Raised on non-2xx responses or network failures.

    `status` is the HTTP status code, or 0 when the request never made it
    (DNS failure, connection refused, etc.). `body` is up to 200 bytes of
    the response or the network error string.
    """

    def __init__(self, status: int, body: str):
        super().__init__(f"kalshi API {status}")
        self.status = status
        self.body = body


class Signer:
    """RSA-PSS SHA-256 signer over (timestamp_ms + METHOD + path).

    Path MUST exclude the query string. Salt length equals the digest length
    (32 bytes for SHA-256).
    """

    def __init__(self, pem_bytes: bytes):
        self._key = serialization.load_pem_private_key(pem_bytes, password=None)

    def sign(self, timestamp_ms: int, method: str, path: str) -> str:
        payload = f"{timestamp_ms}{method}{path}".encode()
        sig = self._key.sign(
            payload,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=hashes.SHA256.digest_size,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(sig).decode("ascii")


def signed_path(path: str) -> str:
    """Return path with any query string removed, for use as the signing input."""
    return path.split("?", 1)[0]


class KalshiClient:
    """Thin signed wrapper around the Kalshi prod REST API.

    All endpoints are GET. Path is given without the /trade-api/v2 prefix
    and without a query string; the client builds the full URL and signs
    the path-without-query. All non-2xx responses raise `KalshiAPIError`.
    """

    def __init__(self, key_id: str, signer: Signer, session=None):
        self._key_id = key_id
        self._signer = signer
        self._session = session or requests.Session()

    def get(self, path: str, params: dict | None = None) -> dict:
        full_path = API_PREFIX + path
        ts_ms = int(time.time() * 1000)
        sig = self._signer.sign(ts_ms, "GET", signed_path(full_path))
        headers = {
            "KALSHI-ACCESS-KEY": self._key_id,
            "KALSHI-ACCESS-TIMESTAMP": str(ts_ms),
            "KALSHI-ACCESS-SIGNATURE": sig,
            "Accept": "application/json",
        }
        url = BASE_URL + full_path
        try:
            resp = self._session.request("GET", url, headers=headers, params=params or {}, timeout=_TIMEOUT)
        except requests.exceptions.RequestException as e:
            raise KalshiAPIError(0, str(e)) from e

        if 200 <= resp.status_code < 300:
            return resp.json()

        body_trim = (resp.text or "")[:200]
        # Defensive redaction — a misbehaving server or proxy could echo our
        # key_id back in an error body. Strip it before letting the body propagate.
        body_trim = body_trim.replace(self._key_id, "<redacted>")
        raise KalshiAPIError(resp.status_code, body_trim)


# ── JSON / output shaping helpers ─────────────────────────────────────


def _parse_dollars(s) -> float:
    """Parse a Kalshi dollar-string like "0.0100" or "3.500000" into a float.

    Live API returns dollar-typed fields as strings. Returns 0.0 for None
    or empty strings (some fields are nullable in settled markets).
    """
    if not s:
        return 0.0
    return float(s)


def _parse_fp(s) -> int:
    """Parse a Kalshi fixed-point string like "5.00" or "0.00" into an int count."""
    if not s:
        return 0
    return int(float(s))


def _derive_event_ticker(market_ticker: str) -> str:
    """Strip the trailing -SUFFIX from a market ticker to derive its event."""
    if "-" not in market_ticker:
        return market_ticker
    return market_ticker.rsplit("-", 1)[0]


def _position_side(position: int) -> str:
    """Derive the human-facing side label from the signed position count."""
    if position > 0:
        return "YES"
    if position < 0:
        return "NO"
    return ""


def fetch_or_404(client: KalshiClient, path: str, params: dict | None = None) -> dict | None:
    """GET `path`; return parsed dict, or None on 404. Other API errors propagate."""
    try:
        return client.get(path, params=params)
    except KalshiAPIError as e:
        if e.status == 404:
            return None
        raise


_MAX_CURSOR_PAGES = 200


def fetch_all_series(client: KalshiClient) -> list[dict]:
    """Walk /series via the cursor field until exhausted.

    Stops on empty cursor, on repeated cursor (defensive guard against a buggy
    server), or after `_MAX_CURSOR_PAGES` pages (defensive guard against a
    strictly-monotone-but-never-empty cursor sequence).
    """
    out: list[dict] = []
    cursor = ""
    for _ in range(_MAX_CURSOR_PAGES):
        params = {"cursor": cursor} if cursor else {}
        page = client.get("/series", params=params)
        out.extend(page.get("series") or [])
        next_cursor = page.get("cursor") or ""
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
    else:
        logger.warning("fetch_all_series hit page cap (%d); truncating", _MAX_CURSOR_PAGES)
    return out


def match_series(series: list[dict], query: str) -> list[dict]:
    """AND-match every whitespace token (case-insensitive substring) against
    title + ticker + tags + category. Empty query -> []."""
    tokens = query.lower().split()
    if not tokens:
        return []
    out = []
    for s in series:
        haystack_parts = [
            s.get("title") or "",
            s.get("ticker") or "",
            s.get("category") or "",
            *(s.get("tags") or []),
        ]
        haystack = " ".join(haystack_parts).lower()
        if all(t in haystack for t in tokens):
            out.append(s)
    return out


def enrich_positions(client: KalshiClient, market_positions: list[dict]) -> list[dict]:
    """Attach event_title + yes_outcome to each position so it renders
    with both the technical ticker and a human-readable description.

    Each unique parent event is fetched once with nested markets, which
    yields both the event's human title and every market's yes_sub_title
    (Kalshi's API name for the YES-side outcome label, surfaced as
    `yes_outcome` in our output) in a single call. If a derived event lookup
    fails (404 or any other API error), the affected positions render with
    empty enrichment rather than aborting the entire account snapshot — partial
    enrichment is far more useful to the user than no answer at all.
    """
    event_cache: dict[str, tuple[str, dict[str, str]]] = {}
    out: list[dict] = []
    for p in market_positions:
        ticker = p["ticker"]
        event_ticker = _derive_event_ticker(ticker)

        if event_ticker not in event_cache:
            event_cache[event_ticker] = ("", {})
            try:
                evt_resp = fetch_or_404(client, f"/events/{event_ticker}", params={"with_nested_markets": "true"})
            except KalshiAPIError as exc:
                logger.warning("enrich_positions: /events/%s lookup failed (%s); rendering without enrichment", event_ticker, exc)
                evt_resp = None
            if evt_resp is not None:
                e = evt_resp.get("event") or {}
                title = e.get("title", "")
                sub_titles = {
                    m["ticker"]: m.get("yes_sub_title", "")
                    for m in (e.get("markets") or [])
                    if "ticker" in m
                }
                event_cache[event_ticker] = (title, sub_titles)

        event_title, sub_titles = event_cache[event_ticker]
        position = _parse_fp(p.get("position_fp"))
        out.append({
            "ticker": ticker,
            "event_title": event_title,
            "yes_outcome": sub_titles.get(ticker, ""),
            "side": _position_side(position),
            "position": position,
            "exposure_cents": round(_parse_dollars(p.get("market_exposure_dollars")) * 100),
        })
    return out


def market_to_json(resp: dict) -> dict:
    """Shape one market response into the canonical market JSON view."""
    m = resp.get("market") or resp
    return {
        "kind": "market",
        "ticker": m["ticker"],
        "yes_sub_title": m.get("yes_sub_title", ""),
        "yes_bid": _parse_dollars(m.get("yes_bid_dollars")),
        "yes_ask": _parse_dollars(m.get("yes_ask_dollars")),
        "last_price": _parse_dollars(m.get("last_price_dollars")),
        "no_bid": _parse_dollars(m.get("no_bid_dollars")),
        "no_ask": _parse_dollars(m.get("no_ask_dollars")),
        "volume_24h": _parse_fp(m.get("volume_24h_fp")),
        "volume": _parse_fp(m.get("volume_fp")),
        "close_time": m.get("close_time", ""),
    }


def event_to_json(resp: dict) -> dict:
    """Shape an event-with-nested-markets response into the canonical event JSON view."""
    evt = resp.get("event") or {}
    markets = evt.get("markets") or []
    close_time = evt.get("close_time", "") or (markets[0].get("close_time", "") if markets else "")
    return {
        "kind": "event",
        "event_ticker": evt.get("event_ticker", ""),
        "title": evt.get("title", ""),
        "close_time": close_time,
        "markets": [
            {
                "ticker": m["ticker"],
                "yes_sub_title": m.get("yes_sub_title", ""),
                "yes_bid": _parse_dollars(m.get("yes_bid_dollars")),
                "yes_ask": _parse_dollars(m.get("yes_ask_dollars")),
                "last_price": _parse_dollars(m.get("last_price_dollars")),
                "volume_24h": _parse_fp(m.get("volume_24h_fp")),
                "volume": _parse_fp(m.get("volume_fp")),
            }
            for m in markets
        ],
    }
