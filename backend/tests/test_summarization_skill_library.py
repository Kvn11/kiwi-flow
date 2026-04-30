"""Tests that DeerFlowSummarizationMiddleware also rescues skill_library reads."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage

from kiwi.agents.middlewares.summarization_middleware import DeerFlowSummarizationMiddleware


def _runtime() -> SimpleNamespace:
    return SimpleNamespace(context={"thread_id": "t-lib"})


def _middleware(
    *,
    skills_container_path: str = "/mnt/skills",
    skill_library_container_path: str = "/mnt/skill-library",
) -> DeerFlowSummarizationMiddleware:
    model = MagicMock()
    model.invoke.return_value = SimpleNamespace(text="compressed summary")
    return DeerFlowSummarizationMiddleware(
        model=model,
        trigger=("messages", 4),
        keep=("messages", 2),
        token_counter=len,
        skills_container_path=skills_container_path,
        skill_library_container_path=skill_library_container_path,
        preserve_recent_skill_count=5,
        preserve_recent_skill_tokens=10_000,
        preserve_recent_skill_tokens_per_skill=10_000,
    )


def _read_call(tool_id: str, path: str) -> dict:
    return {"name": "read_file", "id": tool_id, "args": {"path": path}}


def test_library_read_is_preserved_through_summarization() -> None:
    """A read_file('/mnt/skill-library/...') call should survive summarization just like /mnt/skills/."""
    middleware = _middleware()

    library_path = "/mnt/skill-library/pdf-extract/SKILL.md"
    library_body = "BODY: how to extract text from PDFs ..."
    messages = [
        HumanMessage(content="u1"),
        AIMessage(content="", tool_calls=[_read_call("t-lib", library_path)]),
        ToolMessage(content=library_body, tool_call_id="t-lib"),
        HumanMessage(content="u2"),
        AIMessage(content="ack"),
    ]

    result = middleware.before_model({"messages": messages}, _runtime())
    assert result is not None

    # The library SKILL.md ToolMessage should still be present in the rebuilt message list.
    rebuilt = [m for m in result["messages"] if not isinstance(m, RemoveMessage)]
    contents = [getattr(m, "content", "") for m in rebuilt]
    assert any(library_body in c for c in contents), f"library body was lost during summarization: {contents}"


def test_skills_and_library_reads_both_preserved_in_one_turn() -> None:
    """Both /mnt/skills and /mnt/skill-library reads should be rescued."""
    middleware = _middleware()

    messages = [
        HumanMessage(content="u1"),
        AIMessage(
            content="",
            tool_calls=[
                _read_call("t-skill", "/mnt/skills/public/alpha/SKILL.md"),
                _read_call("t-lib", "/mnt/skill-library/beta/SKILL.md"),
            ],
        ),
        ToolMessage(content="ALPHA-BODY", tool_call_id="t-skill"),
        ToolMessage(content="BETA-BODY", tool_call_id="t-lib"),
        HumanMessage(content="u2"),
        AIMessage(content="ack"),
    ]

    result = middleware.before_model({"messages": messages}, _runtime())
    assert result is not None
    contents = [getattr(m, "content", "") for m in result["messages"] if not isinstance(m, RemoveMessage)]
    joined = " ".join(contents)
    assert "ALPHA-BODY" in joined
    assert "BETA-BODY" in joined
