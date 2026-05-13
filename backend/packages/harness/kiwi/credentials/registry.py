"""Discovers `credentials:` blocks across all skill sources.

The registry is the single source of truth for "which skills declared a need
for credentials, and what fields do they want?". The Gateway uses it to render
the Settings UI; the broker uses it to validate `set_values` payloads.

Skill sources scanned (the same three the rest of Kiwi uses):
- `skills/public/`
- `skills/custom/`
- `skill-library/`

The registry is process-cached. Call `reload_credential_registry()` after
installing or removing a skill so newly-declared schemas appear without
restarting the process.
"""

from __future__ import annotations

import logging

from .parser import parse_skill_credentials
from .types import CredentialSchema

logger = logging.getLogger(__name__)


class CredentialRegistry:
    """In-memory map of `skill_name → CredentialSchema`."""

    def __init__(self, schemas: dict[str, CredentialSchema] | None = None) -> None:
        self._schemas: dict[str, CredentialSchema] = dict(schemas or {})

    def get(self, skill_name: str) -> CredentialSchema | None:
        return self._schemas.get(skill_name)

    def list(self) -> dict[str, CredentialSchema]:
        """Return a copy of the registry (callers shouldn't mutate the singleton)."""
        return dict(self._schemas)

    def __contains__(self, skill_name: str) -> bool:
        return skill_name in self._schemas

    def __len__(self) -> int:
        return len(self._schemas)


def build_credential_registry() -> CredentialRegistry:
    """Scan all skill sources and build a fresh registry."""
    from kiwi.skills.loader import iter_all_skill_files

    schemas: dict[str, CredentialSchema] = {}
    for skill_file in iter_all_skill_files():
        schema = parse_skill_credentials(skill_file)
        if schema is None:
            continue
        if schema.skill_name in schemas:
            logger.warning(
                "Duplicate credentials schema for '%s' (later definition at %s wins over earlier one)",
                schema.skill_name,
                skill_file,
            )
        schemas[schema.skill_name] = schema
    logger.info("Credential registry built with %d schema(s)", len(schemas))
    return CredentialRegistry(schemas)


_registry: CredentialRegistry | None = None


def get_credential_registry() -> CredentialRegistry:
    """Return the cached registry, building it on first access."""
    global _registry
    if _registry is None:
        _registry = build_credential_registry()
    return _registry


def reload_credential_registry() -> CredentialRegistry:
    """Discard the cache and rebuild from disk."""
    global _registry
    _registry = build_credential_registry()
    return _registry


def reset_credential_registry() -> None:
    """Drop the cached registry without rebuilding (useful in tests)."""
    global _registry
    _registry = None


def set_credential_registry(registry: CredentialRegistry) -> None:
    """Inject a custom registry — primarily for tests."""
    global _registry
    _registry = registry
