"""Tests for ClaudeChatModel._apply_oauth_billing."""

import asyncio
import json
from unittest import mock

import pytest

from kiwi.models.claude_provider import OAUTH_BILLING_HEADER, ClaudeChatModel


def _make_model() -> ClaudeChatModel:
    """Return a minimal ClaudeChatModel instance in OAuth mode without network calls."""
    with mock.patch.object(ClaudeChatModel, "model_post_init"):
        m = ClaudeChatModel(model="claude-sonnet-4-6", anthropic_api_key="sk-ant-oat-fake-token")  # type: ignore[call-arg]
    m._is_oauth = True
    m._oauth_access_token = "sk-ant-oat-fake-token"
    return m


def _make_caching_model() -> ClaudeChatModel:
    """Return a minimal ClaudeChatModel in API-key mode with prompt caching enabled."""
    with mock.patch.object(ClaudeChatModel, "model_post_init"):
        m = ClaudeChatModel(model="claude-sonnet-4-6", anthropic_api_key="sk-ant-api-fake")  # type: ignore[call-arg]
    m._is_oauth = False
    m.enable_prompt_caching = True
    m.prompt_cache_size = 3
    return m


@pytest.fixture()
def model() -> ClaudeChatModel:
    return _make_model()


def _billing_block() -> dict:
    return {"type": "text", "text": OAUTH_BILLING_HEADER}


def _count_cache_breakpoints(payload: dict) -> int:
    """Count cache_control markers across system, tools, and message content blocks."""
    n = 0
    for block in payload.get("system") or []:
        if isinstance(block, dict) and "cache_control" in block:
            n += 1
    for tool in payload.get("tools") or []:
        if isinstance(tool, dict) and "cache_control" in tool:
            n += 1
    for msg in payload.get("messages") or []:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and "cache_control" in block:
                    n += 1
    return n


# ---------------------------------------------------------------------------
# Billing block injection
# ---------------------------------------------------------------------------


def test_billing_injected_first_when_no_system(model):
    payload: dict = {}
    model._apply_oauth_billing(payload)
    assert payload["system"][0] == _billing_block()


def test_billing_injected_first_into_list(model):
    payload = {"system": [{"type": "text", "text": "You are a helpful assistant."}]}
    model._apply_oauth_billing(payload)
    assert payload["system"][0] == _billing_block()
    assert payload["system"][1]["text"] == "You are a helpful assistant."


def test_billing_injected_first_into_string_system(model):
    payload = {"system": "You are helpful."}
    model._apply_oauth_billing(payload)
    assert payload["system"][0] == _billing_block()
    assert payload["system"][1]["text"] == "You are helpful."


def test_billing_not_duplicated_on_second_call(model):
    payload = {"system": [{"type": "text", "text": "prompt"}]}
    model._apply_oauth_billing(payload)
    model._apply_oauth_billing(payload)
    billing_count = sum(1 for b in payload["system"] if isinstance(b, dict) and OAUTH_BILLING_HEADER in b.get("text", ""))
    assert billing_count == 1


def test_billing_moved_to_first_if_not_already_first(model):
    """Billing block already present but not first — must be normalized to index 0."""
    payload = {
        "system": [
            {"type": "text", "text": "other block"},
            _billing_block(),
        ]
    }
    model._apply_oauth_billing(payload)
    assert payload["system"][0] == _billing_block()
    assert len([b for b in payload["system"] if OAUTH_BILLING_HEADER in b.get("text", "")]) == 1


def test_billing_string_with_header_collapsed_to_single_block(model):
    """If system is a string that already contains the billing header, collapse to one block."""
    payload = {"system": OAUTH_BILLING_HEADER}
    model._apply_oauth_billing(payload)
    assert payload["system"] == [_billing_block()]


# ---------------------------------------------------------------------------
# metadata.user_id
# ---------------------------------------------------------------------------


def test_metadata_user_id_added_when_missing(model):
    payload: dict = {}
    model._apply_oauth_billing(payload)
    assert "metadata" in payload
    user_id = json.loads(payload["metadata"]["user_id"])
    assert "device_id" in user_id
    assert "session_id" in user_id
    assert user_id["account_uuid"] == "kiwi"


def test_metadata_user_id_not_overwritten_if_present(model):
    payload = {"metadata": {"user_id": "existing-value"}}
    model._apply_oauth_billing(payload)
    assert payload["metadata"]["user_id"] == "existing-value"


def test_metadata_non_dict_replaced_with_dict(model):
    """Non-dict metadata (e.g. None or a string) should be replaced, not crash."""
    for bad_value in (None, "string-metadata", 42):
        payload = {"metadata": bad_value}
        model._apply_oauth_billing(payload)
        assert isinstance(payload["metadata"], dict)
        assert "user_id" in payload["metadata"]


def test_sync_create_strips_cache_control_from_oauth_payload(model):
    payload = {
        "system": [{"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}],
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": "hi", "cache_control": {"type": "ephemeral"}}],
            }
        ],
        "tools": [{"name": "demo", "input_schema": {"type": "object"}, "cache_control": {"type": "ephemeral"}}],
    }

    with mock.patch.object(model._client.messages, "create", return_value=object()) as create:
        model._create(payload)

    sent_payload = create.call_args.kwargs
    assert "cache_control" not in sent_payload["system"][0]
    assert "cache_control" not in sent_payload["messages"][0]["content"][0]
    assert "cache_control" not in sent_payload["tools"][0]


