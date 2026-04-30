"""Tests for the skill_search LangChain tool — return shape and degenerate cases."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from kiwi.skill_library.registry import (
    SkillLibraryRegistry,
    reset_library_registry,
)
from kiwi.skill_library.types import LibrarySkill
from kiwi.tools.builtins.skill_search import skill_search


def _make_skill(name: str, description: str) -> LibrarySkill:
    skill_dir = Path(f"/tmp/{name}")
    return LibrarySkill(
        name=name,
        description=description,
        license=None,
        skill_dir=skill_dir,
        skill_file=skill_dir / "SKILL.md",
        relative_path=Path(name),
        category="library",
        enabled=True,
    )


@pytest.fixture(autouse=True)
def _reset():
    reset_library_registry()
    yield
    reset_library_registry()


def _invoke(query: str) -> str:
    return skill_search.invoke({"query": query})


def test_returns_message_when_no_registry():
    with patch("kiwi.tools.builtins.skill_search.get_library_registry", return_value=None):
        assert _invoke("anything") == "No skill library available."


def test_returns_message_when_registry_empty():
    empty = SkillLibraryRegistry([])
    with patch("kiwi.tools.builtins.skill_search.get_library_registry", return_value=empty):
        assert _invoke("anything") == "No skill library available."


def test_returns_no_match_message_when_no_results():
    registry = SkillLibraryRegistry([_make_skill("alpha", "First")])
    with patch("kiwi.tools.builtins.skill_search.get_library_registry", return_value=registry):
        assert _invoke("zzzzz") == "No skills found matching: zzzzz"


def test_returns_json_array_with_name_description_path():
    registry = SkillLibraryRegistry(
        [
            _make_skill("pdf-extract", "Extract text from PDFs"),
            _make_skill("chart-viz", "Visualize charts"),
        ]
    )
    with patch("kiwi.tools.builtins.skill_search.get_library_registry", return_value=registry):
        raw = _invoke("pdf")

    parsed = json.loads(raw)
    assert isinstance(parsed, list)
    assert len(parsed) == 1
    assert parsed[0] == {
        "name": "pdf-extract",
        "description": "Extract text from PDFs",
        "path": "/mnt/skill-library/pdf-extract/SKILL.md",
    }


def test_select_form_supported():
    registry = SkillLibraryRegistry([_make_skill("alpha", "A"), _make_skill("beta", "B")])
    with patch("kiwi.tools.builtins.skill_search.get_library_registry", return_value=registry):
        raw = _invoke("select:beta")
    parsed = json.loads(raw)
    assert {entry["name"] for entry in parsed} == {"beta"}
