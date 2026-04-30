"""Searchable registry for the on-demand skill library.

Mirrors the deferred-tool pattern in kiwi.tools.builtins.tool_search:
the agent supplies a query (regex / select / +keyword) and gets back a
ranked list of matches. Library skills are file-backed, not LangChain
tools, so there is no `promote()` step — the next agent action after a
search hit is `read_file(container_path)`.

The registry is process-global with mtime-based invalidation. Library
data is identical across requests, so per-request ContextVar isolation
(needed for deferred tools because MCP tool inventories vary per request)
is unnecessary here.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from kiwi.skill_library.loader import load_skill_library
from kiwi.skill_library.types import LibrarySkill

logger = logging.getLogger(__name__)

MAX_RESULTS = 5


@dataclass
class LibrarySkillEntry:
    """One searchable record in the registry."""

    name: str
    description: str
    container_path: str  # Full /mnt/skill-library/<name>/SKILL.md
    skill: LibrarySkill


class SkillLibraryRegistry:
    """Holds library skills and answers regex/keyword/select queries."""

    def __init__(self, skills: list[LibrarySkill], container_base_path: str = "/mnt/skill-library") -> None:
        self._entries: list[LibrarySkillEntry] = [
            LibrarySkillEntry(
                name=s.name,
                description=s.description,
                container_path=s.get_container_file_path(container_base_path),
                skill=s,
            )
            for s in skills
        ]

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def entries(self) -> list[LibrarySkillEntry]:
        return list(self._entries)

    @property
    def names(self) -> list[str]:
        return [e.name for e in self._entries]

    def search(self, query: str, max_results: int = MAX_RESULTS) -> list[LibrarySkillEntry]:
        """Search entries by query. Three forms (mirroring tool_search):

        - "select:name1,name2" — exact name match
        - "+keyword rest"      — require keyword in name, rank by rest
        - regex / keyword      — case-insensitive match against "name description";
                                  name hits outscore description hits.
        """
        query = (query or "").strip()
        if not query:
            return []

        if query.startswith("select:"):
            wanted = {n.strip() for n in query[len("select:") :].split(",") if n.strip()}
            return [e for e in self._entries if e.name in wanted][:max_results]

        if query.startswith("+"):
            parts = query[1:].split(None, 1)
            if not parts:
                return []
            required = parts[0].lower()
            candidates = [e for e in self._entries if required in e.name.lower()]
            if len(parts) > 1:
                candidates.sort(key=lambda e: _regex_score(parts[1], e), reverse=True)
            return candidates[:max_results]

        try:
            regex = re.compile(query, re.IGNORECASE)
        except re.error:
            regex = re.compile(re.escape(query), re.IGNORECASE)

        scored: list[tuple[int, LibrarySkillEntry]] = []
        for entry in self._entries:
            searchable = f"{entry.name} {entry.description}"
            if regex.search(searchable):
                score = 2 if regex.search(entry.name) else 1
                scored.append((score, entry))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [entry for _, entry in scored][:max_results]


def _regex_score(pattern: str, entry: LibrarySkillEntry) -> int:
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        regex = re.compile(re.escape(pattern), re.IGNORECASE)
    return len(regex.findall(f"{entry.name} {entry.description}"))


# ── Module-global cache with mtime-based invalidation ──

_registry: SkillLibraryRegistry | None = None
_registry_signature: tuple | None = None


def _signature(library_path: Path, container_base_path: str) -> tuple:
    """Build a cache key from inputs that affect registry contents."""
    library_mtime = _safe_mtime(library_path)
    extensions_path = _resolve_extensions_path()
    extensions_mtime = _safe_mtime(extensions_path) if extensions_path else None
    return (str(library_path), library_mtime, str(extensions_path), extensions_mtime, container_base_path)


def _safe_mtime(path: Path | None) -> float | None:
    if path is None:
        return None
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _resolve_extensions_path() -> Path | None:
    try:
        from kiwi.config.extensions_config import ExtensionsConfig

        return ExtensionsConfig.resolve_config_path()
    except Exception:
        return None


def get_library_registry() -> SkillLibraryRegistry | None:
    """Return the cached registry, rebuilding if library or extensions config changed.

    Returns None when the skill library is disabled in config or empty on disk.
    """
    global _registry, _registry_signature

    try:
        from kiwi.config import get_app_config

        config = get_app_config()
        library_config = config.skill_library
    except Exception as e:
        logger.warning("Failed to load app config for skill library: %s", e)
        return None

    if not library_config.enabled:
        return None

    library_path = library_config.get_path()
    container_base_path = library_config.container_path
    signature = _signature(library_path, container_base_path)

    if _registry is not None and _registry_signature == signature:
        return _registry if len(_registry) > 0 else None

    skills = load_skill_library(library_path=library_path, use_config=False, enabled_only=True)
    _registry = SkillLibraryRegistry(skills, container_base_path=container_base_path)
    _registry_signature = signature

    return _registry if len(_registry) > 0 else None


def reset_library_registry() -> None:
    """Drop the cached registry — used by tests and after gateway-driven toggles."""
    global _registry, _registry_signature
    _registry = None
    _registry_signature = None
