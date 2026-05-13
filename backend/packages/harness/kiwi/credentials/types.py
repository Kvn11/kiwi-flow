"""Public types for the kiwi.credentials package.

These types are intentionally simple. Schema declarations carry only what the
frontend needs to render a form; everything else (whether a field is required,
whether it is a secret) is implied — credentials are by definition both, and
every field declared in a `credentials:` block is required for the skill to
function.
"""

from dataclasses import dataclass, field
from typing import Literal

FieldType = Literal["text", "textarea"]


@dataclass(frozen=True)
class CredentialField:
    """A single input slot inside a skill's credentials schema."""

    name: str
    label: str
    type: FieldType = "text"


@dataclass(frozen=True)
class CredentialSchema:
    """The full set of credential fields a skill needs.

    Created by `parse_skill_credentials` from a SKILL.md `credentials:` block.
    """

    skill_name: str
    fields: tuple[CredentialField, ...]

    def field_names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields)


@dataclass(frozen=True)
class Token:
    """A session token returned by a skill's `login_fn`.

    Lifetime metadata comes entirely from the upstream provider — there is no
    skill-author-set lifetime knob.
    """

    access_token: str
    expires_at: int | None = None
    scope: str | None = None


@dataclass(frozen=True)
class StoredEntry:
    """One skill's row in credentials.json (in-memory representation, immutable)."""

    values: dict[str, str] = field(default_factory=dict)
    token: Token | None = None
    updated_at: str | None = None
