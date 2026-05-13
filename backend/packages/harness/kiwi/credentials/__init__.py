"""Centralized credential store for Kiwi skills.

Public surface:
- `broker`             — module-level functions skill code calls at runtime
- `with_credentials`   — decorator that turns broker errors into LLM-visible strings
- typed errors          — for skills that want explicit handling
- `CredentialSchema`   — what the registry exposes about each skill

The store file (`$KIWI_FLOW_HOME/credentials.json`, mode 0o600) is intentionally
*not* exported. Only `kiwi.credentials.broker` and the Gateway router should
read or write it; everything else should go through the broker API.
"""

from . import broker
from .decorators import with_credentials
from .error_messages import format_credential_error
from .errors import (
    CredentialError,
    CredentialNotConfigured,
    CredentialRejected,
    NoLoginRegistered,
    UnknownSkill,
)
from .parser import parse_skill_credentials
from .registry import CredentialRegistry, get_credential_registry, reload_credential_registry
from .types import CredentialField, CredentialSchema, FieldType, StoredEntry, Token

__all__ = [
    "broker",
    "with_credentials",
    "format_credential_error",
    "CredentialError",
    "CredentialNotConfigured",
    "CredentialRejected",
    "NoLoginRegistered",
    "UnknownSkill",
    "CredentialField",
    "CredentialSchema",
    "FieldType",
    "StoredEntry",
    "Token",
    "parse_skill_credentials",
    "CredentialRegistry",
    "get_credential_registry",
    "reload_credential_registry",
]
