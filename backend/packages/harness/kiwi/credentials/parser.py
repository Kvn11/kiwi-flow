"""Parse the `credentials:` block from a SKILL.md frontmatter.

The existing `kiwi.skills.parser.parse_skill_file` produces a `Skill` object
that intentionally knows nothing about credentials — that's what keeps the
schema out of any LLM-visible skill metadata. We share the YAML-loading helper
with that module but extract entirely different keys here.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import get_args

from kiwi.skills.parser import load_skill_frontmatter

from .types import CredentialField, CredentialSchema, FieldType

logger = logging.getLogger(__name__)

_VALID_TYPES: frozenset[str] = frozenset(get_args(FieldType))


def parse_skill_credentials(
    skill_file: Path,
    metadata: dict | None = None,
) -> CredentialSchema | None:
    """Return a `CredentialSchema` if the SKILL.md declares a `credentials:` block.

    `metadata` may be passed by callers that already loaded the frontmatter
    (e.g. the registry, which wants to avoid parsing each SKILL.md twice).
    Returns None for missing/empty/malformed credential blocks.
    """
    if metadata is None:
        metadata = load_skill_frontmatter(skill_file)
    if metadata is None:
        return None

    skill_name = metadata.get("name")
    if not isinstance(skill_name, str) or not skill_name.strip():
        return None
    skill_name = skill_name.strip()

    creds_block = metadata.get("credentials")
    if creds_block is None:
        return None
    if not isinstance(creds_block, dict):
        logger.warning("`credentials` block in %s must be a mapping, got %s", skill_file, type(creds_block).__name__)
        return None

    raw_fields = creds_block.get("fields")
    if not isinstance(raw_fields, list) or not raw_fields:
        logger.warning("`credentials.fields` in %s must be a non-empty list", skill_file)
        return None

    fields: list[CredentialField] = []
    seen_names: set[str] = set()
    for entry in raw_fields:
        if not isinstance(entry, dict):
            logger.warning("Field entry in %s is not a mapping: %r", skill_file, entry)
            return None

        f_name = entry.get("name")
        f_label = entry.get("label")
        f_type = entry.get("type", "text")

        if not isinstance(f_name, str) or not f_name.strip():
            logger.warning("Field in %s missing required string 'name': %r", skill_file, entry)
            return None
        if not isinstance(f_label, str) or not f_label.strip():
            logger.warning("Field in %s missing required string 'label': %r", skill_file, entry)
            return None
        if f_type not in _VALID_TYPES:
            logger.warning("Field '%s' in %s has invalid type %r; expected one of %s", f_name, skill_file, f_type, sorted(_VALID_TYPES))
            return None

        f_name_clean = f_name.strip()
        if f_name_clean in seen_names:
            logger.warning("Duplicate field name '%s' in %s", f_name_clean, skill_file)
            return None
        seen_names.add(f_name_clean)

        fields.append(CredentialField(name=f_name_clean, label=f_label.strip(), type=f_type))

    return CredentialSchema(skill_name=skill_name, fields=tuple(fields))
