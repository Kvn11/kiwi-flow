"""Registry for in-process skill tools.

A skill ships a `handlers.py` next to its `SKILL.md`. Each handler is decorated
with `@register_skill_tool(skill="...", tool="...")`, which inserts it into the
process-global registry. At backend startup, `discover_handlers()` walks every
known skill source (public, custom, skill-library) and dynamically imports any
`handlers.py` it finds — the decorator runs at import time and populates the
registry.

A failed import for one skill is logged and skipped; the agent continues to
work, and other skills' handlers remain available.
"""

from __future__ import annotations

import hashlib
import importlib.util
import logging
import sys
import threading
from pathlib import Path

from .types import Handler, SkillToolKey

logger = logging.getLogger(__name__)

_registry: dict[SkillToolKey, Handler] = {}
_discovered: bool = False
_discovery_lock = threading.Lock()
_imported_module_names: set[str] = set()
_PARENT_PKG = "kiwi_skill_handlers"


def register_skill_tool(*, skill: str, tool: str):
    """Decorator: register a function as the handler for `(skill, tool)`.

    The decorator runs at module import time, so importing a skill's
    `handlers.py` is sufficient to make its tools available via the dispatcher.

    Re-registering an existing key replaces the previous handler (last write
    wins) — useful in tests, harmless in production where each handler is
    registered once.
    """

    def decorator(fn: Handler) -> Handler:
        key: SkillToolKey = (skill, tool)
        if key in _registry:
            logger.warning("Replacing existing skill tool handler for %s.%s", skill, tool)
        _registry[key] = fn
        return fn

    return decorator


def get_handler(skill: str, tool: str) -> Handler | None:
    return _registry.get((skill, tool))


def list_handlers() -> dict[SkillToolKey, Handler]:
    """Return a copy of the registry. Tests use this; production code should not."""
    return dict(_registry)


def reset_for_tests() -> None:
    """Drop every registered handler and synthetic module. Tests only."""
    global _discovered
    with _discovery_lock:
        _registry.clear()
        for module_name in _imported_module_names:
            sys.modules.pop(module_name, None)
        _imported_module_names.clear()
        _discovered = False


def discover_handlers(*, force: bool = False) -> None:
    """Scan skill sources for `handlers.py` and import each one.

    Cached and thread-safe: subsequent calls return immediately. Pass `force=True`
    to rescan (clears the previous synthetic-module entries first so re-imports
    re-execute decorators cleanly). Skills without a `handlers.py` are
    documentation-only and are skipped silently.
    """
    global _discovered
    with _discovery_lock:
        if _discovered and not force:
            return
        if force:
            for module_name in _imported_module_names:
                sys.modules.pop(module_name, None)
            _imported_module_names.clear()
        handler_files = _find_handlers_files()
        loaded = 0
        for handlers_file in handler_files:
            if _import_handlers_file(handlers_file):
                loaded += 1
        logger.info("Skill dispatch: imported %d/%d handlers files", loaded, len(handler_files))
        _discovered = True


def _find_handlers_files() -> list[Path]:
    """Return every `handlers.py` next to a `SKILL.md` across all skill sources."""
    from kiwi.skills.loader import iter_all_skill_files

    handler_files: list[Path] = []
    for skill_file in iter_all_skill_files():
        candidate = skill_file.parent / "handlers.py"
        if candidate.is_file():
            handler_files.append(candidate)
    return handler_files


def _import_handlers_file(path: Path) -> bool:
    """Dynamically import a handlers.py. Returns True on success.

    The module is registered under `kiwi_skill_handlers.<skill_dir_name>__<path_hash>`
    so two skills with the same directory name (e.g. one in `skills/custom/` and
    one in `skill-library/`) get distinct sys.modules entries, and so relative
    imports inside `handlers.py` (e.g. `from .kalshi_lib import ...`) resolve
    against the skill's own folder.
    """
    skill_dir = path.parent
    skill_name = skill_dir.name
    path_hash = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:10]
    module_name = f"{_PARENT_PKG}.{skill_name}__{path_hash}"

    if _PARENT_PKG not in sys.modules:
        # Synthesize an empty parent package so submodule names resolve cleanly.
        parent_spec = importlib.util.spec_from_loader(_PARENT_PKG, loader=None, is_package=True)
        if parent_spec is None:
            logger.error("Could not synthesize parent package %s for handler import", _PARENT_PKG)
            return False
        parent_module = importlib.util.module_from_spec(parent_spec)
        parent_module.__path__ = []  # type: ignore[attr-defined]
        sys.modules[_PARENT_PKG] = parent_module

    spec = importlib.util.spec_from_file_location(
        module_name,
        path,
        submodule_search_locations=[str(skill_dir)],
    )
    if spec is None or spec.loader is None:
        logger.error("Could not build spec for %s", path)
        return False

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        logger.exception("Failed to import handlers from %s; skipping", path)
        sys.modules.pop(module_name, None)
        return False
    _imported_module_names.add(module_name)
    return True
