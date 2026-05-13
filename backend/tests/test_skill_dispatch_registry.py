"""Tests for kiwi.skill_dispatch.registry."""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path

import pytest

from kiwi.skill_dispatch import register_skill_tool, reset_for_tests
from kiwi.skill_dispatch.registry import (
    _import_handlers_file,
    discover_handlers,
    get_handler,
    list_handlers,
)


@pytest.fixture(autouse=True)
def _isolate_registry():
    reset_for_tests()
    yield
    reset_for_tests()


def test_register_inserts_handler_into_lookup() -> None:
    @register_skill_tool(skill="kalshi", tool="account")
    def my_handler(args: dict) -> str:
        return "ok"

    assert get_handler("kalshi", "account") is my_handler
    assert ("kalshi", "account") in list_handlers()


def test_register_returns_original_function() -> None:
    """Decorator does not wrap; the original function is callable directly."""

    def handler(args: dict) -> str:
        return f"called with {args}"

    decorated = register_skill_tool(skill="x", tool="y")(handler)
    assert decorated is handler


def test_register_replaces_existing_key(caplog) -> None:
    @register_skill_tool(skill="kalshi", tool="account")
    def first_handler(args: dict) -> str:
        return "first"

    @register_skill_tool(skill="kalshi", tool="account")
    def second_handler(args: dict) -> str:
        return "second"

    assert get_handler("kalshi", "account") is second_handler
    # A warning was emitted
    assert any("Replacing existing" in rec.message for rec in caplog.records)


def test_get_handler_returns_none_for_unknown_key() -> None:
    assert get_handler("nonexistent", "anything") is None


def test_reset_for_tests_clears_all() -> None:
    @register_skill_tool(skill="a", tool="b")
    def h(args: dict) -> str:
        return "x"

    assert len(list_handlers()) == 1
    reset_for_tests()
    assert list_handlers() == {}


# ── discover_handlers + _import_handlers_file ─────────────────────────


@dataclass
class _StubSkill:
    name: str
    skill_file: Path


def _make_skill_with_handlers(tmp_path: Path, name: str, handler_body: str) -> _StubSkill:
    skill_dir = tmp_path / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n", encoding="utf-8")
    (skill_dir / "handlers.py").write_text(textwrap.dedent(handler_body), encoding="utf-8")
    return _StubSkill(name=name, skill_file=skill_dir / "SKILL.md")


def test_import_handlers_file_runs_decorators(tmp_path: Path) -> None:
    skill = _make_skill_with_handlers(
        tmp_path,
        "alpha",
        """
        from kiwi.skill_dispatch import register_skill_tool

        @register_skill_tool(skill="alpha", tool="ping")
        def ping(args):
            return "pong"
        """,
    )

    ok = _import_handlers_file(skill.skill_file.parent / "handlers.py")
    assert ok is True
    h = get_handler("alpha", "ping")
    assert h is not None
    assert h({}) == "pong"


def test_import_handlers_file_swallows_errors(tmp_path: Path, caplog) -> None:
    skill_dir = tmp_path / "broken"
    skill_dir.mkdir()
    (skill_dir / "handlers.py").write_text("this is not valid python ;;\n", encoding="utf-8")

    ok = _import_handlers_file(skill_dir / "handlers.py")
    assert ok is False
    assert any("Failed to import handlers" in rec.message for rec in caplog.records)


def test_relative_imports_inside_handlers_resolve_against_skill_dir(tmp_path: Path) -> None:
    """A handlers.py can `from .lib import ...` to pull from a sibling file."""
    skill_dir = tmp_path / "relative_imports"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: relative_imports\ndescription: x\n---\n", encoding="utf-8")
    (skill_dir / "lib.py").write_text("def double(n): return n * 2\n", encoding="utf-8")
    (skill_dir / "handlers.py").write_text(
        textwrap.dedent(
            """
            from kiwi.skill_dispatch import register_skill_tool
            from .lib import double

            @register_skill_tool(skill="relative_imports", tool="double")
            def handler(args):
                return str(double(args["n"]))
            """
        ),
        encoding="utf-8",
    )

    ok = _import_handlers_file(skill_dir / "handlers.py")
    assert ok is True
    assert get_handler("relative_imports", "double")({"n": 7}) == "14"


