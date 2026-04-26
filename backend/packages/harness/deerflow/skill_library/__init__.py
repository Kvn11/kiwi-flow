"""On-demand skill library — discoverable via skill_search at runtime.

Library skills are NOT injected into the system prompt. The agent searches
for them via the skill_search tool, then read_files the matched SKILL.md
to load the workflow on demand. Mirrors the deferred-tool pattern in
deerflow.tools.builtins.tool_search.
"""

from deerflow.skill_library.loader import get_skill_library_root_path, load_skill_library
from deerflow.skill_library.registry import (
    SkillLibraryRegistry,
    get_library_registry,
    reset_library_registry,
)
from deerflow.skill_library.types import LibrarySkill

__all__ = [
    "LibrarySkill",
    "SkillLibraryRegistry",
    "get_library_registry",
    "get_skill_library_root_path",
    "load_skill_library",
    "reset_library_registry",
]
