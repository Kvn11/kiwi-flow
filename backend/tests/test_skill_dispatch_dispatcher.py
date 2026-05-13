"""Tests for kiwi.skill_dispatch.dispatcher.invoke_skill_tool.

Covers happy path, unknown skill/tool, broker-error translation (must match the
@with_credentials wording exactly), ValueError → "rejected arguments" branch,
and generic-exception containment.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kiwi.credentials import (
    CredentialField,
    CredentialRejected,
    CredentialSchema,
    NoLoginRegistered,
    UnknownSkill,
    broker,
)
from kiwi.credentials import registry as cred_registry_module
from kiwi.credentials.registry import CredentialRegistry, set_credential_registry
from kiwi.credentials.store import CredentialStore
from kiwi.skill_dispatch import register_skill_tool, reset_for_tests
from kiwi.skill_dispatch.dispatcher import dispatch_skill_tool


@pytest.fixture(autouse=True)
def _isolate_dispatch_registry():
    reset_for_tests()
    yield
    reset_for_tests()


@pytest.fixture
def kalshi_schema():
    schema = CredentialSchema(
        skill_name="kalshi",
        fields=(
            CredentialField(name="api_key_id", label="API Key ID", type="text"),
            CredentialField(name="api_private_key", label="Private Key (PEM)", type="textarea"),
        ),
    )
    set_credential_registry(CredentialRegistry({"kalshi": schema}))
    yield schema
    cred_registry_module.reset_credential_registry()


@pytest.fixture
def isolated_store(tmp_path: Path):
    store = CredentialStore(tmp_path / "credentials.json")
    broker.set_store(store)
    broker.reset_logins_for_tests()
    yield store
    broker.set_store(None)
    broker.reset_logins_for_tests()


# ── Happy path ──────────────────────────────────────────────────────────


def testdispatch_skill_tool_returns_handler_result_string() -> None:
    @register_skill_tool(skill="echo", tool="say")
    def say(args: dict) -> str:
        return f"got: {args.get('msg', '')}"

    result = dispatch_skill_tool("echo", "say", {"msg": "hello"})
    assert result == "got: hello"


def test_args_default_to_empty_dict() -> None:
    received = {}

    @register_skill_tool(skill="x", tool="y")
    def h(args: dict) -> str:
        received.update(args)
        return "done"

    dispatch_skill_tool("x", "y", None)
    assert received == {}


# ── Argument validation ────────────────────────────────────────────────


def testdispatch_skill_tool_rejects_non_dict_args() -> None:
    @register_skill_tool(skill="x", tool="y")
    def h(args: dict) -> str:
        return "should not run"

    result = dispatch_skill_tool("x", "y", "not a dict")  # type: ignore[arg-type]
    assert "must be a dict" in result
    assert "str" in result


# ── Unknown skill / tool ───────────────────────────────────────────────


def test_unknown_skill_returns_error_string() -> None:
    result = dispatch_skill_tool("nonexistent", "anything", {})
    assert "No skill tool 'anything' is registered on skill 'nonexistent'" in result


def test_known_skill_unknown_tool_returns_error_string() -> None:
    @register_skill_tool(skill="kalshi", tool="account")
    def known(args: dict) -> str:
        return "ok"

    result = dispatch_skill_tool("kalshi", "made_up", {})
    assert "No skill tool 'made_up' is registered on skill 'kalshi'" in result


# ── Broker-error translation matches @with_credentials wording ────────


def test_credential_not_configured_string(kalshi_schema, isolated_store) -> None:
    @register_skill_tool(skill="kalshi", tool="account")
    def h(args: dict) -> str:
        broker.get_values("kalshi")  # raises CredentialNotConfigured
        return "should not reach"

    result = dispatch_skill_tool("kalshi", "account", {})
    assert "are not configured" in result
    assert "Settings → Credentials → kalshi" in result
    # Field LABELS, not internal names, are listed
    assert "API Key ID" in result
    assert "Private Key (PEM)" in result


def test_credential_rejected_string(kalshi_schema, isolated_store) -> None:
    isolated_store.write_values("kalshi", {"api_key_id": "abc", "api_private_key": "PEM"})

    @register_skill_tool(skill="kalshi", tool="account")
    def h(args: dict) -> str:
        raise CredentialRejected("kalshi")

    result = dispatch_skill_tool("kalshi", "account", {})
    assert "rejected by the upstream service" in result
    assert "Settings → Credentials → kalshi" in result


def test_no_login_registered_string(kalshi_schema, isolated_store) -> None:
    @register_skill_tool(skill="kalshi", tool="account")
    def h(args: dict) -> str:
        raise NoLoginRegistered("kalshi")

    result = dispatch_skill_tool("kalshi", "account", {})
    assert "did not register a login handler" in result


def test_unknown_skill_credential_error_returns_internal_error(kalshi_schema, isolated_store) -> None:
    @register_skill_tool(skill="kalshi", tool="account")
    def h(args: dict) -> str:
        raise UnknownSkill("nonsense")

    result = dispatch_skill_tool("kalshi", "account", {})
    assert "has not declared a credentials schema" in result


def test_credential_not_configured_with_empty_value(kalshi_schema, isolated_store) -> None:
    """End-to-end: write only one of two fields, dispatcher returns the not-configured string."""
    isolated_store.write_values("kalshi", {"api_key_id": "abc"})

    @register_skill_tool(skill="kalshi", tool="account")
    def h(args: dict) -> str:
        broker.get_values("kalshi")
        return "won't get here"

    result = dispatch_skill_tool("kalshi", "account", {})
    assert "are not configured" in result
    # Only the missing field's label appears, not the populated one
    assert "Private Key (PEM)" in result
    assert "API Key ID" not in result


# ── Argument validation by handler ─────────────────────────────────────


def test_handler_arg_sentinel_becomes_rejected_arguments(kalshi_schema, isolated_store) -> None:
    """Handlers signal arg-shape errors with SkillToolArgumentError → 'rejected arguments'."""
    from kiwi.skill_dispatch import SkillToolArgumentError

    @register_skill_tool(skill="kalshi", tool="search")
    def h(args: dict) -> str:
        if "query" not in args:
            raise SkillToolArgumentError("missing required arg 'query'")
        return "ok"

    result = dispatch_skill_tool("kalshi", "search", {})
    assert "rejected arguments" in result
    assert "query" in result


def test_plain_value_error_is_not_misclassified_as_rejected_arguments(kalshi_schema, isolated_store) -> None:
    """A deep-stack ValueError (e.g. int('abc')) must NOT surface as 'rejected arguments'."""

    @register_skill_tool(skill="kalshi", tool="account")
    def h(args: dict) -> str:
        return str(int("not-a-number"))

    result = dispatch_skill_tool("kalshi", "account", {})
    assert "rejected arguments" not in result
    assert "failed" in result.lower()
    assert "ValueError" in result


# ── Generic exception containment ──────────────────────────────────────


def test_handler_generic_exception_caught(kalshi_schema, isolated_store, caplog) -> None:
    @register_skill_tool(skill="kalshi", tool="account")
    def h(args: dict) -> str:
        raise RuntimeError("upstream blew up")

    result = dispatch_skill_tool("kalshi", "account", {})
    assert "failed" in result.lower()
    assert "RuntimeError" in result
    # The log captured the traceback
    assert any("raised" in rec.message for rec in caplog.records)


# ── Args mutation containment ──────────────────────────────────────────


def test_handler_cannot_mutate_caller_args(kalshi_schema, isolated_store) -> None:
    """Caller-supplied dict must not leak handler mutations (LangGraph still references it for tracing)."""

    @register_skill_tool(skill="kalshi", tool="account")
    def h(args: dict) -> str:
        args["injected"] = "leaked"
        args.pop("user_input", None)
        return "ok"

    caller_args = {"user_input": "preserve me"}
    dispatch_skill_tool("kalshi", "account", caller_args)
    assert caller_args == {"user_input": "preserve me"}


# ── Disabled-skill rejection ───────────────────────────────────────────


def test_dispatch_rejects_disabled_skill(kalshi_schema, isolated_store, monkeypatch) -> None:
    """Toggling a skill off in extensions config must block dispatch even after registration."""
    from dataclasses import dataclass

    @dataclass
    class _StubSkill:
        name: str
        enabled: bool

    monkeypatch.setattr(
        "kiwi.skills.loader.load_skills",
        lambda enabled_only=False: [_StubSkill(name="kalshi", enabled=False)],
    )
    monkeypatch.setattr(
        "kiwi.skill_library.loader.load_skill_library",
        lambda enabled_only=False: [],
    )

    @register_skill_tool(skill="kalshi", tool="account")
    def h(args: dict) -> str:
        return "should not be reached"

    result = dispatch_skill_tool("kalshi", "account", {})
    assert "disabled" in result.lower()
    assert "Settings" in result


# ── Coercion ───────────────────────────────────────────────────────────


def test_non_string_handler_return_is_coerced(caplog) -> None:
    @register_skill_tool(skill="x", tool="y")
    def h(args: dict):
        return {"unexpected": "shape"}  # type: ignore[return-value]

    result = dispatch_skill_tool("x", "y", {})
    assert isinstance(result, str)
    assert "unexpected" in result
    assert any("coercing to str" in rec.message for rec in caplog.records)