def test_apply_prompt_caching_skips_thinking_blocks():
    """Reproduces the API 400 from Telegram/Kalshi: cache_control must NOT be
    attached to `thinking` or `redacted_thinking` blocks — Anthropic rejects them.
    """
    m = _make_caching_model()
    payload = {
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "hi"}]},
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "let me think...", "signature": "sig"},
                    {"type": "text", "text": "hello!"},
                ],
            },
            {"role": "user", "content": [{"type": "text", "text": "what's my cash?"}]},
        ]
    }

    m._apply_prompt_caching(payload)

    thinking_block = payload["messages"][1]["content"][0]
    text_block = payload["messages"][1]["content"][1]
    assert thinking_block["type"] == "thinking"
    assert "cache_control" not in thinking_block, "cache_control on thinking block is rejected by Anthropic API"
    assert text_block.get("cache_control") == {"type": "ephemeral"}


def test_apply_prompt_caching_skips_redacted_thinking_blocks():
    m = _make_caching_model()
    payload = {
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {"type": "redacted_thinking", "data": "encrypted-blob"},
                    {"type": "text", "text": "ok"},
                ],
            },
        ]
    }

    m._apply_prompt_caching(payload)

    redacted_block = payload["messages"][0]["content"][0]
    text_block = payload["messages"][0]["content"][1]
    assert "cache_control" not in redacted_block
    assert text_block.get("cache_control") == {"type": "ephemeral"}, "skip must be surgical: sibling text block still gets cache_control"


def test_apply_prompt_caching_respects_4_breakpoint_limit():
    """Anthropic API rejects requests with more than 4 cache_control markers.
    A heavy but realistic agent payload (multi-block system + tools + multi-block
    messages) must never exceed the limit.
    """
    m = _make_caching_model()
    payload = {
        "system": [
            {"type": "text", "text": "system part 1"},
            {"type": "text", "text": "system part 2"},
        ],
        "tools": [
            {"name": "tool1", "input_schema": {"type": "object"}},
            {"name": "tool2", "input_schema": {"type": "object"}},
        ],
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "msg0"}]},
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "...", "signature": "sig"},
                    {"type": "text", "text": "reply 1"},
                    {"type": "tool_use", "id": "tu1", "name": "tool1", "input": {}},
                ],
            },
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu1", "content": "result"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "reply 2"}]},
            {"role": "user", "content": [{"type": "text", "text": "what's my cash?"}]},
        ],
    }

    m._apply_prompt_caching(payload)

    total = _count_cache_breakpoints(payload)
    assert total <= 4, f"expected ≤4 cache_control breakpoints, got {total}"


def test_apply_prompt_caching_places_breakpoints_at_useful_boundaries():
    """Breakpoints should land at the end of the system prompt, the last tool def,
    and the last cacheable block of the most recent messages — not be sprayed
    across every block."""
    m = _make_caching_model()
    m.prompt_cache_size = 2  # leaves budget for 2 message breakpoints
    payload = {
        "system": [
            {"type": "text", "text": "first system block"},
            {"type": "text", "text": "last system block"},
        ],
        "tools": [
            {"name": "tool1", "input_schema": {"type": "object"}},
            {"name": "tool2", "input_schema": {"type": "object"}},
        ],
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "old"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "older reply"}]},
            {"role": "user", "content": [{"type": "text", "text": "recent"}]},
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "...", "signature": "sig"},
                    {"type": "text", "text": "most recent reply"},
                ],
            },
        ],
    }

    m._apply_prompt_caching(payload)

    # System: only the LAST text block carries the marker.
    assert "cache_control" not in payload["system"][0]
    assert payload["system"][1].get("cache_control") == {"type": "ephemeral"}
    # Tools: only the last tool def.
    assert "cache_control" not in payload["tools"][0]
    assert payload["tools"][1].get("cache_control") == {"type": "ephemeral"}
    # Messages: only the last 2 are marked. Older ones untouched.
    assert "cache_control" not in payload["messages"][0]["content"][0]
    assert "cache_control" not in payload["messages"][1]["content"][0]
    assert payload["messages"][2]["content"][0].get("cache_control") == {"type": "ephemeral"}
    # Last message: thinking skipped, text gets the marker.
    assert "cache_control" not in payload["messages"][3]["content"][0]
    assert payload["messages"][3]["content"][1].get("cache_control") == {"type": "ephemeral"}
    # Total ≤ 4.
    assert _count_cache_breakpoints(payload) == 4


def test_apply_prompt_caching_handles_message_with_only_thinking_block():
    """If a message has no cacheable blocks (all thinking), no breakpoint is placed."""
    m = _make_caching_model()
    payload = {
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "...", "signature": "sig"},
                ],
            },
        ]
    }

    m._apply_prompt_caching(payload)

    assert "cache_control" not in payload["messages"][0]["content"][0]
    assert _count_cache_breakpoints(payload) == 0


def test_async_create_strips_cache_control_from_oauth_payload(model):
    payload = {
        "system": [{"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}],
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": "hi", "cache_control": {"type": "ephemeral"}}],
            }
        ],
        "tools": [{"name": "demo", "input_schema": {"type": "object"}, "cache_control": {"type": "ephemeral"}}],
    }

    with mock.patch.object(model._async_client.messages, "create", new=mock.AsyncMock(return_value=object())) as create:
        asyncio.run(model._acreate(payload))

    sent_payload = create.call_args.kwargs
    assert "cache_control" not in sent_payload["system"][0]
    assert "cache_control" not in sent_payload["messages"][0]["content"][0]
    assert "cache_control" not in sent_payload["tools"][0]
