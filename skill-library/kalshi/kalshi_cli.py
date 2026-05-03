#!/usr/bin/env python3
"""Kalshi read-only CLI.

A standalone Python CLI bundled inside a Claude Code skill that gives an
agent read-only access to a Kalshi account: balance/positions, keyword
market search, and event/market price views. See SKILL.md for usage.
"""

# This file is intentionally minimal at chunk 1; subsequent chunks add the
# signer, credentials, HTTP client, and subcommands.

import base64
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


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


def _parse_dollars(s) -> float:
    """Parse a Kalshi dollar-string like "0.0100" or "3.500000" into a float.

    Live API returns dollar-typed fields as strings. Returns 0.0 for None
    or empty strings (some fields are nullable in settled markets)."""
    if not s:
        return 0.0
    return float(s)


def _parse_fp(s) -> int:
    """Parse a Kalshi fixed-point string like "5.00" or "0.00" into an int count."""
    if not s:
        return 0
    return int(float(s))


import os
from pathlib import Path

BASE_URL = "https://api.elections.kalshi.com"
API_PREFIX = "/trade-api/v2"

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "kalshi"
CONFIG_PATH = CONFIG_DIR / "config.toml"
DEFAULT_KEY_PATH = CONFIG_DIR / "private_key.pem"


import sys
from dataclasses import dataclass
from typing import NoReturn

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover — exercised on 3.10 only
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass
class Credentials:
    key_id: str
    private_key_path: Path


def _expand(path_str: str) -> Path:
    return Path(path_str).expanduser()


def _read_config_file() -> dict:
    """Read CONFIG_PATH if it exists, else return {}. Raises on parse error."""
    if not CONFIG_PATH.exists():
        return {}
    _check_mode(CONFIG_PATH, "config file")
    with CONFIG_PATH.open("rb") as f:
        return tomllib.load(f)


def _check_mode(path: Path, what: str) -> None:
    mode = path.stat().st_mode & 0o777
    if mode & 0o077:
        die(
            f"error: {what} at {path} has unsafe permissions "
            f"(mode {mode:04o}); run: chmod 600 {path}",
            exit_code=2,
        )


def die(msg: str, exit_code: int = 1) -> NoReturn:
    """Print a one-line error to stderr and exit with the given code."""
    print(msg, file=sys.stderr)
    sys.exit(exit_code)


def load_credentials() -> Credentials:
    """Resolve credentials per spec §4.1: env-first, file-fallback, per-field."""
    cfg = _read_config_file()

    key_id = os.environ.get("KALSHI_API_KEY_ID") or cfg.get("key_id")
    if not key_id:
        die(
            "error: no Kalshi credentials found. "
            "Run: python3 kalshi_cli.py setup",
            exit_code=2,
        )

    key_path_str = (
        os.environ.get("KALSHI_PRIVATE_KEY_PATH")
        or cfg.get("private_key_path")
        or str(DEFAULT_KEY_PATH)
    )
    key_path = _expand(key_path_str)
    if not key_path.exists():
        die(
            "error: no Kalshi credentials found. "
            "Run: python3 kalshi_cli.py setup",
            exit_code=2,
        )
    _check_mode(key_path, "private key")

    return Credentials(key_id=key_id, private_key_path=key_path)


import time

import requests


_TIMEOUT = (10, 15)  # (connect, read) seconds — spec §6.1


class KalshiAPIError(Exception):
    """Raised on non-2xx responses; carries the status code and body."""

    def __init__(self, status: int, body: str):
        super().__init__(f"kalshi API {status}")
        self.status = status
        self.body = body


class KalshiClient:
    """Thin signed wrapper around the Kalshi prod REST API.

    All endpoints are GET. Path is given without the /trade-api/v2 prefix
    and without a query string; the client builds the full URL and signs
    the path-without-query.
    """

    def __init__(self, key_id: str, signer: "Signer", session=None):
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
            resp = self._session.request(
                "GET", url, headers=headers, params=params or {}, timeout=_TIMEOUT,
            )
        except requests.exceptions.RequestException as e:
            die(f"error: network — {e}", exit_code=4)

        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 401:
            die(
                "error: kalshi API 401 — credentials rejected "
                "(key/PEM mismatch or clock drift)",
                exit_code=3,
            )
        if resp.status_code == 404:
            raise KalshiAPIError(404, resp.text or "")
        body_trim = (resp.text or "")[:200]
        # Defense in depth: a misbehaving server (or proxy) could echo our
        # key_id back in a 5xx body. Redact it before it lands in stderr.
        body_trim = body_trim.replace(self._key_id, "<redacted>")
        die(f"error: kalshi API {resp.status_code} — {body_trim}", exit_code=3)


