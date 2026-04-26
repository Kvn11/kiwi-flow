"""Gateway router for the on-demand skill library.

Library skills are not auto-injected into the system prompt — the agent
discovers them at runtime via skill_search. This router exposes:

  - GET    /api/library-skills            — list all (with enabled state)
  - GET    /api/library-skills/{name}     — details for one
  - PUT    /api/library-skills/{name}     — toggle enabled

Toggling writes extensions_config.json (round-tripping the full document so
unrelated sections — mcpServers, skills — are preserved) and resets the
in-process registry cache so the next skill_search reflects the change.
There is NO prompt-cache invalidation: library skills never appear in the
system prompt.
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from deerflow.config.extensions_config import (
    ExtensionsConfig,
    LibrarySkillStateConfig,
    reload_extensions_config,
)
from deerflow.skill_library import LibrarySkill, load_skill_library, reset_library_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["library-skills"])


class LibrarySkillResponse(BaseModel):
    """Response model for a library skill."""

    name: str = Field(..., description="Name of the library skill")
    description: str = Field(..., description="What the library skill does")
    license: str | None = Field(None, description="License information")
    enabled: bool = Field(default=True, description="Whether this library skill is searchable")
    path: str = Field(..., description="Container path to the SKILL.md (read with read_file)")


class LibrarySkillsListResponse(BaseModel):
    skills: list[LibrarySkillResponse]


class LibrarySkillUpdateRequest(BaseModel):
    enabled: bool = Field(..., description="Whether to enable or disable the library skill")


def _to_response(skill: LibrarySkill) -> LibrarySkillResponse:
    return LibrarySkillResponse(
        name=skill.name,
        description=skill.description,
        license=skill.license,
        enabled=skill.enabled,
        path=skill.get_container_file_path(),
    )


@router.get(
    "/library-skills",
    response_model=LibrarySkillsListResponse,
    summary="List Library Skills",
    description="List all skills under the on-demand skill library directory.",
)
async def list_library_skills() -> LibrarySkillsListResponse:
    try:
        skills = load_skill_library(enabled_only=False)
        return LibrarySkillsListResponse(skills=[_to_response(s) for s in skills])
    except Exception as e:
        logger.error("Failed to list library skills: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list library skills: {e}") from e


@router.get(
    "/library-skills/{skill_name}",
    response_model=LibrarySkillResponse,
    summary="Get Library Skill",
    description="Get details for a single library skill by name.",
)
async def get_library_skill(skill_name: str) -> LibrarySkillResponse:
    try:
        skills = load_skill_library(enabled_only=False)
        skill = next((s for s in skills if s.name == skill_name), None)
        if skill is None:
            raise HTTPException(status_code=404, detail=f"Library skill '{skill_name}' not found")
        return _to_response(skill)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get library skill %s: %s", skill_name, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get library skill: {e}") from e


@router.put(
    "/library-skills/{skill_name}",
    response_model=LibrarySkillResponse,
    summary="Update Library Skill",
    description="Enable or disable a single library skill. Disabled skills are excluded from skill_search results.",
)
async def update_library_skill(skill_name: str, request: LibrarySkillUpdateRequest) -> LibrarySkillResponse:
    try:
        skills = load_skill_library(enabled_only=False)
        skill = next((s for s in skills if s.name == skill_name), None)
        if skill is None:
            raise HTTPException(status_code=404, detail=f"Library skill '{skill_name}' not found")

        config_path = ExtensionsConfig.resolve_config_path()
        if config_path is None:
            # Place the extensions config alongside the project (same fallback as skills router).
            config_path = Path.cwd().parent / "extensions_config.json"
            logger.info("No existing extensions config found. Creating new config at: %s", config_path)

        # Always read fresh from disk before mutating — get_extensions_config()
        # returns a process-local singleton that may be stale relative to whatever
        # the gateway/langgraph cross-process state has written.
        extensions_config = ExtensionsConfig.from_file(str(config_path)) if config_path.exists() else ExtensionsConfig()
        extensions_config.library_skills[skill_name] = LibrarySkillStateConfig(enabled=request.enabled)

        # Round-trip the full config — preserves mcpServers / skills / any extra fields.
        config_data = extensions_config.model_dump(by_alias=True, exclude_none=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)

        logger.info("Library skill '%s' enabled=%s; config written to %s", skill_name, request.enabled, config_path)

        reload_extensions_config()
        # Bust the in-process registry so the next skill_search picks up the change immediately.
        reset_library_registry()

        skills = load_skill_library(enabled_only=False)
        updated = next((s for s in skills if s.name == skill_name), None)
        if updated is None:
            raise HTTPException(status_code=500, detail=f"Failed to reload library skill '{skill_name}' after update")
        return _to_response(updated)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update library skill %s: %s", skill_name, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update library skill: {e}") from e
