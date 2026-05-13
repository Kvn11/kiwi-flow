"""End-to-end tests for the Kalshi skill handlers.

The handlers live at `skill-library/kalshi/handlers.py`; we import them via the
same dispatcher discovery pattern Kiwi uses at runtime, so this also smoke-tests
that the dispatch wiring picks them up. Each test stubs out the HTTP layer
(`KalshiClient._session.request`) so no network calls fire.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from kiwi.credentials import (
    CredentialField,
    CredentialSchema,
    broker,
)
from kiwi.credentials import registry as cred_registry_module
from kiwi.credentials.registry import CredentialRegistry, set_credential_registry
from kiwi.credentials.store import CredentialStore
from kiwi.skill_dispatch import get_handler, reset_for_tests
from kiwi.skill_dispatch.registry import _import_handlers_file


def _generate_test_pem() -> bytes:
    """Build a fresh RSA private key as PKCS#8 PEM for the test fixture.

    Generated per-test-run rather than hardcoded so the key never accidentally
    becomes a real-world credential and the test is self-contained.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


_TEST_PEM = _generate_test_pem()


@pytest.fixture(autouse=True)
def _import_kalshi_handlers():
    """Import skill-library/kalshi/handlers.py so its decorators register the handlers."""
    reset_for_tests()
    repo_root = Path(__file__).resolve().parents[2]
    handlers_path = repo_root / "skill-library" / "kalshi" / "handlers.py"
    assert handlers_path.is_file(), f"expected handlers at {handlers_path}"
    ok = _import_handlers_file(handlers_path)
    assert ok, "handlers.py failed to import"
    yield
    reset_for_tests()


@pytest.fixture
def kalshi_registered():
    schema = CredentialSchema(
        skill_name="kalshi",
        fields=(
            CredentialField(name="api_key_id", label="API Key ID", type="text"),
            CredentialField(name="api_private_key", label="Private Key (PEM)", type="textarea"),
        ),
    )
    set_credential_registry(CredentialRegistry({"kalshi": schema}))
    yield schema
    cred_registry_module.reset_credential_registry()


@pytest.fixture
def configured_store(tmp_path: Path):
    store = CredentialStore(tmp_path / "credentials.json")
    broker.set_store(store)
    broker.reset_logins_for_tests()
    store.write_values(
        "kalshi",
        {
            "api_key_id": "00000000-0000-0000-0000-000000000000",
            "api_private_key": _TEST_PEM.decode("ascii"),
        },
    )
    yield store
    broker.set_store(None)
    broker.reset_logins_for_tests()