import argparse
import json


def _emit_json(obj) -> None:
    print(json.dumps(obj, separators=(",", ":")))


def cmd_account(argv: list[str], client: "KalshiClient") -> int:
    parser = argparse.ArgumentParser(prog="kalshi_cli.py account")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    bal = client.get("/portfolio/balance")

    # Walk the positions cursor to completion. Mirrors the parent repo's
    # pattern (internal/kalshi/client.go Positions()): Kalshi returns at
    # most `limit` rows per page, so single-page reads silently truncate
    # large portfolios.
    all_market_positions: list[dict] = []
    cursor = ""
    while True:
        params: dict = {"limit": 200}
        if cursor:
            params["cursor"] = cursor
        page = client.get("/portfolio/positions", params=params)
        all_market_positions.extend(page.get("market_positions") or [])
        next_cursor = page.get("cursor") or ""
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor

    cash = int(bal["balance"])
    positions_value = int(bal["portfolio_value"])
    total = cash + positions_value

    positions_out = _enrich_positions(client, all_market_positions)

    if args.json:
        _emit_json({
            "cash_cents": cash,
            "positions_cents": positions_value,
            "total_cents": total,
            "positions": positions_out,
        })
    else:
        _print_account_text(cash, positions_value, total, positions_out)
    return 0


def _derive_event_ticker(market_ticker: str) -> str:
    """Strip the trailing -SUFFIX from a market ticker to derive its event.

    Kalshi's market-ticker convention is <EVENT_TICKER>-<MARKET_SUFFIX>,
    so KXCODINGMODEL-26DEC-ANTH → KXCODINGMODEL-26DEC. Returns the input
    unchanged if there is no dash."""
    if "-" not in market_ticker:
        return market_ticker
    return market_ticker.rsplit("-", 1)[0]


def _enrich_positions(client: "KalshiClient", market_positions: list[dict]) -> list[dict]:
    """Attach event_title + yes_outcome to each position so it renders
    with both the technical ticker and a human-readable description.

    Each unique parent event is fetched once with nested markets, which
    yields both the event's human title and every market's yes_sub_title
    (Kalshi's API name for the YES-side outcome label, surfaced as
    `yes_outcome` in our output) in a single call — so M event fetches
    cover any number of positions. If the derived event 404s, the
    position renders with empty enrichment rather than failing."""
    # event_ticker -> (event_title, {market_ticker: yes_outcome})
    event_cache: dict[str, tuple[str, dict[str, str]]] = {}
    out: list[dict] = []
    for p in market_positions:
        ticker = p["ticker"]
        event_ticker = _derive_event_ticker(ticker)

        if event_ticker not in event_cache:
            event_cache[event_ticker] = ("", {})
            evt_resp = _fetch_event_or_404(client, event_ticker)
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


def _position_side(position: int) -> str:
    """Derive the human-facing side label from the signed position count.

    Kalshi's `position_fp` is signed: positive = net long YES, negative =
    net long NO (i.e. short YES). For multi-choice events this matters —
    `NO Anthropic` is a bet on any other candidate, not the same trade as
    `YES Anthropic`. A flat (0) position returns "" so it doesn't add
    visual noise; in practice flat rows shouldn't appear in /portfolio/
    positions but we handle it defensively."""
    if position > 0:
        return "YES"
    if position < 0:
        return "NO"
    return ""


def fetch_all_series(client: "KalshiClient") -> list[dict]:
    """Walk /series via the cursor field until exhausted. No partial results."""
    out: list[dict] = []
    cursor = ""
    while True:
        params = {"cursor": cursor} if cursor else {}
        page = client.get("/series", params=params)
        out.extend(page.get("series") or [])
        cursor = page.get("cursor") or ""
        if not cursor:
            break
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
            s.get("title", ""),
            s.get("ticker", ""),
            s.get("category", ""),
            *s.get("tags", []),
        ]
        haystack = " ".join(haystack_parts).lower()
        if all(t in haystack for t in tokens):
            out.append(s)
    return out


