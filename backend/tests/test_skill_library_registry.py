"""Tests for SkillLibraryRegistry — search query forms and ranking."""

from pathlib import Path

import pytest

from deerflow.skill_library.registry import (
    MAX_RESULTS,
    SkillLibraryRegistry,
    reset_library_registry,
)
from deerflow.skill_library.types import LibrarySkill


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


@pytest.fixture
def sample_registry() -> SkillLibraryRegistry:
    return SkillLibraryRegistry(
        [
            _make_skill("pdf-extract", "Extract text and tables from PDF documents"),
            _make_skill("chart-viz", "Visualize datasets as charts and plots"),
            _make_skill("academic-paper-review", "Review and critique academic papers"),
            _make_skill("data-cleaner", "Clean tabular data and detect outliers"),
            _make_skill("transcribe-audio", "Transcribe audio files to text"),
            _make_skill("summarize-long-doc", "Summarize long documents"),
        ]
    )


def test_select_form_returns_exact_matches(sample_registry):
    results = sample_registry.search("select:pdf-extract,chart-viz")
    assert {e.name for e in results} == {"pdf-extract", "chart-viz"}


def test_select_form_unknown_names_return_nothing(sample_registry):
    results = sample_registry.search("select:does-not-exist")
    assert results == []


def test_plus_keyword_form_requires_substring(sample_registry):
    results = sample_registry.search("+chart")
    assert [e.name for e in results] == ["chart-viz"]


def test_plus_keyword_form_ranks_remaining(sample_registry):
    # Both data-cleaner and chart-viz mention "data" in their descriptions, but only
    # data-cleaner has "data" in the name, so +data should pull data-cleaner first.
    results = sample_registry.search("+data outliers")
    assert results[0].name == "data-cleaner"


def test_regex_search_matches_name_and_description(sample_registry):
    results = sample_registry.search("paper")
    assert "academic-paper-review" in {e.name for e in results}


def test_regex_search_name_outscores_description(sample_registry):
    """A name match should rank above a description-only match for the same query."""
    registry = SkillLibraryRegistry(
        [
            _make_skill("docs-finder", "Search arbitrary documents"),
            _make_skill("misc", "Helper for working with docs"),
        ]
    )
    results = registry.search("docs")
    assert results[0].name == "docs-finder"


def test_invalid_regex_falls_back_to_literal(sample_registry):
    # Unbalanced bracket should not raise — the registry should fall back to literal.
    results = sample_registry.search("pdf[")
    # The literal "pdf[" matches nothing, so empty result is expected.
    assert results == []


def test_empty_query_returns_nothing(sample_registry):
    assert sample_registry.search("") == []
    assert sample_registry.search("   ") == []


def test_max_results_clamp():
    big = SkillLibraryRegistry([_make_skill(f"skill-{i}", "common description text") for i in range(50)])
    results = big.search("common")
    assert len(results) == MAX_RESULTS


def test_container_path_uses_configured_base():
    registry = SkillLibraryRegistry(
        [_make_skill("only", "lonely skill")],
        container_base_path="/custom/mount",
    )
    results = registry.search("only")
    assert results[0].container_path == "/custom/mount/only/SKILL.md"
