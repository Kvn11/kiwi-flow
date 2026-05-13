"""In-process dispatcher for skill tools.

A single LangChain tool (`invoke_skill_tool`) is bound to the agent. Each
skill ships a `handlers.py` next to its `SKILL.md` containing one or more
`@register_skill_tool`-decorated functions; the dispatcher routes calls to
them in-process, so credentials supplied by `kiwi.credentials.broker` never
leave Python memory.
"""

from .dispatcher import invoke_skill_tool
from .registry import (
    discover_handlers,
    get_handler,
    list_handlers,
    register_skill_tool,
    reset_for_tests,
)
from .types import Handler, SkillToolArgumentError, SkillToolKey

__all__ = [
    "invoke_skill_tool",
    "register_skill_tool",
    "discover_handlers",
    "get_handler",
    "list_handlers",
    "reset_for_tests",
    "Handler",
    "SkillToolArgumentError",
    "SkillToolKey",
]
