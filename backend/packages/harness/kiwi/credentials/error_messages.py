"""LLM-visible message wording for credential broker errors.

Both `kiwi.credentials.decorators.with_credentials` and
`kiwi.skill_dispatch.dispatcher.invoke_skill_tool` translate broker exceptions
into tool-result strings that the LLM pattern-matches on. Keeping the wording
in one place ensures a skill's behavior is identical whether it uses the
@with_credentials decorator or runs through the skill dispatcher.

These strings deliberately never include credential values — only field labels
and skill names.
"""

from __future__ import annotations

import logging

from .errors import (
    CredentialError,
    CredentialNotConfigured,
    CredentialRejected,
    NoLoginRegistered,
    UnknownSkill,
)

logger = logging.getLogger(__name__)


def format_credential_error(skill_name: str, exc: CredentialError) -> str:
    """Translate a typed CredentialError into the canonical LLM-visible string."""
    if isinstance(exc, CredentialNotConfigured):
        return f"Credentials for '{skill_name}' are not configured. Ask the user to open Settings → Credentials → {skill_name} and fill in: {_label_list(skill_name, exc.missing_fields)}."
    if isinstance(exc, CredentialRejected):
        return (
            f"Stored credentials for '{skill_name}' were rejected by the upstream service. Ask the user to double-check the values in Settings → Credentials → {skill_name} — the API key may have rotated, or a value may have been mistyped."
        )
    if isinstance(exc, NoLoginRegistered):
        return f"Internal error: skill '{skill_name}' did not register a login handler. This is a bug in the skill code, not user-fixable."
    if isinstance(exc, UnknownSkill):
        return f"Internal error: skill '{skill_name}' has not declared a credentials schema in its SKILL.md. This is a bug in the skill, not user-fixable."
    logger.warning("Unexpected CredentialError for '%s': %s", skill_name, exc.__class__.__name__)
    return f"Internal error obtaining credentials for '{skill_name}'."


def _label_list(skill_name: str, field_names: list[str]) -> str:
    """Translate internal field names into the human labels declared in SKILL.md."""
    from .registry import get_credential_registry

    schema = get_credential_registry().get(skill_name)
    if schema is None:
        return ", ".join(field_names)
    label_by_name = {f.name: f.label for f in schema.fields}
    return ", ".join(label_by_name.get(n, n) for n in field_names)
