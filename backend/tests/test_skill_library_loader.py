"""Tests for the skill_library loader."""

from pathlib import Path

import pytest

from kiwi.config.extensions_config import ExtensionsConfig, reset_extensions_config, set_extensions_config
from kiwi.skill_library.loader import get_skill_library_root_path, load_skill_library


def _write_skill(skill_dir: Path, name: str, description: str) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def _isolated_extensions_config(monkeypatch):
    """Each test starts with no extensions config (singleton + env var cleared) so
    default-enabled wins unless the test points DEER_FLOW_EXTENSIONS_CONFIG_PATH at a fixture file."""
    monkeypatch.delenv("DEER_FLOW_EXTENSIONS_CONFIG_PATH", raising=False)
    set_extensions_config(ExtensionsConfig())
    yield
    reset_extensions_config()


def test_get_skill_library_root_path_points_to_repo_root_skill_library():
    p = get_skill_library_root_path()
    assert p.name == "skill-library"
    assert (p.parent / "backend").is_dir()


def test_load_returns_empty_when_directory_missing(tmp_path: Path):
    result = load_skill_library(library_path=tmp_path / "nope", use_config=False)
    assert result == []


def test_load_discovers_flat_skills(tmp_path: Path):
    library = tmp_path / "skill-library"
    _write_skill(library / "alpha", "alpha", "First skill")
    _write_skill(library / "beta", "beta", "Second skill")

    skills = load_skill_library(library_path=library, use_config=False)
    by_name = {s.name: s for s in skills}

    assert set(by_name) == {"alpha", "beta"}
    assert by_name["alpha"].get_container_file_path() == "/mnt/skill-library/alpha/SKILL.md"
    assert by_name["beta"].get_container_file_path() == "/mnt/skill-library/beta/SKILL.md"
    assert by_name["alpha"].category == "library"


def test_load_uses_flat_layout_only_one_level(tmp_path: Path):
    """Nested SKILL.md files are NOT discovered — library is FLAT."""
    library = tmp_path / "skill-library"
    _write_skill(library / "ok", "ok", "Top-level skill")
    _write_skill(library / "parent" / "nested", "nested", "Nested skill (should be ignored)")

    skills = load_skill_library(library_path=library, use_config=False)
    names = {s.name for s in skills}
    assert "ok" in names
    assert "nested" not in names


def test_load_skips_hidden_directories(tmp_path: Path):
    library = tmp_path / "skill-library"
    _write_skill(library / "visible", "visible", "Should appear")
    _write_skill(library / ".hidden-skill", "hidden", "Should be skipped")

    skills = load_skill_library(library_path=library, use_config=False)
    assert {s.name for s in skills} == {"visible"}


def test_load_skips_malformed_skill(tmp_path: Path):
    library = tmp_path / "skill-library"
    _write_skill(library / "good", "good", "OK")
    bad_dir = library / "bad"
    bad_dir.mkdir()
    (bad_dir / "SKILL.md").write_text("no frontmatter here", encoding="utf-8")

    skills = load_skill_library(library_path=library, use_config=False)
    assert {s.name for s in skills} == {"good"}


def test_load_returns_skills_sorted_by_name(tmp_path: Path):
    library = tmp_path / "skill-library"
    _write_skill(library / "z-last", "z-last", "Z")
    _write_skill(library / "a-first", "a-first", "A")
    _write_skill(library / "m-mid", "m-mid", "M")

    skills = load_skill_library(library_path=library, use_config=False)
    assert [s.name for s in skills] == ["a-first", "m-mid", "z-last"]


def test_enabled_state_from_extensions_config(tmp_path: Path, monkeypatch):
    """Loader respects librarySkills enable state from extensions_config.json on disk."""
    library = tmp_path / "skill-library"
    _write_skill(library / "alpha", "alpha", "First")
    _write_skill(library / "beta", "beta", "Second")

    extensions = tmp_path / "extensions_config.json"
    import json as _json

    extensions.write_text(
        _json.dumps({"mcpServers": {}, "skills": {}, "librarySkills": {"alpha": {"enabled": False}}}),
        encoding="utf-8",
    )
    # Point the loader at our tmp extensions config (the loader calls from_file()
    # which respects DEER_FLOW_EXTENSIONS_CONFIG_PATH).
    monkeypatch.setenv("DEER_FLOW_EXTENSIONS_CONFIG_PATH", str(extensions))

    skills = load_skill_library(library_path=library, use_config=False, enabled_only=False)
    by_name = {s.name: s for s in skills}
    assert by_name["alpha"].enabled is False, "alpha should be disabled per extensions_config"
    assert by_name["beta"].enabled is True, "beta should default-enabled (not in config)"


def test_enabled_only_filter_drops_disabled(tmp_path: Path, monkeypatch):
    library = tmp_path / "skill-library"
    _write_skill(library / "alpha", "alpha", "First")
    _write_skill(library / "beta", "beta", "Second")

    extensions = tmp_path / "extensions_config.json"
    import json as _json

    extensions.write_text(
        _json.dumps({"mcpServers": {}, "skills": {}, "librarySkills": {"alpha": {"enabled": False}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEER_FLOW_EXTENSIONS_CONFIG_PATH", str(extensions))

    skills = load_skill_library(library_path=library, use_config=False, enabled_only=True)
    assert {s.name for s in skills} == {"beta"}


def test_load_handles_skill_directory_without_skill_md(tmp_path: Path):
    library = tmp_path / "skill-library"
    (library / "no-skill-md").mkdir(parents=True)
    (library / "no-skill-md" / "README.md").write_text("not a skill", encoding="utf-8")

    skills = load_skill_library(library_path=library, use_config=False)
    assert skills == []