def _stub_response(status: int, json_body: dict | None = None, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_body or {}
    resp.text = text
    return resp


def _patch_client_session(stub_get):
    """Patch requests.Session().request used by KalshiClient.

    `stub_get(method, url, headers, params, timeout) -> response_mock`
    """
    return patch.object(requests.Session, "request", side_effect=stub_get)


# ── Handlers are registered ────────────────────────────────────────────


def test_handlers_registered() -> None:
    assert get_handler("kalshi", "account") is not None
    assert get_handler("kalshi", "search") is not None
    assert get_handler("kalshi", "prices") is not None


# ── kalshi_account ─────────────────────────────────────────────────────


def test_account_returns_canonical_json_shape(kalshi_registered, configured_store) -> None:
    handler = get_handler("kalshi", "account")
    assert handler is not None

    def stub(method, url, **kwargs):
        if "/portfolio/balance" in url:
            return _stub_response(200, {"balance": 12254, "portfolio_value": 1047})
        if "/portfolio/positions" in url:
            return _stub_response(
                200,
                {
                    "market_positions": [
                        {
                            "ticker": "KXCODINGMODEL-26DEC-ANTH",
                            "position_fp": "6",
                            "market_exposure_dollars": "4.80",
                        }
                    ],
                    "cursor": "",
                },
            )
        if "/events/KXCODINGMODEL-26DEC" in url:
            return _stub_response(
                200,
                {
                    "event": {
                        "title": "Best coding model by Dec 26th?",
                        "markets": [{"ticker": "KXCODINGMODEL-26DEC-ANTH", "yes_sub_title": "Anthropic"}],
                    }
                },
            )
        return _stub_response(404, text="not found")

    with _patch_client_session(stub):
        result_str = handler({})

    payload = json.loads(result_str)
    assert payload == {
        "cash_cents": 12254,
        "positions_cents": 1047,
        "total_cents": 13301,
        "positions": [
            {
                "ticker": "KXCODINGMODEL-26DEC-ANTH",
                "event_title": "Best coding model by Dec 26th?",
                "yes_outcome": "Anthropic",
                "side": "YES",
                "position": 6,
                "exposure_cents": 480,
            }
        ],
    }


def test_account_walks_positions_cursor_to_completion(kalshi_registered, configured_store) -> None:
    handler = get_handler("kalshi", "account")
    page_calls = {"n": 0}

    def stub(method, url, **kwargs):
        if "/portfolio/balance" in url:
            return _stub_response(200, {"balance": 0, "portfolio_value": 0})
        if "/portfolio/positions" in url:
            page_calls["n"] += 1
            if page_calls["n"] == 1:
                return _stub_response(200, {"market_positions": [], "cursor": "p2"})
            return _stub_response(200, {"market_positions": [], "cursor": ""})
        return _stub_response(404, text="not found")

    with _patch_client_session(stub):
        handler({})

    assert page_calls["n"] == 2  # Both pages walked


def test_account_translates_401_to_credential_rejected(kalshi_registered, configured_store) -> None:
    """A 401 from /portfolio/balance should bubble up as CredentialRejected so
    the dispatcher emits the 'rejected by upstream' canonical wording."""
    from kiwi.credentials.errors import CredentialRejected

    handler = get_handler("kalshi", "account")

    def stub(method, url, **kwargs):
        return _stub_response(401, text="unauthorized")

    with _patch_client_session(stub), pytest.raises(CredentialRejected):
        handler({})


def test_malformed_pem_translates_to_credential_rejected(kalshi_registered, tmp_path: Path) -> None:
    """A malformed PEM in the store should surface as CredentialRejected, not as a
    cryptography.ValueError that the dispatcher would misclassify as 'rejected arguments'."""
    from kiwi.credentials.errors import CredentialRejected

    store = CredentialStore(tmp_path / "credentials.json")
    broker.set_store(store)
    broker.reset_logins_for_tests()
    store.write_values(
        "kalshi",
        {
            "api_key_id": "00000000-0000-0000-0000-000000000000",
            "api_private_key": "-----BEGIN PRIVATE KEY-----\nnot-valid-pem-data\n-----END PRIVATE KEY-----\n",
        },
    )
    try:
        handler = get_handler("kalshi", "account")
        with pytest.raises(CredentialRejected):
            handler({})
    finally:
        broker.set_store(None)
        broker.reset_logins_for_tests()


# ── kalshi_search ──────────────────────────────────────────────────────


def test_search_requires_query(kalshi_registered, configured_store) -> None:
    handler = get_handler("kalshi", "search")
    with pytest.raises(ValueError, match="query"):
        handler({})


def test_search_rejects_negative_limit(kalshi_registered, configured_store) -> None:
    handler = get_handler("kalshi", "search")
    with pytest.raises(ValueError, match="limit"):
        handler({"query": "ethereum", "limit": -1})


def test_search_returns_matches_with_open_events(kalshi_registered, configured_store) -> None:
    handler = get_handler("kalshi", "search")

    def stub(method, url, **kwargs):
        if "/series" in url:
            return _stub_response(
                200,
                {
                    "series": [
                        {
                            "ticker": "KXETH",
                            "title": "Ethereum hourly",
                            "category": "Crypto",
                            "frequency": "hourly",
                            "tags": ["crypto", "ethereum"],
                        },
                        {
                            "ticker": "KXBTC",
                            "title": "Bitcoin hourly",
                            "category": "Crypto",
                            "frequency": "hourly",
                            "tags": ["crypto", "bitcoin"],
                        },
                    ],
                    "cursor": "",
                },
            )
        if "/events" in url:
            params = kwargs.get("params") or {}
            assert params.get("status") == "open"
            assert params.get("series_ticker") == "KXETH"
            return _stub_response(
                200,
                {"events": [{"event_ticker": "KXETH-26APR2823", "title": "ETH Apr 28 23:00", "close_time": "2026-04-28T23:00:00Z"}]},
            )
        return _stub_response(404, text="not found")

    with _patch_client_session(stub):
        result_str = handler({"query": "ethereum"})

    payload = json.loads(result_str)
    assert payload["query"] == "ethereum"
    assert len(payload["series"]) == 1
    s = payload["series"][0]
    assert s["ticker"] == "KXETH"
    assert s["events"] == [{"ticker": "KXETH-26APR2823", "title": "ETH Apr 28 23:00", "close_time": "2026-04-28T23:00:00Z"}]


def test_search_all_events_drops_status_filter(kalshi_registered, configured_store) -> None:
    handler = get_handler("kalshi", "search")
    captured = {}

    def stub(method, url, **kwargs):
        if "/series" in url:
            return _stub_response(
                200,
                {"series": [{"ticker": "KXETH", "title": "ethereum", "tags": ["ethereum"]}], "cursor": ""},
            )
        if "/events" in url:
            captured["params"] = kwargs.get("params") or {}
            return _stub_response(200, {"events": []})
        return _stub_response(404)

    with _patch_client_session(stub):
        handler({"query": "ethereum", "all_events": True})

    assert "status" not in captured["params"]


# ── kalshi_prices ──────────────────────────────────────────────────────


def test_prices_requires_ticker(kalshi_registered, configured_store) -> None:
    handler = get_handler("kalshi", "prices")
    with pytest.raises(ValueError, match="ticker"):
        handler({})


def test_prices_rejects_invalid_kind(kalshi_registered, configured_store) -> None:
    handler = get_handler("kalshi", "prices")
    with pytest.raises(ValueError, match="kind"):
        handler({"ticker": "KXETH-26APR2823", "kind": "weird"})


def test_prices_returns_market_when_market_lookup_succeeds(kalshi_registered, configured_store) -> None:
    handler = get_handler("kalshi", "prices")

    def stub(method, url, **kwargs):
        if "/markets/KXETH-26APR2823-B2310" in url:
            return _stub_response(
                200,
                {
                    "market": {
                        "ticker": "KXETH-26APR2823-B2310",
                        "yes_sub_title": ">= 2310",
                        "yes_bid_dollars": "0.55",
                        "yes_ask_dollars": "0.57",
                        "last_price_dollars": "0.56",
                        "no_bid_dollars": "0.43",
                        "no_ask_dollars": "0.45",
                        "volume_24h_fp": "1500",
                        "volume_fp": "12000",
                        "close_time": "2026-04-28T23:00:00Z",
                    }
                },
            )
        return _stub_response(404)

    with _patch_client_session(stub):
        result_str = handler({"ticker": "KXETH-26APR2823-B2310"})

    payload = json.loads(result_str)
    assert payload["kind"] == "market"
    assert payload["ticker"] == "KXETH-26APR2823-B2310"
    assert payload["yes_bid"] == 0.55
    assert payload["volume_24h"] == 1500


def test_prices_falls_back_to_event_when_market_missing(kalshi_registered, configured_store) -> None:
    handler = get_handler("kalshi", "prices")

    def stub(method, url, **kwargs):
        if "/markets/KXETH-26APR2823" in url:
            return _stub_response(404)
        if "/events/KXETH-26APR2823" in url:
            return _stub_response(
                200,
                {
                    "event": {
                        "event_ticker": "KXETH-26APR2823",
                        "title": "ETH ladder",
                        "close_time": "2026-04-28T23:00:00Z",
                        "markets": [
                            {
                                "ticker": "KXETH-26APR2823-B2310",
                                "yes_sub_title": ">= 2310",
                                "yes_bid_dollars": "0.50",
                                "yes_ask_dollars": "0.52",
                                "last_price_dollars": "0.51",
                                "volume_24h_fp": "1000",
                                "volume_fp": "5000",
                            }
                        ],
                    }
                },
            )
        return _stub_response(404)

    with _patch_client_session(stub):
        result_str = handler({"ticker": "KXETH-26APR2823"})

    payload = json.loads(result_str)
    assert payload["kind"] == "event"
    assert payload["event_ticker"] == "KXETH-26APR2823"
    assert len(payload["markets"]) == 1


def test_prices_with_kind_market_does_not_probe_events(kalshi_registered, configured_store) -> None:
    handler = get_handler("kalshi", "prices")
    paths_called = []

    def stub(method, url, **kwargs):
        paths_called.append(url)
        if "/markets/" in url:
            return _stub_response(404)
        return _stub_response(200, {"event": {"event_ticker": "x", "markets": []}})

    with _patch_client_session(stub), pytest.raises(ValueError, match="no market matching"):
        handler({"ticker": "KXBOGUS", "kind": "market"})

    assert any("/markets/" in p for p in paths_called)
    assert not any("/events/" in p for p in paths_called), "should not have probed /events when kind=market"


def test_prices_404_on_both_paths_raises_value_error(kalshi_registered, configured_store) -> None:
    handler = get_handler("kalshi", "prices")

    def stub(method, url, **kwargs):
        return _stub_response(404)

    with _patch_client_session(stub), pytest.raises(ValueError, match="no event or market"):
        handler({"ticker": "KXBOGUS"})
