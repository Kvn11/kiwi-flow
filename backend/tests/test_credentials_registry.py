"""Tests for `kiwi.credentials.registry.CredentialRegistry`.

The registry walks every skill source (skills/public, skills/custom, skill-library)
and parses each SKILL.md's `credentials:` block. We monkeypatch the loader-side
helpers so the test doesn't depend on real on-disk skills.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from kiwi.credentials import (
    CredentialField,
    CredentialSchema,
    get_credential_registry,
    reload_credential_registry,
)
from kiwi.credentials import registry as registry_module


@dataclass
class _StubSkill:
    name: str
    skill_file: Path


def _make_skill(tmp_path: Path, sub: str, name: str, frontmatter: str) -> _StubSkill:
    skill_dir = tmp_path / sub / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(f"---\n{frontmatter}\n---\nbody\n", encoding="utf-8")
    return _StubSkill(name=name, skill_file=skill_file)


@pytest.fixture(autouse=True)
def _reset_registry_cache():
    registry_module.reset_credential_registry()
    yield
    registry_module.reset_credential_registry()


def test_registry_aggregates_all_three_skill_roots(monkeypatch, tmp_path: Path) -> None:
    public_skill = _make_skill(
        tmp_path,
        "public",
        "kalshi",
        "name: kalshi\ndescription: Trade markets\ncredentials:\n  fields:\n    - { name: api_key, label: 'Key' }",
    )
    custom_skill = _make_skill(
        tmp_path,
        "custom",
        "myservice",
        "name: myservice\ndescription: Custom\ncredentials:\n  fields:\n    - { name: token, label: 'Token' }",
    )
    library_skill = _make_skill(
        tmp_path,
        "library",
        "datafeed",
        "name: datafeed\ndescription: Data\ncredentials:\n  fields:\n    - { name: feed_key, label: 'Feed Key' }",
    )

    monkeypatch.setattr(
        "kiwi.skills.loader.load_skills",
        lambda enabled_only=False: [public_skill, custom_skill],
    )
    monkeypatch.setattr(
        "kiwi.skill_library.loader.load_skill_library",
        lambda enabled_only=False: [library_skill],
    )

    reg = reload_credential_registry()

    assert reg.list() == {
        "kalshi": CredentialSchema(
            skill_name="kalshi",
            fields=(CredentialField(name="api_key", label="Key", type="text"),),
        ),
        "myservice": CredentialSchema(
            skill_name="myservice",
            fields=(CredentialField(name="token", label="Token", type="text"),),
        ),
        "datafeed": CredentialSchema(
            skill_name="datafeed",
            fields=(CredentialField(name="feed_key", label="Feed Key", type="text"),),
        ),
    }


def test_skills_without_credentials_block_are_omitted(monkeypatch, tmp_path: Path) -> None:
    skill_with = _make_skill(
        tmp_path,
        "public",
        "needs_creds",
        "name: needs_creds\ndescription: Has creds\ncredentials:\n  fields:\n    - { name: x, label: 'X' }",
    )
    skill_without = _make_skill(
        tmp_path,
        "public",
        "no_creds",
        "name: no_creds\ndescription: No creds",
    )

    monkeypatch.setattr(
        "kiwi.skills.loader.load_skills",
        lambda enabled_only=False: [skill_with, skill_without],
    )
    monkeypatch.setattr("kiwi.skill_library.loader.load_skill_library", lambda enabled_only=False: [])

    reg = reload_credential_registry()
    assert "needs_creds" in reg
    assert "no_creds" not in reg


def test_get_returns_none_for_unknown_skill(monkeypatch) -> None:
    monkeypatch.setattr("kiwi.skills.loader.load_skills", lambda enabled_only=False: [])
    monkeypatch.setattr("kiwi.skill_library.loader.load_skill_library", lambda enabled_only=False: [])

    reg = reload_credential_registry()
    assert reg.get("missing") is None


def test_get_credential_registry_caches_across_calls(monkeypatch, tmp_path: Path) -> None:
    skill = _make_skill(
        tmp_path,
        "public",
        "x",
        "name: x\ndescription: y\ncredentials:\n  fields:\n    - { name: k, label: 'K' }",
    )
    calls = {"n": 0}

    def fake_load(enabled_only=False):
        calls["n"] += 1
        return [skill]

    monkeypatch.setattr("kiwi.skills.loader.load_skills", fake_load)
    monkeypatch.setattr("kiwi.skill_library.loader.load_skill_library", lambda enabled_only=False: [])

    get_credential_registry()
    get_credential_registry()
    get_credential_registry()

    assert calls["n"] == 1, "Registry should be built only once until reload is called"


def test_reload_rebuilds_from_disk(monkeypatch, tmp_path: Path) -> None:
    skill = _make_skill(
        tmp_path,
        "public",
        "x",
        "name: x\ndescription: y\ncredentials:\n  fields:\n    - { name: k, label: 'K' }",
    )
    monkeypatch.setattr("kiwi.skills.loader.load_skills", lambda enabled_only=False: [skill])
    monkeypatch.setattr("kiwi.skill_library.loader.load_skill_library", lambda enabled_only=False: [])

    reg1 = get_credential_registry()
    assert "x" in reg1

    # Edit the SKILL.md to add a second field, then reload.
    skill.skill_file.write_text(
        "---\nname: x\ndescription: y\ncredentials:\n  fields:\n    - { name: k, label: 'K' }\n    - { name: k2, label: 'K2' }\n---\nbody\n",
        encoding="utf-8",
    )

    reg2 = reload_credential_registry()
    schema = reg2.get("x")
    assert schema is not None
    assert schema.field_names() == ("k", "k2")


def test_loader_failures_are_swallowed(monkeypatch) -> None:
    def boom(enabled_only=False):
        raise RuntimeError("loader exploded")

    monkeypatch.setattr("kiwi.skills.loader.load_skills", boom)
    monkeypatch.setattr("kiwi.skill_library.loader.load_skill_library", lambda enabled_only=False: [])

    # Should not raise — registry stays empty.
    reg = reload_credential_registry()
    assert len(reg) == 0
