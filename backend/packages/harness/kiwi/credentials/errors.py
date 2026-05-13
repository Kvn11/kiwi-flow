"""Typed exceptions raised by the credentials broker.

The `@with_credentials` decorator catches these and converts them into distinct
LLM-visible tool result strings — the LLM should be able to react differently
to each case (e.g., direct the user to settings vs. ask them to verify a value).
"""


class CredentialError(Exception):
    """Base class for all credential-related errors."""


class CredentialNotConfigured(CredentialError):
    """No entry exists for this skill, or one or more required fields are empty."""

    def __init__(self, skill_name: str, missing_fields: list[str]) -> None:
        self.skill_name = skill_name
        self.missing_fields = list(missing_fields)
        super().__init__(f"Credentials for '{skill_name}' are not configured (missing: {self.missing_fields})")


class CredentialRejected(CredentialError):
    """The skill's `login_fn` ran with stored values but the upstream rejected them."""

    def __init__(self, skill_name: str, reason: str | None = None) -> None:
        self.skill_name = skill_name
        self.reason = reason
        message = f"Credentials for '{skill_name}' were rejected by the upstream service"
        if reason:
            message = f"{message}: {reason}"
        super().__init__(message)


class NoLoginRegistered(CredentialError):
    """The skill's tools called the broker but the skill never registered a `login_fn`."""

    def __init__(self, skill_name: str) -> None:
        self.skill_name = skill_name
        super().__init__(f"Skill '{skill_name}' did not register a login handler")


class UnknownSkill(CredentialError):
    """A consumer referenced a skill that has not declared a credentials schema."""

    def __init__(self, skill_name: str) -> None:
        self.skill_name = skill_name
        super().__init__(f"Skill '{skill_name}' has not registered a credentials schema")
