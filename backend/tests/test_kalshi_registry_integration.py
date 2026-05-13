"""End-to-end regression: `skill-library/kalshi/SKILL.md` is parsed by the registry.

Without this test, an accidental edit that breaks the Kalshi credentials block
(typo, wrong indent, missing field) would silently disappear from the Settings
UI without any test catching it.
"""

from __future__ import annotations

import pytest

from kiwi.credentials import parse_skill_credentials
from kiwi.credentials.registry import build_credential_registry
from kiwi.skill_library.loader import get_skill_library_root_path

SKILL_NAME = "kalshi"


@pytest.fixture(autouse=True)
def _isolate_registry():
    from kiwi.credentials import registry as registry_module

    registry_module.reset_credential_registry()
    yield
    registry_module.reset_credential_registry()


def test_kalshi_skill_md_declares_expected_fields() -> None:
    """The on-disk SKILL.md should parse into a schema with exactly the two declared fields."""
    skill_file = get_skill_library_root_path() / "kalshi" / "SKILL.md"
    assert skill_file.is_file(), f"Expected {skill_file} to exist"

    schema = parse_skill_credentials(skill_file)
    assert schema is not None, "Kalshi SKILL.md must declare a `credentials:` block"
    assert schema.skill_name == SKILL_NAME

    field_names = schema.field_names()
    assert "api_key_id" in field_names
    assert "api_private_key" in field_names

    by_name = {f.name: f for f in schema.fields}
    assert by_name["api_key_id"].type == "text"
    assert by_name["api_private_key"].type == "textarea"


def test_kalshi_appears_in_built_registry() -> None:
    """A full registry scan (skills/public + skills/custom + skill-library) should include kalshi."""
    registry = build_credential_registry()
    assert SKILL_NAME in registry, f"Kalshi schema not found in registry. Known schemas: {sorted(registry.list().keys())}"
    schema = registry.get(SKILL_NAME)
    assert schema is not None
    assert sorted(schema.field_names()) == ["api_key_id", "api_private_key"]
