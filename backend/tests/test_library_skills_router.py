"""Tests for the /api/library-skills router."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.routers import library_skills as router_module
from deerflow.config.extensions_config import (
    ExtensionsConfig,
    reset_extensions_config,
    set_extensions_config,
)
from deerflow.skill_library.registry import reset_library_registry


def _skill_content(name: str, description: str = "Demo library skill") -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n"


@pytest.fixture(autouse=True)
def _isolate_state():
    reset_library_registry()
    set_extensions_config(ExtensionsConfig())
    yield
    reset_library_registry()
    reset_extensions_config()


@pytest.fixture
def populated_library(tmp_path: Path, monkeypatch):
    library_root = tmp_path / "skill-library"
    (library_root / "alpha").mkdir(parents=True)
    (library_root / "alpha" / "SKILL.md").write_text(_skill_content("alpha", "First library skill"), encoding="utf-8")
    (library_root / "beta").mkdir(parents=True)
    (library_root / "beta" / "SKILL.md").write_text(_skill_content("beta", "Second library skill"), encoding="utf-8")

    config = SimpleNamespace(
        skill_library=SimpleNamespace(
            enabled=True,
            get_path=lambda: library_root,
            container_path="/mnt/skill-library",
        )
    )
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)
    return library_root


def _client(extensions_path: Path) -> TestClient:
    """Build a test client and patch the router to use a tmp extensions_config.json."""

    def _resolve(path: str | None = None) -> Path:
        if path is not None:
            return Path(path)
        return extensions_path

    app = FastAPI()
    app.include_router(router_module.router)
    # Patch resolve_config_path so the router writes into our tmp file.
    router_module.ExtensionsConfig.resolve_config_path = classmethod(lambda cls, path=None: _resolve(path))
    return TestClient(app)


def test_list_returns_all_library_skills(populated_library, tmp_path: Path):
    extensions = tmp_path / "extensions_config.json"
    extensions.write_text(json.dumps({"librarySkills": {}, "skills": {}, "mcpServers": {}}), encoding="utf-8")

    with _client(extensions) as client:
        resp = client.get("/api/library-skills")
        assert resp.status_code == 200
        data = resp.json()
        names = sorted(s["name"] for s in data["skills"])
        assert names == ["alpha", "beta"]
        for skill in data["skills"]:
            assert skill["enabled"] is True
            assert skill["path"].startswith("/mnt/skill-library/")
            assert skill["path"].endswith("/SKILL.md")


def test_get_returns_404_for_unknown(populated_library, tmp_path: Path):
    extensions = tmp_path / "extensions_config.json"
    extensions.write_text(json.dumps({"librarySkills": {}, "skills": {}, "mcpServers": {}}), encoding="utf-8")

    with _client(extensions) as client:
        resp = client.get("/api/library-skills/does-not-exist")
        assert resp.status_code == 404


def test_get_returns_skill_details(populated_library, tmp_path: Path):
    extensions = tmp_path / "extensions_config.json"
    extensions.write_text(json.dumps({"librarySkills": {}, "skills": {}, "mcpServers": {}}), encoding="utf-8")

    with _client(extensions) as client:
        resp = client.get("/api/library-skills/alpha")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "alpha"
        assert data["description"] == "First library skill"
        assert data["path"] == "/mnt/skill-library/alpha/SKILL.md"


def test_put_persists_disabled_state(populated_library, tmp_path: Path):
    extensions = tmp_path / "extensions_config.json"
    extensions.write_text(
        json.dumps({"mcpServers": {}, "skills": {"unrelated": {"enabled": True}}, "librarySkills": {}}),
        encoding="utf-8",
    )

    with _client(extensions) as client:
        resp = client.put("/api/library-skills/alpha", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    written = json.loads(extensions.read_text(encoding="utf-8"))
    assert written["librarySkills"]["alpha"]["enabled"] is False
    # Crucial regression: unrelated sections must be preserved.
    assert written["skills"]["unrelated"]["enabled"] is True
    assert "mcpServers" in written


def test_put_404_for_unknown_skill(populated_library, tmp_path: Path):
    extensions = tmp_path / "extensions_config.json"
    extensions.write_text(json.dumps({"librarySkills": {}, "skills": {}, "mcpServers": {}}), encoding="utf-8")

    with _client(extensions) as client:
        resp = client.put("/api/library-skills/missing", json={"enabled": False})
        assert resp.status_code == 404


def test_put_resets_registry_cache(populated_library, tmp_path: Path, monkeypatch):
    extensions = tmp_path / "extensions_config.json"
    extensions.write_text(json.dumps({"librarySkills": {}, "skills": {}, "mcpServers": {}}), encoding="utf-8")

    reset_calls = {"count": 0}

    def _reset() -> None:
        reset_calls["count"] += 1

    monkeypatch.setattr("app.gateway.routers.library_skills.reset_library_registry", _reset)

    with _client(extensions) as client:
        client.put("/api/library-skills/alpha", json={"enabled": False})

    assert reset_calls["count"] == 1