def test_discover_handlers_walks_all_skill_sources(tmp_path: Path, monkeypatch) -> None:
    a = _make_skill_with_handlers(
        tmp_path,
        "a",
        """
        from kiwi.skill_dispatch import register_skill_tool
        @register_skill_tool(skill="a", tool="t")
        def f(args): return "a-result"
        """,
    )
    b = _make_skill_with_handlers(
        tmp_path,
        "b",
        """
        from kiwi.skill_dispatch import register_skill_tool
        @register_skill_tool(skill="b", tool="t")
        def f(args): return "b-result"
        """,
    )
    no_handlers = tmp_path / "no_handlers"
    no_handlers.mkdir()
    (no_handlers / "SKILL.md").write_text("---\nname: no_handlers\ndescription: x\n---\n", encoding="utf-8")
    no_handlers_skill = _StubSkill(name="no_handlers", skill_file=no_handlers / "SKILL.md")

    monkeypatch.setattr(
        "kiwi.skills.loader.load_skills",
        lambda enabled_only=False: [a, no_handlers_skill],
    )
    monkeypatch.setattr(
        "kiwi.skill_library.loader.load_skill_library",
        lambda enabled_only=False: [b],
    )

    discover_handlers()
    assert get_handler("a", "t")({}) == "a-result"
    assert get_handler("b", "t")({}) == "b-result"
    # Only handlers.py-bearing skills register; doc-only skills are silently skipped.
    assert {("a", "t"), ("b", "t")} == set(list_handlers().keys())


def test_discover_handlers_continues_after_one_skill_fails(tmp_path: Path, monkeypatch) -> None:
    good = _make_skill_with_handlers(
        tmp_path,
        "good",
        """
        from kiwi.skill_dispatch import register_skill_tool
        @register_skill_tool(skill="good", tool="t")
        def f(args): return "ok"
        """,
    )
    broken_dir = tmp_path / "broken"
    broken_dir.mkdir()
    (broken_dir / "SKILL.md").write_text("---\nname: broken\ndescription: x\n---\n", encoding="utf-8")
    (broken_dir / "handlers.py").write_text("import nonexistent_module_xyz\n", encoding="utf-8")
    broken_skill = _StubSkill(name="broken", skill_file=broken_dir / "SKILL.md")

    monkeypatch.setattr(
        "kiwi.skills.loader.load_skills",
        lambda enabled_only=False: [good, broken_skill],
    )
    monkeypatch.setattr(
        "kiwi.skill_library.loader.load_skill_library",
        lambda enabled_only=False: [],
    )

    discover_handlers()
    assert get_handler("good", "t") is not None
    assert get_handler("broken", "t") is None


def test_discover_handlers_is_cached(tmp_path: Path, monkeypatch) -> None:
    """Second call short-circuits without rescanning skill sources."""
    skill = _make_skill_with_handlers(
        tmp_path,
        "cached",
        """
        from kiwi.skill_dispatch import register_skill_tool
        @register_skill_tool(skill="cached", tool="t")
        def f(args): return "cached-result"
        """,
    )

    calls = {"public": 0, "library": 0}

    def fake_load_skills(enabled_only: bool = False):
        calls["public"] += 1
        return [skill]

    def fake_load_skill_library(enabled_only: bool = False):
        calls["library"] += 1
        return []

    monkeypatch.setattr("kiwi.skills.loader.load_skills", fake_load_skills)
    monkeypatch.setattr("kiwi.skill_library.loader.load_skill_library", fake_load_skill_library)

    discover_handlers()
    discover_handlers()
    discover_handlers()
    assert calls == {"public": 1, "library": 1}

    discover_handlers(force=True)
    assert calls == {"public": 2, "library": 2}
