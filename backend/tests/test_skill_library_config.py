"""Tests for SkillLibraryConfig (parses path/container_path correctly,
defaults to repo-relative skill-library/)."""

from pathlib import Path

from deerflow.config.skill_library_config import SkillLibraryConfig


def test_defaults():
    cfg = SkillLibraryConfig()
    assert cfg.enabled is True
    assert cfg.path is None
    assert cfg.container_path == "/mnt/skill-library"


def test_disabled_via_field():
    cfg = SkillLibraryConfig(enabled=False)
    assert cfg.enabled is False


def test_get_path_uses_explicit_absolute_path(tmp_path: Path):
    target = tmp_path / "lib"
    target.mkdir()
    cfg = SkillLibraryConfig(path=str(target))
    assert cfg.get_path() == target.resolve()


def test_get_path_resolves_relative_to_repo_root():
    cfg = SkillLibraryConfig(path="some-relative-dir")
    resolved = cfg.get_path()
    # Repo root is the parent of the backend/ directory, four levels up from this test
    repo_root = Path(__file__).resolve().parents[2]
    assert resolved == (repo_root / "some-relative-dir").resolve()


def test_get_path_default_points_to_repo_root_skill_library():
    cfg = SkillLibraryConfig()
    p = cfg.get_path()
    assert p.name == "skill-library", f"Expected default to point at skill-library/, got {p}"
    # Sanity: the parent directory should contain the backend/ directory
    assert (p.parent / "backend").is_dir(), f"Expected default skill-library to be a sibling of backend/, got {p}"
