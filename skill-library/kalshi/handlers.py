"""In-process skill-tool handlers for the Kalshi skill."""

from __future__ import annotations

import json
import logging

from kiwi.credentials import broker
from kiwi.credentials.errors import CredentialRejected
from kiwi.skill_dispatch import SkillToolArgumentError, register_skill_tool

from .kalshi_lib import (
    KalshiAPIError,
    KalshiClient,
    Signer,
    enrich_positions,
    event_to_json,
    fetch_all_series,
    fetch_or_404,
    market_to_json,
    match_series,
)

logger = logging.getLogger(__name__)

SKILL_NAME = "kalshi"
_MAX_POSITIONS_PAGES = 200


class _AuthTranslatingKalshiClient(KalshiClient):
    """KalshiClient that translates HTTP 401 into CredentialRejected.

    Used so every kalshi_lib helper that calls `client.get(...)` gets the
    translation for free, without per-call wrapping or instance monkey-patching.
    """

    def get(self, path: str, params: dict | None = None) -> dict:
        try:
            return super().get(path, params=params)
        except KalshiAPIError as exc:
            if exc.status == 401:
                raise CredentialRejected(SKILL_NAME, reason="key/PEM mismatch or clock drift") from exc
            raise


def _build_client() -> KalshiClient:
    """Pull values from the broker, build a signed REST client.

    Broker exceptions (CredentialNotConfigured / Rejected / etc.) propagate up
    to the dispatcher, which formats them into LLM-visible strings. A malformed
    PEM is translated to CredentialRejected so the user is pointed at Settings
    rather than seeing a misleading "rejected arguments" error.
    """
    creds = broker.get_values(SKILL_NAME)
    try:
        signer = Signer(creds["api_private_key"].encode("utf-8"))
    except Exception as exc:
        raise CredentialRejected(SKILL_NAME, reason="private key PEM is malformed") from exc
    return _AuthTranslatingKalshiClient(key_id=creds["api_key_id"], signer=signer)


@register_skill_tool(skill=SKILL_NAME, tool="account")
def kalshi_account(args: dict) -> str:
    """Cash, positions, total portfolio value as a JSON string.

    Args: none. Returns {cash_cents, positions_cents, total_cents, positions: [...]}.
    """
    client = _build_client()
    bal = client.get("/portfolio/balance")

    # Walk the positions cursor to completion. Bounded both by repeated-cursor
    # detection and a hard page cap so a misbehaving server can't pin the agent
    # in an infinite loop.
    all_market_positions: list[dict] = []
    cursor = ""
    for _ in range(_MAX_POSITIONS_PAGES):
        params: dict = {"limit": 200}
        if cursor:
            params["cursor"] = cursor
        page = client.get("/portfolio/positions", params=params)
        all_market_positions.extend(page.get("market_positions") or [])
        next_cursor = page.get("cursor") or ""
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
    else:
        logger.warning("kalshi_account hit positions page cap (%d); truncating", _MAX_POSITIONS_PAGES)

    cash = int(bal["balance"])
    positions_value = int(bal["portfolio_value"])
    total = cash + positions_value

    positions_out = enrich_positions(client, all_market_positions)

    return json.dumps(
        {
            "cash_cents": cash,
            "positions_cents": positions_value,
            "total_cents": total,
            "positions": positions_out,
        },
        separators=(",", ":"),
    )


@register_skill_tool(skill=SKILL_NAME, tool="search")
def kalshi_search(args: dict) -> str:
    """Find Kalshi series by keyword, returning matches with their open events.

    Args:
        query (str, required): one or more keywords; AND-matched (case-insensitive
            substring) against series title, ticker, tags, category.
        limit (int, optional, default=10): cap on number of series returned. 0 = no cap.
        all_events (bool, optional, default=False): include non-open events when True.

    Returns a JSON string of shape {query, series: [{ticker, title, category,
    frequency, events: [{ticker, title, close_time}, ...]}, ...]}.
    """
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        raise SkillToolArgumentError("'query' is required and must be a non-empty string")

    limit = args.get("limit", 10)
    if not isinstance(limit, int) or limit < 0:
        raise SkillToolArgumentError("'limit' must be a non-negative integer")

    all_events = bool(args.get("all_events", False))

    client = _build_client()
    all_series = fetch_all_series(client)
    matched = match_series(all_series, query)
    if limit > 0:
        matched = matched[:limit]

    enriched = []
    for s in matched:
        params = {"series_ticker": s["ticker"]}
        if not all_events:
            params["status"] = "open"
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

    return json.dumps({"query": query, "series": enriched}, separators=(",", ":"))


@register_skill_tool(skill=SKILL_NAME, tool="prices")
def kalshi_prices(args: dict) -> str:
    """Current prices for an event (ladder of binary contracts) or single market.

    Args:
        ticker (str, required): event ticker (e.g. "KXETH-26APR2823") or market
            ticker (e.g. "KXETH-26APR2823-B2310").
        kind (str, optional): "event" or "market". When omitted, the handler
            probes /markets/<ticker> first then falls back to /events/<ticker>.

    Returns a JSON string. Market shape: {kind: "market", ticker, yes_sub_title,
    yes_bid, yes_ask, last_price, no_bid, no_ask, volume_24h, volume, close_time}.
    Event shape: {kind: "event", event_ticker, title, close_time, markets: [...]}.
    """
    ticker = args.get("ticker")
    if not isinstance(ticker, str):
        raise SkillToolArgumentError("'ticker' is required and must be a string")
    ticker = ticker.strip()
    if not ticker:
        raise SkillToolArgumentError("'ticker' must not be empty")

    kind = args.get("kind")
    if kind not in (None, "event", "market"):
        raise SkillToolArgumentError("'kind' must be 'event', 'market', or omitted")

    client = _build_client()
    market_obj = None
    event_obj = None

    if kind == "market":
        market_obj = fetch_or_404(client, f"/markets/{ticker}")
        if market_obj is None:
            raise SkillToolArgumentError(f"no market matching ticker {ticker}")
    elif kind == "event":
        event_obj = fetch_or_404(client, f"/events/{ticker}", params={"with_nested_markets": "true"})
        if event_obj is None:
            raise SkillToolArgumentError(f"no event matching ticker {ticker}")
    else:
        market_obj = fetch_or_404(client, f"/markets/{ticker}")
        if market_obj is None:
            event_obj = fetch_or_404(client, f"/events/{ticker}", params={"with_nested_markets": "true"})
            if event_obj is None:
                raise SkillToolArgumentError(f"no event or market matching ticker {ticker}")

    payload = market_to_json(market_obj) if market_obj is not None else event_to_json(event_obj)
    return json.dumps(payload, separators=(",", ":"))