def cmd_search(argv: list[str], client: "KalshiClient") -> int:
    parser = argparse.ArgumentParser(prog="kalshi_cli.py search")
    parser.add_argument("query", nargs="+", help="one or more keywords")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--all-events", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.limit < 0:
        parser.error("--limit must be >= 0")
    query = " ".join(args.query)

    all_series = fetch_all_series(client)
    matched = match_series(all_series, query)
    if args.limit > 0:
        matched = matched[: args.limit]

    enriched = []
    for s in matched:
        params = {"series_ticker": s["ticker"]}
        if not args.all_events:
            params["status"] = "open"
        # Let KalshiAPIError propagate. /events should never 404 for a
        # series we just got from /series; if it does, that's a real
        # inconsistency worth surfacing (consistent with §6.1 "no retries,
        # no silent error masking" stance and the no-partial-results rule
        # for the /series walk above).
        evt_resp = client.get("/events", params=params)
        events = [
            {
                "ticker": e["event_ticker"],
                "title": e.get("title", ""),
                "close_time": e.get("close_time", ""),
            }
            for e in (evt_resp.get("events") or [])
        ]
        enriched.append({
            "ticker": s["ticker"],
            "title": s.get("title", ""),
            "category": s.get("category", ""),
            "frequency": s.get("frequency", ""),
            "events": events,
        })

    if args.json:
        _emit_json({"query": query, "series": enriched})
    else:
        _print_search_text(query, enriched)
    return 0


def _print_search_text(query: str, series: list[dict]) -> None:
    """Render search results as text: one block per series with its open events."""
    if not series:
        print(f"(no series matched '{query}')")
        return
    for s in series:
        meta = f"{s['frequency']}, {s['category']}".strip(", ")
        print(f"{s['ticker']:<8} {s['title']} ({meta})")
        for e in s["events"]:
            print(f"  {e['ticker']:<22} {e['title']:<60} closes {e['close_time']}")
        print()


def _print_account_text(cash: int, positions_value: int, total: int, positions: list[dict]) -> None:
    """Render account summary as aligned human-readable text. Each position
    shows the technical ticker followed by an indented human-readable line
    combining the event title and market sub-title (when available)."""
    print(f"cash:        ${cash/100:.2f}")
    print(f"positions:   ${positions_value/100:.2f}")
    print(f"total:       ${total/100:.2f}")
    print()
    print(f"positions ({len(positions)}):")
    if not positions:
        print("  (none)")
        return
    for p in positions:
        print(
            f"  {p['ticker']}  pos={p['position']}  "
            f"exposure=${p['exposure_cents']/100:.2f}"
        )
        description = _format_position_description(
            p.get("event_title", ""), p.get("side", ""), p.get("yes_outcome", "")
        )
        if description:
            print(f"    {description}")


def _format_position_description(event_title: str, side: str, yes_outcome: str) -> str:
    """Combine event title, position side, and YES outcome into one line.

    The YES outcome is prefixed with the side ("YES"/"NO") so multi-choice
    holdings disambiguate: `Best coding model by Dec 26th? — NO Anthropic`
    means "betting Anthropic does NOT win", not the same as YES Anthropic.
    Empty side drops the prefix; empty outcome drops the right of the em-
    dash; both empty falls back to just the event title."""
    if yes_outcome:
        labeled = f"{side} {yes_outcome}".strip() if side else yes_outcome
        if event_title:
            return f"{event_title} — {labeled}"
        return labeled
    return event_title


