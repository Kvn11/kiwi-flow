"""Discovery and loading for the on-demand skill library."""

import logging
from pathlib import Path

from kiwi.skill_library.types import LibrarySkill
from kiwi.skills.parser import parse_skill_file

logger = logging.getLogger(__name__)


def get_skill_library_root_path() -> Path:
    """Default skill-library directory: sibling of backend/.

    loader.py lives at packages/harness/kiwi/skill_library/loader.py — 5
    parents up reaches backend/.
    """
    backend_dir = Path(__file__).resolve().parent.parent.parent.parent.parent
    return backend_dir.parent / "skill-library"


def load_skill_library(
    library_path: Path | None = None,
    use_config: bool = True,
    enabled_only: bool = False,
) -> list[LibrarySkill]:
    """Load library skills from skill-library/<name>/SKILL.md (FLAT layout).

    Library skills are searched once and read on demand — they are not auto-injected
    into the system prompt the way skills/ are.

    Args:
        library_path: Optional override path. Defaults to config or repo-root sibling.
        use_config: When library_path is None and this is True, read the path from
            AppConfig.skill_library; otherwise fall back to the default.
        enabled_only: When True, drop skills the extensions config has disabled.

    Returns:
        Sorted list of LibrarySkill (by name).
    """
    if library_path is None:
        if use_config:
            try:
                from kiwi.config import get_app_config

                config = get_app_config()
                library_path = config.skill_library.get_path()
            except Exception:
                library_path = get_skill_library_root_path()
        else:
            library_path = get_skill_library_root_path()

    if not library_path.exists() or not library_path.is_dir():
        return []

    skills_by_name: dict[str, LibrarySkill] = {}

    # FLAT layout: only consider the immediate children of library_path.
    for entry in sorted(library_path.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        skill_file = entry / "SKILL.md"
        if not skill_file.is_file():
            continue

        # parse_skill_file is reused as-is — it is category-agnostic.
        parsed = parse_skill_file(skill_file, category="library", relative_path=Path(entry.name))
        if parsed is None:
            continue

        # Re-wrap the parsed Skill as a LibrarySkill (FLAT path semantics).
        library_skill = LibrarySkill(
            name=parsed.name,
            description=parsed.description,
            license=parsed.license,
            skill_dir=parsed.skill_dir,
            skill_file=parsed.skill_file,
            relative_path=parsed.relative_path,
            category=parsed.category,
            enabled=True,
        )
        skills_by_name[library_skill.name] = library_skill

    skills = list(skills_by_name.values())

    # Apply extensions_config enable state. Read from disk (not the cached
    # singleton) so Gateway-driven toggles propagate across processes — same
    # pattern as kiwi.skills.loader.
    try:
        from kiwi.config.extensions_config import ExtensionsConfig

        extensions_config = ExtensionsConfig.from_file()
        for skill in skills:
            skill.enabled = extensions_config.is_library_skill_enabled(skill.name)
    except Exception as e:
        logger.warning("Failed to load extensions config for library skills: %s", e)

    if enabled_only:
        skills = [s for s in skills if s.enabled]

    skills.sort(key=lambda s: s.name)

    return skills
