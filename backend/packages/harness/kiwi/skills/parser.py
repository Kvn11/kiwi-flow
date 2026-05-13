import logging
import re
from pathlib import Path

import yaml

from .types import Skill

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def load_skill_frontmatter(skill_file: Path) -> dict | None:
    """Return the parsed YAML frontmatter of a SKILL.md as a dict, or None.

    Returns None when the file is missing/unreadable, has no frontmatter,
    has malformed YAML, or has frontmatter that is not a mapping. Each caller
    decides which keys to read; this function never inspects field semantics.
    """
    if skill_file.name != "SKILL.md":
        return None
    try:
        content = skill_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.warning("Cannot read %s: %s", skill_file, exc)
        return None

    match = _FRONTMATTER_RE.match(content)
    if not match:
        return None
    try:
        metadata = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        logger.error("Invalid YAML front-matter in %s: %s", skill_file, exc)
        return None
    if not isinstance(metadata, dict):
        logger.error("Front-matter in %s is not a YAML mapping", skill_file)
        return None
    return metadata


def parse_skill_file(skill_file: Path, category: str, relative_path: Path | None = None) -> Skill | None:
    """Parse a SKILL.md file and extract metadata.

    Args:
        skill_file: Path to the SKILL.md file.
        category: Category of the skill ('public' or 'custom').
        relative_path: Relative path from the category root to the skill
            directory.  Defaults to the skill directory name when omitted.

    Returns:
        Skill object if parsing succeeds, None otherwise.
    """
    metadata = load_skill_frontmatter(skill_file)
    if metadata is None:
        return None

    try:
        name = metadata.get("name")
        description = metadata.get("description")
        if not isinstance(name, str) or not isinstance(description, str):
            return None
        name = name.strip()
        description = description.strip()
        if not name or not description:
            return None

        license_text = metadata.get("license")
        if license_text is not None:
            license_text = str(license_text).strip() or None

        return Skill(
            name=name,
            description=description,
            license=license_text,
            skill_dir=skill_file.parent,
            skill_file=skill_file,
            relative_path=relative_path or Path(skill_file.parent.name),
            category=category,
            enabled=True,  # Actual state comes from the extensions config file.
        )
    except Exception:
        logger.exception("Unexpected error parsing skill file %s", skill_file)
        return None
