"""Tests for the credentials broker."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from kiwi.credentials import (
    CredentialField,
    CredentialNotConfigured,
    CredentialRejected,
    CredentialSchema,
    NoLoginRegistered,
    Token,
    UnknownSkill,
    broker,
)
from kiwi.credentials import registry as registry_module
from kiwi.credentials.registry import CredentialRegistry, set_credential_registry
from kiwi.credentials.store import CredentialStore


@pytest.fixture
def registry_with_kalshi():
    schema = CredentialSchema(
        skill_name="kalshi",
        fields=(
            CredentialField(name="api_key_id", label="API Key ID", type="text"),
            CredentialField(name="api_private_key", label="Private Key", type="textarea"),
        ),
    )
    set_credential_registry(CredentialRegistry({"kalshi": schema}))
    yield schema
    registry_module.reset_credential_registry()


@pytest.fixture
def fresh_store(tmp_path: Path):
    store = CredentialStore(tmp_path / "credentials.json")
    broker.set_store(store)
    broker.reset_logins_for_tests()
    yield store
    broker.set_store(None)
    broker.reset_logins_for_tests()


# ── get_values ─────────────────────────────────────────────────────────


def test_get_values_raises_unknown_for_unregistered_skill(registry_with_kalshi, fresh_store) -> None:
    with pytest.raises(UnknownSkill):
        broker.get_values("nonsense")


def test_get_values_raises_when_no_entry(registry_with_kalshi, fresh_store) -> None:
    with pytest.raises(CredentialNotConfigured) as exc:
        broker.get_values("kalshi")
    assert sorted(exc.value.missing_fields) == ["api_key_id", "api_private_key"]


def test_get_values_raises_when_partial(registry_with_kalshi, fresh_store) -> None:
    fresh_store.write_values("kalshi", {"api_key_id": "abc"})
    with pytest.raises(CredentialNotConfigured) as exc:
        broker.get_values("kalshi")
    assert exc.value.missing_fields == ["api_private_key"]


def test_get_values_treats_whitespace_as_empty(registry_with_kalshi, fresh_store) -> None:
    fresh_store.write_values("kalshi", {"api_key_id": "abc", "api_private_key": "   "})
    with pytest.raises(CredentialNotConfigured) as exc:
        broker.get_values("kalshi")
    assert exc.value.missing_fields == ["api_private_key"]


def test_get_values_returns_dict_when_complete(registry_with_kalshi, fresh_store) -> None:
    fresh_store.write_values("kalshi", {"api_key_id": "abc", "api_private_key": "PEM"})
    assert broker.get_values("kalshi") == {"api_key_id": "abc", "api_private_key": "PEM"}


# ── get_token ──────────────────────────────────────────────────────────


def test_get_token_returns_cached_if_fresh(registry_with_kalshi, fresh_store) -> None:
    fresh_store.write_values("kalshi", {"api_key_id": "abc", "api_private_key": "PEM"})
    fresh_store.write_token("kalshi", Token(access_token="cached", expires_at=int(time.time()) + 3600))

    # No login_fn registered — but cache hit means we shouldn't need it.
    assert broker.get_token("kalshi") == "cached"


def test_get_token_invokes_login_fn_on_cold_cache(registry_with_kalshi, fresh_store) -> None:
    fresh_store.write_values("kalshi", {"api_key_id": "abc", "api_private_key": "PEM"})

    captured = {}

    def fake_login(values: dict[str, str]) -> Token:
        captured["values"] = values
        return Token(access_token="fresh-token", expires_at=int(time.time()) + 3600)

    broker.register_login("kalshi", fake_login)

    assert broker.get_token("kalshi") == "fresh-token"
    assert captured["values"] == {"api_key_id": "abc", "api_private_key": "PEM"}

    # Subsequent call returns cached value, login_fn not re-invoked.
    captured.clear()
    assert broker.get_token("kalshi") == "fresh-token"
    assert "values" not in captured


def test_get_token_re_invokes_login_when_token_about_to_expire(registry_with_kalshi, fresh_store) -> None:
    fresh_store.write_values("kalshi", {"api_key_id": "abc", "api_private_key": "PEM"})
    # Expires in 30s — within the 60s refresh skew, so should be considered stale.
    fresh_store.write_token("kalshi", Token(access_token="stale", expires_at=int(time.time()) + 30))

    def fake_login(values):
        return Token(access_token="renewed", expires_at=int(time.time()) + 3600)

    broker.register_login("kalshi", fake_login)
    assert broker.get_token("kalshi") == "renewed"


def test_get_token_raises_not_configured_when_values_missing(registry_with_kalshi, fresh_store) -> None:
    broker.register_login("kalshi", lambda v: Token(access_token="x"))
    with pytest.raises(CredentialNotConfigured):
        broker.get_token("kalshi")


def test_get_token_raises_no_login_when_callback_missing(registry_with_kalshi, fresh_store) -> None:
    fresh_store.write_values("kalshi", {"api_key_id": "abc", "api_private_key": "PEM"})
    with pytest.raises(NoLoginRegistered):
        broker.get_token("kalshi")


def test_get_token_translates_login_exceptions_to_rejected(registry_with_kalshi, fresh_store) -> None:
    fresh_store.write_values("kalshi", {"api_key_id": "abc", "api_private_key": "PEM"})

    def boom(values):
        raise RuntimeError("upstream returned 401 Unauthorized")

    broker.register_login("kalshi", boom)
    with pytest.raises(CredentialRejected) as exc:
        broker.get_token("kalshi")
    # The reason is intentionally NOT included to avoid leaking upstream error
    # bodies that may echo the credential.
    assert "401" not in str(exc.value)
    assert "RuntimeError" not in str(exc.value)


def test_get_token_rejected_when_login_returns_non_token(registry_with_kalshi, fresh_store) -> None:
    fresh_store.write_values("kalshi", {"api_key_id": "abc", "api_private_key": "PEM"})
    broker.register_login("kalshi", lambda v: "just a string")
    with pytest.raises(CredentialRejected):
        broker.get_token("kalshi")


def test_get_token_re_raises_explicit_rejected(registry_with_kalshi, fresh_store) -> None:
    fresh_store.write_values("kalshi", {"api_key_id": "abc", "api_private_key": "PEM"})

    def login(values):
        raise CredentialRejected("kalshi", reason="explicit reason from skill")

    broker.register_login("kalshi", login)
    with pytest.raises(CredentialRejected) as exc:
        broker.get_token("kalshi")
    assert "explicit reason from skill" in str(exc.value)


# ── invalidate_token ───────────────────────────────────────────────────


def test_invalidate_token_clears_cache(registry_with_kalshi, fresh_store) -> None:
    fresh_store.write_values("kalshi", {"api_key_id": "abc", "api_private_key": "PEM"})
    fresh_store.write_token("kalshi", Token(access_token="t1", expires_at=int(time.time()) + 3600))

    call_count = {"n": 0}

    def login(values):
        call_count["n"] += 1
        return Token(access_token=f"t{call_count['n'] + 1}", expires_at=int(time.time()) + 3600)

    broker.register_login("kalshi", login)

    # Cached value first
    assert broker.get_token("kalshi") == "t1"
    assert call_count["n"] == 0

    # Invalidate, then ask again — login_fn runs and returns a new token.
    broker.invalidate_token("kalshi")
    assert broker.get_token("kalshi") == "t2"
    assert call_count["n"] == 1


# ── set_values ─────────────────────────────────────────────────────────


def test_set_values_rejects_unknown_field_names(registry_with_kalshi, fresh_store) -> None:
    with pytest.raises(ValueError) as exc:
        broker.set_values("kalshi", {"not_a_field": "x"})
    assert "not_a_field" in str(exc.value)


def test_set_values_rejects_unknown_skill(registry_with_kalshi, fresh_store) -> None:
    with pytest.raises(UnknownSkill):
        broker.set_values("nonsense", {"api_key_id": "x"})


def test_set_values_partial_update_preserves_untouched(registry_with_kalshi, fresh_store) -> None:
    broker.set_values("kalshi", {"api_key_id": "abc", "api_private_key": "PEM"})
    broker.set_values("kalshi", {"api_key_id": "new"})

    entry = fresh_store.read_one("kalshi")
    assert entry is not None
    assert entry.values == {"api_key_id": "new", "api_private_key": "PEM"}


# ── clear ──────────────────────────────────────────────────────────────


def test_clear_wipes_both_values_and_token(registry_with_kalshi, fresh_store) -> None:
    fresh_store.write_values("kalshi", {"api_key_id": "abc", "api_private_key": "PEM"})
    fresh_store.write_token("kalshi", Token(access_token="t"))

    broker.clear("kalshi")

    assert fresh_store.read_one("kalshi") is None


def test_clear_works_for_orphaned_entry(registry_with_kalshi, fresh_store) -> None:
    """Skill schema removed (e.g. uninstall), entry remains — clear must still work."""
    fresh_store.write_values("orphan", {"some_field": "x"})

    # registry has only kalshi, but clear should be lenient.
    broker.clear("orphan")
    assert fresh_store.read_one("orphan") is None


# ── status ─────────────────────────────────────────────────────────────


def test_status_for_unconfigured_skill(registry_with_kalshi, fresh_store) -> None:
    s = broker.status("kalshi")
    assert s == {
        "configured": False,
        "fields_set": [],
        "has_token": False,
        "token_expires_at": None,
        "updated_at": None,
    }


def test_status_for_partially_configured_skill(registry_with_kalshi, fresh_store) -> None:
    fresh_store.write_values("kalshi", {"api_key_id": "abc"})
    s = broker.status("kalshi")
    assert s["configured"] is False
    assert s["fields_set"] == ["api_key_id"]
    assert s["has_token"] is False


def test_status_for_fully_configured_skill_with_fresh_token(registry_with_kalshi, fresh_store) -> None:
    fresh_store.write_values("kalshi", {"api_key_id": "abc", "api_private_key": "PEM"})
    expires = int(time.time()) + 3600
    fresh_store.write_token("kalshi", Token(access_token="t", expires_at=expires))

    s = broker.status("kalshi")
    assert s["configured"] is True
    assert sorted(s["fields_set"]) == ["api_key_id", "api_private_key"]
    assert s["has_token"] is True
    assert s["token_expires_at"] == expires
    assert isinstance(s["updated_at"], str)


def test_status_does_not_contain_values(registry_with_kalshi, fresh_store) -> None:
    """Defense-in-depth: the status dict must never contain raw values."""
    fresh_store.write_values("kalshi", {"api_key_id": "SECRET-VALUE-ABC", "api_private_key": "SECRET-PEM-XYZ"})
    s = broker.status("kalshi")
    serialized = repr(s)
    assert "SECRET-VALUE-ABC" not in serialized
    assert "SECRET-PEM-XYZ" not in serialized


def test_status_unknown_skill_raises(registry_with_kalshi, fresh_store) -> None:
    with pytest.raises(UnknownSkill):
        broker.status("nonsense")
