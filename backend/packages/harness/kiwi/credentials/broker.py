"""Module-level broker API for skill credentials.

Skills call these functions to obtain valid tokens or raw values; the broker
handles schema validation, session-token caching with refresh-skew, and
invoking each skill's `login_fn` on cache miss / expiry / 401. See CLAUDE.md
for usage patterns.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from .errors import CredentialNotConfigured, CredentialRejected, NoLoginRegistered, UnknownSkill
from .registry import get_credential_registry
from .store import CredentialStore
from .types import CredentialSchema, StoredEntry, Token

logger = logging.getLogger(__name__)

LoginFn = Callable[[dict[str, str]], Token]

# Refresh tokens this many seconds before their declared expiry. Same default
# as the existing OAuthTokenManager so behavior is consistent across the codebase.
REFRESH_SKEW_SECONDS = 60

_login_registry: dict[str, LoginFn] = {}
_store: CredentialStore | None = None


def _get_store() -> CredentialStore:
    global _store
    if _store is None:
        _store = CredentialStore()
    return _store


def set_store(store: CredentialStore | None) -> None:
    """Override the default store. Pass None to fall back to the default. (Tests.)"""
    global _store
    _store = store


def register_login(skill_name: str, login_fn: LoginFn) -> None:
    """Register a skill's login callback. Idempotent — last registration wins."""
    _login_registry[skill_name] = login_fn


def has_login_registered(skill_name: str) -> bool:
    return skill_name in _login_registry


def reset_logins_for_tests() -> None:
    """Clear all registered login callbacks. (Tests.)"""
    _login_registry.clear()


# ── Public API ───────────────────────────────────────────────────────────


def get_values(skill_name: str) -> dict[str, str]:
    """Return stored values for a skill, validated against its schema.

    Raises:
        UnknownSkill: not in the credential registry.
        CredentialNotConfigured: schema exists but one or more fields are empty.
    """
    schema = _require_schema(skill_name)
    entry = _get_store().read_one(skill_name)
    values = entry.values if entry is not None else {}
    missing = _missing_fields(schema, values)
    if missing:
        raise CredentialNotConfigured(skill_name, missing)
    return {f.name: values[f.name] for f in schema.fields}


def get_token(skill_name: str) -> str:
    """Return a fresh access token, running `login_fn` if necessary.

    Raises:
        UnknownSkill: not in the credential registry.
        CredentialNotConfigured: values missing for one or more required fields.
        NoLoginRegistered: no `login_fn` registered for this skill.
        CredentialRejected: `login_fn` ran but the upstream returned an error.
    """
    schema = _require_schema(skill_name)

    entry = _get_store().read_one(skill_name)
    if entry is not None and entry.token is not None and _is_token_fresh(entry.token):
        return entry.token.access_token

    values = entry.values if entry is not None else {}
    missing = _missing_fields(schema, values)
    if missing:
        raise CredentialNotConfigured(skill_name, missing)

    login_fn = _login_registry.get(skill_name)
    if login_fn is None:
        raise NoLoginRegistered(skill_name)

    filtered = {f.name: values[f.name] for f in schema.fields}
    try:
        token = login_fn(filtered)
    except CredentialRejected:
        raise
    except Exception as exc:
        # Log only the exception class — the message may contain credential bytes echoed
        # back by the upstream API.
        logger.warning("login_fn for '%s' raised %s", skill_name, exc.__class__.__name__)
        raise CredentialRejected(skill_name) from exc

    if not isinstance(token, Token):
        raise CredentialRejected(skill_name, reason="login_fn did not return a Token")

    _get_store().write_token(skill_name, token)
    return token.access_token


def invalidate_token(skill_name: str) -> None:
    """Clear the cached token so the next `get_token` re-runs `login_fn`."""
    _get_store().write_token(skill_name, None)


def set_values(skill_name: str, values: dict[str, str]) -> StoredEntry:
    """Persist user-entered values, validated against the registered schema.

    Unknown field names raise `ValueError`. Existing values for fields not
    present in `values` are preserved (partial-update semantics). Returns the
    post-merge entry so the caller doesn't need a second store read.
    """
    schema = _require_schema(skill_name)
    allowed = {f.name for f in schema.fields}
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ValueError(f"Unknown credential fields for '{skill_name}': {unknown}")

    return _get_store().merge_values(skill_name, values)


def clear(skill_name: str) -> None:
    """Wipe both values and token for a skill. Idempotent."""
    _get_store().delete(skill_name)


def status(skill_name: str) -> dict[str, object]:
    """Return a serializable status dict — never contains raw values."""
    schema = _require_schema(skill_name)
    entry = _get_store().read_one(skill_name)
    return _entry_to_status(schema, entry)


def status_all(skill_names: list[str]) -> dict[str, dict[str, object]]:
    """Compute status for many skills with a single store read.

    Used by the Gateway list endpoint so the per-skill `read_one` lock churn
    is collapsed into one `read_all`. Skills not in the registry are skipped.
    """
    registry = get_credential_registry()
    all_entries = _get_store().read_all()
    out: dict[str, dict[str, object]] = {}
    for name in skill_names:
        schema = registry.get(name)
        if schema is None:
            continue
        out[name] = _entry_to_status(schema, all_entries.get(name))
    return out


def _entry_to_status(schema: CredentialSchema, entry: StoredEntry | None) -> dict[str, object]:
    values = entry.values if entry is not None else {}
    field_names = [f.name for f in schema.fields]
    fields_set = [name for name in field_names if values.get(name, "").strip()]
    has_token = entry is not None and entry.token is not None and _is_token_fresh(entry.token)
    return {
        "configured": len(fields_set) == len(field_names),
        "fields_set": fields_set,
        "has_token": has_token,
        "token_expires_at": entry.token.expires_at if entry is not None and entry.token is not None else None,
        "updated_at": entry.updated_at if entry is not None else None,
    }


def _require_schema(skill_name: str) -> CredentialSchema:
    schema = get_credential_registry().get(skill_name)
    if schema is None:
        raise UnknownSkill(skill_name)
    return schema


def _missing_fields(schema: CredentialSchema, values: dict[str, str]) -> list[str]:
    return [f.name for f in schema.fields if not values.get(f.name, "").strip()]


def _is_token_fresh(token: Token) -> bool:
    if token.expires_at is None:
        return True
    return token.expires_at - int(time.time()) > REFRESH_SKEW_SECONDS
