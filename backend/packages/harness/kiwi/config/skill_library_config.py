from pathlib import Path

from pydantic import BaseModel, Field


def _default_repo_root() -> Path:
    """Resolve the repo root without relying on the current working directory."""
    return Path(__file__).resolve().parents[5]


class SkillLibraryConfig(BaseModel):
    """Configuration for the on-demand skill library (discoverable via skill_search).

    Skills under the library directory are NOT injected into the system prompt.
    The agent discovers them at runtime via the skill_search tool, then reads
    the matched SKILL.md to load instructions on demand. Use this for
    specialized skills that would otherwise bloat the prompt.
    """

    enabled: bool = Field(
        default=True,
        description="Enable skill_search tool and load library skills",
    )
    path: str | None = Field(
        default=None,
        description="Path to skill-library directory. If not specified, defaults to ../skill-library relative to backend directory",
    )
    container_path: str = Field(
        default="/mnt/skill-library",
        description="Path where library skills are mounted in the sandbox container",
    )

    def get_path(self) -> Path:
        """Get the resolved skill-library directory path."""
        if self.path:
            path = Path(self.path)
            if not path.is_absolute():
                path = _default_repo_root() / path
            return path.resolve()
        from kiwi.skill_library.loader import get_skill_library_root_path

        return get_skill_library_root_path()
