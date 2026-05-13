"""Public types for the kiwi.skill_dispatch package."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# A skill tool is uniquely identified by (skill_name, tool_name).
SkillToolKey = tuple[str, str]

# Handlers take an opaque args dict and return an LLM-visible string.
# Validation of args' shape is each handler's responsibility — the dispatcher
# only enforces that args is a dict.
Handler = Callable[[dict[str, Any]], str]


class SkillToolArgumentError(ValueError):
    """Raised by a handler when the caller-supplied args dict is malformed.

    Subclasses ValueError so handlers can keep the natural `raise ValueError(...)`
    pattern, but the dedicated class lets the dispatcher distinguish arg-shape
    errors from deep-stack ValueErrors (e.g., int('abc'), float parse failures
    on upstream data) that should NOT be reported back to the LLM as 'rejected
    arguments'. Plain ValueError from a handler now lands in the generic-exception
    branch.
    """
