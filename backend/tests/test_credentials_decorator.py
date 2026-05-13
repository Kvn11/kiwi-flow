"""Tests for `kiwi.credentials.decorators.with_credentials`.

The most important guarantee: each broker error path produces a *distinct* LLM-visible
string, and **none** of them ever echo the credential values back to the agent.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from kiwi.credentials import (
    CredentialField,
    CredentialSchema,
    Token,
    broker,
    with_credentials,
)
from kiwi.credentials import registry as registry_module
from kiwi.credentials.errors import CredentialRejected as RejectedExc
from kiwi.credentials.registry import CredentialRegistry, set_credential_registry
from kiwi.credentials.store import CredentialStore

SECRET_KEY = "SECRET-API-KEY-VALUE"
SECRET_PEM = "SECRET-PRIVATE-PEM"


@pytest.fixture
def registered_kalshi():
    schema = CredentialSchema(
        skill_name="kalshi",
        fields=(
            CredentialField(name="api_key_id", label="API Key ID", type="text"),
            CredentialField(name="api_private_key", label="Private Key (PEM)", type="textarea"),
        ),
    )
    set_credential_registry(CredentialRegistry({"kalshi": schema}))
    yield schema
    registry_module.reset_credential_registry()


@pytest.fixture
def isolated_store(tmp_path: Path):
    store = CredentialStore(tmp_path / "credentials.json")
    broker.set_store(store)
    broker.reset_logins_for_tests()
    yield store
    broker.set_store(None)
    broker.reset_logins_for_tests()


# ── Happy path ─────────────────────────────────────────────────────────


def test_decorator_passes_creds_proxy_with_fresh_token(registered_kalshi, isolated_store) -> None:
    isolated_store.write_values("kalshi", {"api_key_id": SECRET_KEY, "api_private_key": SECRET_PEM})
    isolated_store.write_token("kalshi", Token(access_token="bearer-tok", expires_at=int(time.time()) + 3600))

    @with_credentials("kalshi")
    def my_tool(creds, x: int) -> str:
        return f"called with x={x}, token={creds.token}"

    result = my_tool(42)
    assert result == "called with x=42, token=bearer-tok"


def test_decorator_strips_creds_from_signature(registered_kalshi) -> None:
    """LangChain's @tool relies on inspect.signature to build the tool schema —
    the creds proxy must not appear in the externally-visible signature."""

    import inspect

    @with_credentials("kalshi")
    def my_tool(creds, market_id: str, qty: int) -> str:
        return ""

    sig = inspect.signature(my_tool)
    assert list(sig.parameters) == ["market_id", "qty"]


# ── Error paths produce distinct, value-free strings ──────────────────


def test_not_configured_returns_settings_directive(registered_kalshi, isolated_store) -> None:
    @with_credentials("kalshi")
    def my_tool(creds) -> str:
        return "should not run"

    result = my_tool()
    assert "are not configured" in result
    assert "Settings → Credentials → kalshi" in result
    # The label list should reference the user-facing labels, not internal names.
    assert "API Key ID" in result
    assert "Private Key (PEM)" in result


def test_rejected_returns_verify_directive(registered_kalshi, isolated_store) -> None:
    isolated_store.write_values("kalshi", {"api_key_id": SECRET_KEY, "api_private_key": SECRET_PEM})

    def bad_login(values):
        raise RuntimeError("upstream said 401")

    broker.register_login("kalshi", bad_login)

    @with_credentials("kalshi")
    def my_tool(creds) -> str:
        return "should not run"

    result = my_tool()
    assert "rejected by the upstream service" in result
    assert "double-check" in result
    assert "Settings → Credentials → kalshi" in result


def test_no_login_registered_returns_internal_error(registered_kalshi, isolated_store) -> None:
    isolated_store.write_values("kalshi", {"api_key_id": SECRET_KEY, "api_private_key": SECRET_PEM})

    @with_credentials("kalshi")
    def my_tool(creds) -> str:
        return "should not run"

    result = my_tool()
    assert "did not register a login handler" in result
    assert "bug in the skill code" in result


def test_unknown_skill_returns_internal_error(isolated_store) -> None:
    """Skill not in the registry — registered_kalshi fixture not used."""
    set_credential_registry(CredentialRegistry({}))

    @with_credentials("nonsense")
    def my_tool(creds) -> str:
        return "should not run"

    result = my_tool()
    assert "has not declared a credentials schema" in result
    registry_module.reset_credential_registry()


# ── No value bytes leak through any error path ────────────────────────


@pytest.mark.parametrize(
    "scenario",
    ["not_configured", "rejected", "no_login", "unknown_skill"],
)
def test_no_value_bytes_in_any_error_string(registered_kalshi, isolated_store, scenario) -> None:
    if scenario == "not_configured":
        isolated_store.write_values("kalshi", {"api_key_id": SECRET_KEY})  # missing one
    elif scenario == "rejected":
        isolated_store.write_values("kalshi", {"api_key_id": SECRET_KEY, "api_private_key": SECRET_PEM})

        def boom(values):
            # Simulate an upstream that helpfully echoes the bad credential — the broker must drop this.
            raise RuntimeError(f"401 for key {values.get('api_key_id', '')}")

        broker.register_login("kalshi", boom)
    elif scenario == "no_login":
        isolated_store.write_values("kalshi", {"api_key_id": SECRET_KEY, "api_private_key": SECRET_PEM})
    elif scenario == "unknown_skill":
        # Override the registry with a skill that doesn't exist.
        set_credential_registry(CredentialRegistry({}))

    target_skill = "nonsense" if scenario == "unknown_skill" else "kalshi"

    @with_credentials(target_skill)
    def my_tool(creds) -> str:
        return "should not run"

    result = my_tool()
    assert SECRET_KEY not in result
    assert SECRET_PEM not in result


# ── invalidate() round-trips through the broker ───────────────────────


def test_invalidate_clears_broker_token(registered_kalshi, isolated_store) -> None:
    isolated_store.write_values("kalshi", {"api_key_id": "abc", "api_private_key": "PEM"})
    isolated_store.write_token("kalshi", Token(access_token="t-old", expires_at=int(time.time()) + 3600))

    captured = {}

    @with_credentials("kalshi")
    def my_tool(creds) -> str:
        captured["before"] = creds.token
        creds.invalidate()
        # No login_fn → re-fetch raises NoLoginRegistered, but we caught the first
        # token already, and the broker entry should be wiped.
        try:
            creds.token
        except Exception as exc:
            captured["after_exc"] = type(exc).__name__
        return "ok"

    result = my_tool()
    assert result == "ok"
    assert captured["before"] == "t-old"
    assert captured["after_exc"] == "NoLoginRegistered"
    # Broker-level token entry was cleared on invalidate
    entry = isolated_store.read_one("kalshi")
    assert entry is not None
    assert entry.token is None


# ── Sanity ──────────────────────────────────────────────────────────────


def test_decorator_requires_at_least_one_param() -> None:
    with pytest.raises(TypeError):

        @with_credentials("kalshi")
        def bad_tool() -> str:
            return ""


def test_explicit_credential_rejected_passes_through_to_string(registered_kalshi, isolated_store) -> None:
    isolated_store.write_values("kalshi", {"api_key_id": "abc", "api_private_key": "PEM"})

    def login(values):
        raise RejectedExc("kalshi", reason="some upstream-specific reason")

    broker.register_login("kalshi", login)

    @with_credentials("kalshi")
    def my_tool(creds) -> str:
        return "should not run"

    # The wrapper's string is the canonical user-facing one; the explicit reason from
    # the skill is *not* embedded into the LLM string (to keep it stable).
    result = my_tool()
    assert "rejected by the upstream service" in result
