"""The single LangChain tool that fans out to every registered skill tool."""

from __future__ import annotations

import logging
from typing import Any

from langchain.tools import tool

from kiwi.credentials import CredentialError, format_credential_error

from .registry import get_handler
from .types import SkillToolArgumentError

logger = logging.getLogger(__name__)


def _is_skill_enabled(skill_name: str) -> bool:
    """Return True if the skill is enabled in extensions config (or unknown).

    Unknown skills (no SKILL.md found) default to enabled — they may be
    test-only skills registered programmatically without going through the loader.
    """
    try:
        from kiwi.skills.loader import load_skills

        for skill in load_skills(enabled_only=False):
            if skill.name == skill_name:
                return skill.enabled
    except Exception:
        logger.debug("load_skills failed during enabled-skill check", exc_info=True)
    try:
        from kiwi.skill_library.loader import load_skill_library

        for skill in load_skill_library(enabled_only=False):
            if skill.name == skill_name:
                return skill.enabled
    except Exception:
        logger.debug("load_skill_library failed during enabled-skill check", exc_info=True)
    return True


@tool("invoke_skill_tool", parse_docstring=True)
def invoke_skill_tool(skill: str, tool: str, args: dict[str, Any] | None = None) -> str:
    """Invoke a tool offered by a skill.

    Use this after discovering a skill via skill_search and reading its SKILL.md
    to learn what tools that skill exposes and what arguments each tool takes.

    The skill's SKILL.md is the source of truth for the available tool names and
    the shape of `args`. If you call this with an unknown skill or tool name,
    the result will be an error string telling you so.

    Args:
        skill: The skill's name (e.g., "kalshi"), exactly as it appears in the skill's SKILL.md frontmatter.
        tool: The skill-tool name as documented in the skill's SKILL.md (e.g., "account").
        args: Arguments specific to this tool, with shapes documented in the skill's SKILL.md. Pass an empty dict {} if the tool takes no arguments.
    """
    return dispatch_skill_tool(skill, tool, args)


def dispatch_skill_tool(skill: str, tool_name: str, args: dict[str, Any] | None) -> str:
    """Pure dispatch implementation — exposed without the @tool wrapper for tests."""
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return f"Skill tool args must be a dict, got {type(args).__name__}."

    handler = get_handler(skill, tool_name)
    if handler is None:
        return f"No skill tool '{tool_name}' is registered on skill '{skill}'."

    if not _is_skill_enabled(skill):
        return f"Skill '{skill}' is currently disabled. Enable it in Settings → Skills before invoking '{tool_name}'."

    # Pass a copy so a buggy handler can't mutate caller-owned tool input
    # (LangGraph may still hold the original dict for tracing/logging).
    try:
        result = handler(dict(args))
    except CredentialError as exc:
        return format_credential_error(skill, exc)
    except SkillToolArgumentError as exc:
        return f"Skill tool '{skill}.{tool_name}' rejected arguments: {exc}"
    except Exception as exc:
        logger.exception("Skill tool '%s.%s' raised", skill, tool_name)
        return f"Skill tool '{skill}.{tool_name}' failed: {exc.__class__.__name__}: {exc}"

    if not isinstance(result, str):
        logger.warning(
            "Skill tool '%s.%s' returned %s; coercing to str",
            skill,
            tool_name,
            type(result).__name__,
        )
        return str(result)
    return result
