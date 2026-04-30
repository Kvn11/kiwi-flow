from dataclasses import dataclass

from kiwi.skills.types import Skill


@dataclass
class LibrarySkill(Skill):
    """A skill from the on-demand library.

    Layout is FLAT (skill-library/<name>/SKILL.md) — no public/custom
    category split — so we override get_container_path() to skip the
    category segment that the base Skill class hardcodes.
    """

    def get_container_path(self, container_base_path: str = "/mnt/skill-library") -> str:
        skill_path = self.skill_path
        if skill_path:
            return f"{container_base_path}/{skill_path}"
        return container_base_path

    def get_container_file_path(self, container_base_path: str = "/mnt/skill-library") -> str:
        return f"{self.get_container_path(container_base_path)}/SKILL.md"

    def __repr__(self) -> str:
        return f"LibrarySkill(name={self.name!r}, description={self.description!r})"
