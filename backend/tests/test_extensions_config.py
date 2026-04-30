"""Tests for ExtensionsConfig — focused on the library_skills additions and
the model_dump round-trip used by the gateway routers."""

import json
from pathlib import Path

from kiwi.config.extensions_config import ExtensionsConfig, LibrarySkillStateConfig, SkillStateConfig


def test_is_library_skill_enabled_defaults_true_when_absent():
    cfg = ExtensionsConfig()
    assert cfg.is_library_skill_enabled("anything") is True


def test_is_library_skill_enabled_respects_explicit_false():
    cfg = ExtensionsConfig(library_skills={"foo": LibrarySkillStateConfig(enabled=False)})
    assert cfg.is_library_skill_enabled("foo") is False


def test_is_library_skill_enabled_respects_explicit_true():
    cfg = ExtensionsConfig(library_skills={"foo": LibrarySkillStateConfig(enabled=True)})
    assert cfg.is_library_skill_enabled("foo") is True


def test_library_skills_alias_round_trips():
    """librarySkills (camelCase) is the on-disk alias; library_skills is the python field."""
    cfg = ExtensionsConfig.model_validate({"librarySkills": {"a": {"enabled": False}}})
    assert cfg.is_library_skill_enabled("a") is False

    dumped = cfg.model_dump(by_alias=True, exclude_none=True)
    assert "librarySkills" in dumped
    assert dumped["librarySkills"] == {"a": {"enabled": False}}


def test_from_file_handles_missing_library_skills_section(tmp_path: Path):
    """Existing extensions_config.json files won't have librarySkills — that must default to {}."""
    config_file = tmp_path / "extensions_config.json"
    config_file.write_text(json.dumps({"mcpServers": {}, "skills": {"x": {"enabled": False}}}), encoding="utf-8")

    cfg = ExtensionsConfig.from_file(str(config_file))
    assert cfg.library_skills == {}
    assert cfg.is_library_skill_enabled("anything") is True
    # Existing skills section is preserved
    assert cfg.is_skill_enabled("x", "public") is False


def test_round_trip_preserves_unrelated_sections(tmp_path: Path):
    """Regression for the bug where update_skill rebuilt the config dict by hand and
    dropped librarySkills (or any other top-level field). Round-tripping via
    model_dump(by_alias=True) must keep all sections intact."""
    config_file = tmp_path / "extensions_config.json"
    config_file.write_text(
        json.dumps(
            {
                "mcpServers": {"server-a": {"enabled": True, "type": "stdio", "command": "echo"}},
                "skills": {"s1": {"enabled": True}},
                "librarySkills": {"lib1": {"enabled": False}},
            }
        ),
        encoding="utf-8",
    )
    cfg = ExtensionsConfig.from_file(str(config_file))

    # Mutate one section as a router would
    cfg.skills["s1"] = SkillStateConfig(enabled=False)

    # Write back via model_dump
    dumped = cfg.model_dump(by_alias=True, exclude_none=True)
    config_file.write_text(json.dumps(dumped), encoding="utf-8")

    reloaded = ExtensionsConfig.from_file(str(config_file))
    assert reloaded.is_skill_enabled("s1", "public") is False
    assert reloaded.is_library_skill_enabled("lib1") is False
    assert "server-a" in reloaded.mcp_servers
