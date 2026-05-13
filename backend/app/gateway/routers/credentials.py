"""Gateway endpoints for the centralized credential store.

The router exposes a write-only-for-secrets API: callers can read each skill's
*schema* and *configured status*, but never the stored values. Only skills that
have declared a credentials schema (via SKILL.md) can have entries set or
cleared — the registry is the source of truth for which slots exist, so the
frontend cannot create new ones.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from kiwi.config.extensions_config import ExtensionsConfig
from kiwi.credentials import (
    UnknownSkill,
    broker,
    get_credential_registry,
)
from kiwi.credentials.types import CredentialSchema

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["credentials"])


# ── Schemas ────────────────────────────────────────────────────────────


class CredentialFieldSchema(BaseModel):
    """Single field declaration as exposed to the frontend."""

    name: str = Field(..., description="Internal field name")
    label: str = Field(..., description="Human-facing label")
    type: Literal["text", "textarea"] = Field(..., description="UI rendering hint")


class CredentialEntryStatus(BaseModel):
    """Status of one skill's credential entry. Never contains raw values."""

    skill_name: str
    fields: list[CredentialFieldSchema] = Field(..., description="Schema fields for this skill")
    configured: bool = Field(..., description="True if every required field has a non-empty value")
    fields_set: list[str] = Field(..., description="Names of fields that are currently set")
    has_token: bool = Field(..., description="True if a fresh cached token is present")
    token_expires_at: int | None = Field(None, description="Unix timestamp the cached token expires at, if any")
    updated_at: str | None = Field(None, description="ISO 8601 timestamp of the last value update")


class CredentialListResponse(BaseModel):
    credentials: list[CredentialEntryStatus]


class CredentialUpdateRequest(BaseModel):
    field_values: dict[str, str] = Field(
        ...,
        description="Map of field name → new value. Only fields named in the schema are accepted.",
    )


# ── Helpers ────────────────────────────────────────────────────────────


def _build_enabled_skill_set() -> set[str]:
    """Set of skill names enabled in extensions_config across public/custom/library sources.

    Skills that don't appear in either loader (e.g. registry survived after the
    SKILL.md was removed) are treated as enabled so the user can still clear them.
    """
    try:
        ext_cfg = ExtensionsConfig.from_file()
    except Exception as exc:
        logger.warning("Could not load extensions config; treating all schemas as enabled: %s", exc)
        return set(get_credential_registry().list().keys())

    enabled: set[str] = set()
    seen: set[str] = set()
    try:
        from kiwi.skills.loader import load_skills

        for skill in load_skills(enabled_only=False):
            seen.add(skill.name)
            if ext_cfg.is_skill_enabled(skill.name, skill.category):
                enabled.add(skill.name)
    except Exception:
        pass

    try:
        from kiwi.skill_library.loader import load_skill_library

        for skill in load_skill_library(enabled_only=False):
            seen.add(skill.name)
            if ext_cfg.is_library_skill_enabled(skill.name):
                enabled.add(skill.name)
    except Exception:
        pass

    # Schemas with no matching SKILL.md are treated as enabled (orphan-clear path).
    enabled.update(name for name in get_credential_registry().list() if name not in seen)
    return enabled


def _make_entry_status(skill_name: str, schema: CredentialSchema, status: dict[str, object]) -> CredentialEntryStatus:
    return CredentialEntryStatus(
        skill_name=skill_name,
        fields=[CredentialFieldSchema(name=f.name, label=f.label, type=f.type) for f in schema.fields],
        configured=bool(status["configured"]),
        fields_set=list(status["fields_set"]),  # type: ignore[arg-type]
        has_token=bool(status["has_token"]),
        token_expires_at=status.get("token_expires_at"),  # type: ignore[arg-type]
        updated_at=status.get("updated_at"),  # type: ignore[arg-type]
    )


def _build_status(skill_name: str) -> CredentialEntryStatus:
    schema = get_credential_registry().get(skill_name)
    if schema is None:
        raise HTTPException(status_code=404, detail=f"No credentials schema registered for skill '{skill_name}'")
    return _make_entry_status(skill_name, schema, broker.status(skill_name))


# ── Endpoints ──────────────────────────────────────────────────────────


@router.get(
    "/credentials",
    response_model=CredentialListResponse,
    summary="List Credential Slots",
    description="List every skill that declared a credentials schema, with its configured status. Never returns raw values. Disabled skills are filtered out.",
)
async def list_credentials() -> CredentialListResponse:
    try:
        registry = get_credential_registry()
        enabled = _build_enabled_skill_set()
        candidates = sorted(name for name in registry.list() if name in enabled)
        statuses_by_name = broker.status_all(candidates)
        return CredentialListResponse(
            credentials=[_make_entry_status(name, registry.get(name), statuses_by_name[name]) for name in candidates if name in statuses_by_name],
        )
    except Exception as exc:
        logger.error("Failed to list credentials: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list credentials: {exc}")


@router.get(
    "/credentials/{skill_name}",
    response_model=CredentialEntryStatus,
    summary="Get Credential Slot",
    description="Get the schema and configured status for a single skill's credentials slot.",
)
async def get_credential(skill_name: str) -> CredentialEntryStatus:
    return _build_status(skill_name)


@router.put(
    "/credentials/{skill_name}",
    response_model=CredentialEntryStatus,
    summary="Update Credential Values",
    description="Persist user-entered values for a skill's credentials. Returns 404 if the skill has not declared a credentials schema.",
)
async def update_credential(skill_name: str, request: CredentialUpdateRequest) -> CredentialEntryStatus:
    if get_credential_registry().get(skill_name) is None:
        raise HTTPException(status_code=404, detail=f"No credentials schema registered for skill '{skill_name}'")
    try:
        broker.set_values(skill_name, request.field_values)
    except UnknownSkill:
        raise HTTPException(status_code=404, detail=f"No credentials schema registered for skill '{skill_name}'")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Failed to update credentials for '%s': %s", skill_name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update credentials: {exc}")
    return _build_status(skill_name)


@router.delete(
    "/credentials/{skill_name}",
    summary="Clear Credentials",
    description="Wipe both stored values and any cached token for a skill.",
)
async def delete_credential(skill_name: str) -> dict[str, bool]:
    if get_credential_registry().get(skill_name) is None:
        raise HTTPException(status_code=404, detail=f"No credentials schema registered for skill '{skill_name}'")
    try:
        broker.clear(skill_name)
    except Exception as exc:
        logger.error("Failed to clear credentials for '%s': %s", skill_name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to clear credentials: {exc}")
    return {"success": True}