def cmd_prices(argv: list[str], client: "KalshiClient") -> int:
    parser = argparse.ArgumentParser(prog="kalshi_cli.py prices")
    parser.add_argument("ticker")
    parser.add_argument("--kind", choices=["event", "market"], default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    ticker = args.ticker.strip()
    if not ticker:
        die("error: empty ticker", exit_code=5)

    market_obj = None
    event_obj = None

    if args.kind == "market":
        market_obj = _fetch_market_or_404(client, ticker)
        if market_obj is None:
            die(f"error: no event or market matching ticker {ticker}", exit_code=5)
    elif args.kind == "event":
        event_obj = _fetch_event_or_404(client, ticker)
        if event_obj is None:
            die(f"error: no event or market matching ticker {ticker}", exit_code=5)
    else:
        market_obj = _fetch_market_or_404(client, ticker)
        if market_obj is None:
            event_obj = _fetch_event_or_404(client, ticker)
            if event_obj is None:
                die(
                    f"error: no event or market matching ticker {ticker}",
                    exit_code=5,
                )

    if market_obj is not None:
        if args.json:
            _emit_json(_market_to_json(market_obj))
        else:
            _print_market_text(market_obj)
    else:
        if args.json:
            _emit_json(_event_to_json(event_obj))
        else:
            _print_event_text(event_obj)
    return 0


def _fetch_market_or_404(client, ticker):
    """GET /markets/<ticker>; return parsed dict, or None on 404."""
    try:
        return client.get(f"/markets/{ticker}")
    except KalshiAPIError as e:
        if e.status == 404:
            return None
        raise


def _fetch_event_or_404(client, ticker):
    """GET /events/<ticker>?with_nested_markets=true; return parsed dict, or None on 404."""
    try:
        return client.get(f"/events/{ticker}", params={"with_nested_markets": "true"})
    except KalshiAPIError as e:
        if e.status == 404:
            return None
        raise


def _market_to_json(resp: dict) -> dict:
    """Shape one market response into the CLI's JSON market view."""
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


def _print_market_text(resp: dict) -> None:
    """Render single-market view as human-readable text."""
    j = _market_to_json(resp)
    print(j["ticker"])
    print(f"  strike:       {j['yes_sub_title']}")
    print(f"  yes:          bid {j['yes_bid']:.2f} / ask {j['yes_ask']:.2f}   last {j['last_price']:.2f}")
    print(f"  no:           bid {j['no_bid']:.2f} / ask {j['no_ask']:.2f}")
    print(f"  volume:       24h {j['volume_24h']:,}   total {j['volume']:,}")
    print(f"  closes:       {j['close_time']}")


def _event_to_json(resp: dict) -> dict:
    """Shape an event-with-nested-markets response into the CLI's JSON event view."""
    evt = resp.get("event") or {}
    markets = (resp.get("event") or {}).get("markets") or []
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


def _print_event_text(resp: dict) -> None:
    """Render the full event ladder as a human-readable table."""
    j = _event_to_json(resp)
    print(f"{j['event_ticker']}   {j['title']}   closes {j['close_time']}")
    print()
    print(f"  {'TICKER':<32} {'STRIKE':<22} {'YES_BID':<8} {'YES_ASK':<8} {'LAST':<7} {'VOL_24H'}")
    for m in j["markets"]:
        print(
            f"  {m['ticker']:<32} {m['yes_sub_title']:<22} "
            f"{m['yes_bid']:<8.2f} {m['yes_ask']:<8.2f} {m['last_price']:<7.2f} "
            f"{m['volume_24h']:,}"
        )


import re
from cryptography.hazmat.primitives.asymmetric import rsa as _rsa


_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _validate_uuid(s: str) -> str | None:
    """Return error string if `s` is not a canonical UUID; None on success."""
    if not _UUID_RE.match(s.strip()):
        return "error: API key ID is not a valid UUID"
    return None


def _validate_pem(path: Path) -> str | None:
    """Return error string if PEM at `path` is missing/malformed/non-RSA; None on success."""
    if not path.exists():
        return f"error: private key at {path} does not exist"
    try:
        data = path.read_bytes()
        key = serialization.load_pem_private_key(data, password=None)
    except Exception:
        return (
            f"error: private key at {path} is not a valid PKCS#1 or PKCS#8 RSA PEM"
        )
    if not isinstance(key, _rsa.RSAPrivateKey):
        return (
            f"error: private key at {path} is not a valid PKCS#1 or PKCS#8 RSA PEM"
        )
    return None


import shutil


def cmd_setup(argv: list[str], stdin=None, stdout=None, session_factory=None) -> int:
    """Interactive one-time setup. See spec §4.3.

    stdin/stdout/session_factory are dependency-injection points for tests;
    when omitted, the CLI uses real stdin / stdout / requests.Session.
    """
    parser = argparse.ArgumentParser(prog="kalshi_cli.py setup")
    parser.parse_args(argv)

    si = stdin or sys.stdin
    so = stdout or sys.stdout

    def prompt(label: str) -> str:
        print(label, end="", file=so, flush=True)
        line = si.readline()
        if not line:
            die("error: setup aborted (EOF on prompt)", exit_code=2)
        return line.rstrip("\n").strip()

    key_id = prompt("Kalshi API key ID (UUID): ")
    err = _validate_uuid(key_id)
    if err:
        die(err, exit_code=2)

    pem_src_str = prompt("Path to your Kalshi RSA private key PEM file: ")
    pem_src = _expand(pem_src_str)
    err = _validate_pem(pem_src)
    if err:
        die(err, exit_code=2)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.chmod(0o700)
    dest = DEFAULT_KEY_PATH
    if pem_src.resolve() != dest.resolve():
        if dest.exists():
            ans = prompt(f"overwrite existing key at {dest}? [y/N]: ").lower()
            if ans != "y":
                die("setup aborted: existing key not overwritten", exit_code=2)
        # Copy then chmod *immediately*, before any further IO, so the PEM
        # is never observable on disk with default-umask perms (typically 0o644).
        shutil.copyfile(pem_src, dest)
        dest.chmod(0o600)

    # Same discipline for the TOML — chmod right after creation.
    CONFIG_PATH.write_text(
        f'key_id = "{key_id}"\n'
        f'private_key_path = "{dest}"\n'
    )
    CONFIG_PATH.chmod(0o600)

    # Sanity check: signed GET /portfolio/balance.
    # Spec §4.3 step 6 mandates the "setup failed:" framing on errors so the
    # user knows the *whole setup process* did not complete (vs. a generic
    # API error from a routine call). We perform the request inline rather
    # than via KalshiClient.get() so we control the error message.
    pem_bytes = dest.read_bytes()
    signer = Signer(pem_bytes)
    session = (session_factory() if session_factory else requests.Session())

    full_path = API_PREFIX + "/portfolio/balance"
    ts_ms = int(time.time() * 1000)
    sig = signer.sign(ts_ms, "GET", signed_path(full_path))
    headers = {
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-TIMESTAMP": str(ts_ms),
        "KALSHI-ACCESS-SIGNATURE": sig,
        "Accept": "application/json",
    }
    def _rollback_and_die(message: str, exit_code: int) -> None:
        """Unlink the just-written PEM and config TOML before failing.

        Without this, a sanity-check failure leaves bad credentials on
        disk; the next subcommand call hits a 401 with non-`setup failed:`
        framing, which obscures the root cause. We unlink unconditionally
        on any probe failure (401, other API status, network error). If
        the user accepted overwrite of pre-existing credentials and the
        new ones fail, the old ones are gone too — that's intentional;
        the failure message is explicit so they aren't surprised.
        """
        if dest.exists():
            dest.unlink()
        if CONFIG_PATH.exists():
            CONFIG_PATH.unlink()
        die(
            f"setup failed: {message} — partial install rolled back; "
            "no credentials stored",
            exit_code=exit_code,
        )

    try:
        resp = session.request("GET", BASE_URL + full_path, headers=headers, timeout=_TIMEOUT)
    except requests.exceptions.RequestException as e:
        _rollback_and_die(f"network — {e}", exit_code=4)

    if resp.status_code == 401:
        _rollback_and_die(
            "401 — credentials rejected (key/PEM mismatch or clock drift)",
            exit_code=3,
        )
    if resp.status_code != 200:
        body_trim = (resp.text or "")[:200]
        # Defense in depth: a misbehaving server (or proxy) could echo our
        # key_id back in a 5xx body. Redact it before it lands in stderr.
        body_trim = body_trim.replace(key_id, "<redacted>")
        _rollback_and_die(
            f"kalshi API {resp.status_code} — {body_trim}",
            exit_code=3,
        )

    bal = resp.json()
    cash = int(bal["balance"])
    pv = int(bal["portfolio_value"])
    print(f"setup ok — total portfolio: ${(cash+pv)/100:.2f}", file=so)
    return 0


_SUBCOMMANDS = ("account", "search", "prices", "setup")


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]

    # Manual dispatch: argparse subparsers + REMAINDER doesn't pass `-`-prefixed
    # tokens (notably `--help`) through to the subcommand cleanly. Instead,
    # detect the subcommand ourselves and let each cmd_* parser handle its own
    # `--help` (argparse exits 0 from there).
    if argv and argv[0] in _SUBCOMMANDS:
        sub, rest = argv[0], argv[1:]
        if sub == "setup":
            return cmd_setup(rest)
        # If the user only asked for help, skip credential loading so
        # `<sub> --help` works on a fresh box without `setup` having run.
        if any(a in ("-h", "--help") for a in rest):
            client = None
        else:
            creds = load_credentials()
            pem_bytes = creds.private_key_path.read_bytes()
            signer = Signer(pem_bytes)
            client = KalshiClient(key_id=creds.key_id, signer=signer)
        if sub == "account":
            return cmd_account(rest, client=client)
        if sub == "search":
            return cmd_search(rest, client=client)
        if sub == "prices":
            return cmd_prices(rest, client=client)
        return 1  # pragma: no cover — _SUBCOMMANDS guarded above

    # Fall through to argparse so top-level `--help` and unknown-subcommand
    # error reporting both behave correctly.
    parser = argparse.ArgumentParser(
        prog="kalshi_cli.py",
        description="Read-only Kalshi CLI: account, search, prices, setup.",
    )
    subs = parser.add_subparsers(dest="subcommand", required=True)
    for name in _SUBCOMMANDS:
        subs.add_parser(name, add_help=False)
    parser.parse_args(argv)
    return 1  # pragma: no cover — parse_args exits before reaching here


if __name__ == "__main__":
    sys.exit(main())
