"""Tests for the /api/credentials Gateway router.

The most important guarantee: no endpoint ever returns a raw credential value
in any response body, regardless of how the value was set.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.routers import credentials as credentials_router
from kiwi.credentials import (
    CredentialField,
    CredentialSchema,
    Token,
    broker,
)
from kiwi.credentials import registry as registry_module
from kiwi.credentials.registry import CredentialRegistry, set_credential_registry
from kiwi.credentials.store import CredentialStore

SECRET_KEY = "SUPER-SECRET-KEY-1234"
SECRET_PEM = "SUPER-SECRET-PEM-XYZ"


@pytest.fixture
def isolated_state(tmp_path: Path):
    schema = CredentialSchema(
        skill_name="kalshi",
        fields=(
            CredentialField(name="api_key_id", label="API Key ID", type="text"),
            CredentialField(name="api_private_key", label="Private Key (PEM)", type="textarea"),
        ),
    )
    set_credential_registry(CredentialRegistry({"kalshi": schema}))

    store = CredentialStore(tmp_path / "credentials.json")
    broker.set_store(store)
    broker.reset_logins_for_tests()

    yield store

    broker.set_store(None)
    broker.reset_logins_for_tests()
    registry_module.reset_credential_registry()


@pytest.fixture
def client(isolated_state, monkeypatch):
    # Bypass the enabled-skill filter — no extensions_config.json or skill files in tmp_path.
    monkeypatch.setattr(
        credentials_router,
        "_build_enabled_skill_set",
        lambda: set(credentials_router.get_credential_registry().list().keys()),
    )
    app = FastAPI()
    app.include_router(credentials_router.router)
    return TestClient(app)


# ── GET /api/credentials ───────────────────────────────────────────────


def test_list_returns_unconfigured_slot(client) -> None:
    resp = client.get("/api/credentials")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["credentials"]) == 1
    entry = data["credentials"][0]
    assert entry["skill_name"] == "kalshi"
    assert entry["configured"] is False
    assert entry["fields_set"] == []
    assert entry["has_token"] is False
    # Schema is exposed
    assert {f["name"] for f in entry["fields"]} == {"api_key_id", "api_private_key"}


def test_list_response_does_not_contain_raw_values(client, isolated_state) -> None:
    isolated_state.write_values("kalshi", {"api_key_id": SECRET_KEY, "api_private_key": SECRET_PEM})
    isolated_state.write_token("kalshi", Token(access_token="t", expires_at=int(time.time()) + 3600))

    resp = client.get("/api/credentials")
    body = resp.text  # check the raw serialized response
    assert resp.status_code == 200
    assert SECRET_KEY not in body
    assert SECRET_PEM not in body
    # The access_token JSON field must be omitted entirely from the response.
    assert "access_token" not in body


def test_list_filters_disabled_skills(client, monkeypatch) -> None:
    monkeypatch.setattr(credentials_router, "_build_enabled_skill_set", lambda: set())
    resp = client.get("/api/credentials")
    assert resp.status_code == 200
    assert resp.json()["credentials"] == []


# ── GET /api/credentials/{skill_name} ──────────────────────────────────


def test_get_returns_schema_and_status(client, isolated_state) -> None:
    isolated_state.write_values("kalshi", {"api_key_id": SECRET_KEY, "api_private_key": SECRET_PEM})

    resp = client.get("/api/credentials/kalshi")
    assert resp.status_code == 200
    data = resp.json()
    assert data["skill_name"] == "kalshi"
    assert data["configured"] is True
    assert sorted(data["fields_set"]) == ["api_key_id", "api_private_key"]
    assert SECRET_KEY not in resp.text
    assert SECRET_PEM not in resp.text


def test_get_404_for_unknown_skill(client) -> None:
    resp = client.get("/api/credentials/nonsense")
    assert resp.status_code == 404


# ── PUT /api/credentials/{skill_name} ──────────────────────────────────


def test_put_persists_values(client, isolated_state) -> None:
    resp = client.put(
        "/api/credentials/kalshi",
        json={"field_values": {"api_key_id": SECRET_KEY, "api_private_key": SECRET_PEM}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is True
    assert sorted(data["fields_set"]) == ["api_key_id", "api_private_key"]

    # Round-trip via the store directly
    entry = isolated_state.read_one("kalshi")
    assert entry is not None
    assert entry.values == {"api_key_id": SECRET_KEY, "api_private_key": SECRET_PEM}


def test_put_404_for_unknown_skill(client) -> None:
    """User cannot create new credential slots — only update declared ones."""
    resp = client.put(
        "/api/credentials/nonsense",
        json={"field_values": {"api_key_id": "x"}},
    )
    assert resp.status_code == 404


def test_put_400_for_unknown_field(client) -> None:
    resp = client.put(
        "/api/credentials/kalshi",
        json={"field_values": {"not_a_field": "x"}},
    )
    assert resp.status_code == 400


def test_put_response_does_not_contain_values(client) -> None:
    resp = client.put(
        "/api/credentials/kalshi",
        json={"field_values": {"api_key_id": SECRET_KEY, "api_private_key": SECRET_PEM}},
    )
    assert resp.status_code == 200
    assert SECRET_KEY not in resp.text
    assert SECRET_PEM not in resp.text


def test_put_partial_update_preserves_untouched(client, isolated_state) -> None:
    client.put(
        "/api/credentials/kalshi",
        json={"field_values": {"api_key_id": "first", "api_private_key": "PEM-1"}},
    )
    resp = client.put(
        "/api/credentials/kalshi",
        json={"field_values": {"api_key_id": "second"}},
    )
    assert resp.status_code == 200

    entry = isolated_state.read_one("kalshi")
    assert entry is not None
    assert entry.values == {"api_key_id": "second", "api_private_key": "PEM-1"}


# ── DELETE /api/credentials/{skill_name} ───────────────────────────────


def test_delete_wipes_values_and_token(client, isolated_state) -> None:
    isolated_state.write_values("kalshi", {"api_key_id": SECRET_KEY, "api_private_key": SECRET_PEM})
    isolated_state.write_token("kalshi", Token(access_token="t"))

    resp = client.delete("/api/credentials/kalshi")
    assert resp.status_code == 200
    assert resp.json() == {"success": True}

    assert isolated_state.read_one("kalshi") is None


def test_delete_404_for_unknown_skill(client) -> None:
    resp = client.delete("/api/credentials/nonsense")
    assert resp.status_code == 404


def test_delete_idempotent_for_configured_but_now_empty(client, isolated_state) -> None:
    """Deleting an already-empty entry should still 200 — the slot persists in the registry."""
    resp1 = client.delete("/api/credentials/kalshi")
    assert resp1.status_code == 200
    resp2 = client.delete("/api/credentials/kalshi")
    assert resp2.status_code == 200


# ── End-to-end shape regression ─────────────────────────────────────────


def test_full_flow_round_trip(client, isolated_state) -> None:
    # Initially unconfigured
    assert client.get("/api/credentials/kalshi").json()["configured"] is False

    # PUT values
    resp = client.put(
        "/api/credentials/kalshi",
        json={"field_values": {"api_key_id": SECRET_KEY, "api_private_key": SECRET_PEM}},
    )
    assert resp.status_code == 200
    assert resp.json()["configured"] is True

    # GET reflects the new state, no values leak
    detail = client.get("/api/credentials/kalshi").json()
    assert detail["configured"] is True
    assert detail["fields_set"] == sorted(["api_key_id", "api_private_key"])

    # DELETE clears
    assert client.delete("/api/credentials/kalshi").status_code == 200
    assert client.get("/api/credentials/kalshi").json()["configured"] is False
