"""The `@with_credentials` decorator that ties skill tools to the broker.

A skill tool decorated with `@with_credentials("kalshi")` receives a `Creds`
proxy as its first positional argument. The proxy lazily fetches a fresh token
on first access and exposes `.invalidate()` for the upstream-401 case.

Broker exceptions are caught and converted into **distinct, LLM-visible
strings** — the agent reading the tool result can pattern-match on each case
and behave differently (open settings, ask user to verify, etc.). The decorator
never echoes credential values into the result strings.
"""

from __future__ import annotations

import functools
import inspect
import logging
from collections.abc import Callable
from typing import Any

from . import broker
from .error_messages import format_credential_error
from .errors import CredentialError

logger = logging.getLogger(__name__)


class Creds:
    """Proxy passed to the wrapped tool. Lazily fetches a fresh token."""

    def __init__(self, skill_name: str) -> None:
        self._skill_name = skill_name
        self._cached_token: str | None = None

    @property
    def skill_name(self) -> str:
        return self._skill_name

    @property
    def token(self) -> str:
        if self._cached_token is None:
            self._cached_token = broker.get_token(self._skill_name)
        return self._cached_token

    def invalidate(self) -> None:
        """Clear both the broker's stored token and the local cache.

        Call this after receiving a 401/403 from the upstream so the next
        `creds.token` access triggers a fresh login.
        """
        broker.invalidate_token(self._skill_name)
        self._cached_token = None

    @property
    def values(self) -> dict[str, str]:
        """Raw stored values, validated. Use only for non-token auth (Basic, etc.)."""
        return broker.get_values(self._skill_name)


def with_credentials(skill_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorate a tool so its first positional arg receives a `Creds` proxy.

    Errors from the broker are translated into LLM-visible result strings:

    - `CredentialNotConfigured` → "open Settings, fill in: …"
    - `CredentialRejected` → "values were rejected, ask user to verify"
    - `NoLoginRegistered` → "internal bug: skill missed register_login"
    - `UnknownSkill` → "internal bug: skill missed credentials block"

    Decoration order with `@tool` matters — apply `@with_credentials` first so
    the resulting signature (no `creds` argument) is what LangChain inspects:

        @tool("name", parse_docstring=True)
        @with_credentials("kalshi")
        def kalshi_buy(creds, market_id: str, qty: int) -> str:
            ...
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        if not params:
            raise TypeError(f"@with_credentials requires the wrapped function to accept at least one positional parameter for the Creds proxy (got '{fn.__name__}' with no parameters)")
        public_sig = sig.replace(parameters=params[1:])

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            creds = Creds(skill_name)
            try:
                _ = creds.token
            except CredentialError as exc:
                return format_credential_error(skill_name, exc)
            return fn(creds, *args, **kwargs)

        wrapper.__signature__ = public_sig  # type: ignore[attr-defined]
        return wrapper

    return decorator
