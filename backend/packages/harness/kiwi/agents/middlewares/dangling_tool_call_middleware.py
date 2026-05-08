"""Middleware to repair tool_call/ToolMessage mismatches before model invocation.

- AIMessage tool_calls with no matching ToolMessage get a synthetic error
  ToolMessage inserted right after them.
- ToolMessages with no matching AIMessage tool_call are dropped.

Uses wrap_model_call so patches land at the correct positions instead of being
appended via the add_messages reducer.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse
from langchain_core.messages import ToolMessage

logger = logging.getLogger(__name__)


class DanglingToolCallMiddleware(AgentMiddleware[AgentState]):
    """Inserts placeholder ToolMessages for dangling tool calls before model invocation.

    Scans the message history for AIMessages whose tool_calls lack corresponding
    ToolMessages, and injects synthetic error responses immediately after the
    offending AIMessage so the LLM receives a well-formed conversation.
    """

    @staticmethod
    def _message_tool_calls(msg) -> list[dict]:
        """Return normalized tool calls from structured fields or raw provider payloads."""
        tool_calls = getattr(msg, "tool_calls", None) or []
        if tool_calls:
            return list(tool_calls)

        raw_tool_calls = (getattr(msg, "additional_kwargs", None) or {}).get("tool_calls") or []
        normalized: list[dict] = []
        for raw_tc in raw_tool_calls:
            if not isinstance(raw_tc, dict):
                continue

            function = raw_tc.get("function")
            name = raw_tc.get("name")
            if not name and isinstance(function, dict):
                name = function.get("name")

            args = raw_tc.get("args", {})
            if not args and isinstance(function, dict):
                raw_args = function.get("arguments")
                if isinstance(raw_args, str):
                    try:
                        parsed_args = json.loads(raw_args)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        parsed_args = {}
                    args = parsed_args if isinstance(parsed_args, dict) else {}

            normalized.append(
                {
                    "id": raw_tc.get("id"),
                    "name": name or "unknown",
                    "args": args if isinstance(args, dict) else {},
                }
            )

        return normalized

    def _build_patched_messages(self, messages: list) -> list | None:
        """Repair tool_call/ToolMessage mismatches; return ``None`` if balanced."""
        ai_tool_call_ids: set[str] = set()
        tool_msg_ids: set[str] = set()
        for msg in messages:
            if getattr(msg, "type", None) == "ai":
                for tc in self._message_tool_calls(msg):
                    tc_id = tc.get("id")
                    if tc_id:
                        ai_tool_call_ids.add(tc_id)
            elif isinstance(msg, ToolMessage) and msg.tool_call_id:
                tool_msg_ids.add(msg.tool_call_id)

        orphan_ids = tool_msg_ids - ai_tool_call_ids
        dangling_ids = ai_tool_call_ids - tool_msg_ids
        if not orphan_ids and not dangling_ids:
            return None

        patched: list = []
        injected_ids: set[str] = set()
        for msg in messages:
            if isinstance(msg, ToolMessage) and msg.tool_call_id in orphan_ids:
                continue
            patched.append(msg)
            if getattr(msg, "type", None) != "ai":
                continue
            for tc in self._message_tool_calls(msg):
                tc_id = tc.get("id")
                if tc_id in dangling_ids and tc_id not in injected_ids:
                    patched.append(
                        ToolMessage(
                            content="[Tool call was interrupted and did not return a result.]",
                            tool_call_id=tc_id,
                            name=tc.get("name", "unknown"),
                            status="error",
                        )
                    )
                    injected_ids.add(tc_id)

        if orphan_ids:
            logger.warning(f"Dropping {len(orphan_ids)} orphan ToolMessage(s) with no matching AIMessage tool_call")
        if injected_ids:
            logger.warning(f"Injecting {len(injected_ids)} placeholder ToolMessage(s) for dangling tool calls")
        return patched

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        patched = self._build_patched_messages(request.messages)
        if patched is not None:
            request = request.override(messages=patched)
        return handler(request)

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        patched = self._build_patched_messages(request.messages)
        if patched is not None:
            request = request.override(messages=patched)
        return await handler(request)
