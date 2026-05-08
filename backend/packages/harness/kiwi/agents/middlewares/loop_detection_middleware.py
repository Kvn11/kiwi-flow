"""Middleware to detect and break repetitive tool call loops.

P0 safety: prevents the agent from calling the same tool with the same
arguments indefinitely until the recursion limit kills the run.

Detection strategy:
  1. After each model response, hash the tool calls (name + args).
  2. Track recent hashes in a sliding window.
  3. If the same hash appears >= warn_threshold times, inject a
     "you are repeating yourself — wrap up" system message (once per hash).
  4. If it appears >= hard_limit times, strip all tool_calls from the
     response so the agent is forced to produce a final text answer.
"""

import hashlib
import json
import logging
import threading
from collections import OrderedDict, defaultdict, deque
from copy import deepcopy
from typing import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

# Defaults — can be overridden via constructor
_DEFAULT_WARN_THRESHOLD = 3  # inject warning after 3 identical calls
_DEFAULT_HARD_LIMIT = 5  # force-stop after 5 identical calls
_DEFAULT_WINDOW_SIZE = 20  # track last N tool calls
_DEFAULT_MAX_TRACKED_THREADS = 100  # LRU eviction limit
_DEFAULT_TOOL_FREQ_WARN = 30  # warn after 30 same-name calls within window
_DEFAULT_TOOL_FREQ_HARD_LIMIT = 50  # force-stop after 50 same-name calls within window
_DEFAULT_TOOL_FREQ_WINDOW = 80  # sliding window of recent tool calls per thread
_DEFAULT_TOOL_FREQ_DIVERSITY_FLOOR = 0.5  # if distinct/count >= floor, treat as research, not loop


def _normalize_tool_call_args(raw_args: object) -> tuple[dict, str | None]:
    """Normalize tool call args to a dict plus an optional fallback key.

    Some providers serialize ``args`` as a JSON string instead of a dict.
    We defensively parse those cases so loop detection does not crash while
    still preserving a stable fallback key for non-dict payloads.
    """
    if isinstance(raw_args, dict):
        return raw_args, None

    if isinstance(raw_args, str):
        try:
            parsed = json.loads(raw_args)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}, raw_args

        if isinstance(parsed, dict):
            return parsed, None
        return {}, json.dumps(parsed, sort_keys=True, default=str)

    if raw_args is None:
        return {}, None

    return {}, json.dumps(raw_args, sort_keys=True, default=str)


def _stable_tool_key(name: str, args: dict, fallback_key: str | None) -> str:
    """Derive a stable key from salient args without overfitting to noise."""
    if name == "read_file" and fallback_key is None:
        path = args.get("path") or ""
        start_line = args.get("start_line")
        end_line = args.get("end_line")

        bucket_size = 200
        try:
            start_line = int(start_line) if start_line is not None else 1
        except (TypeError, ValueError):
            start_line = 1
        try:
            end_line = int(end_line) if end_line is not None else start_line
        except (TypeError, ValueError):
            end_line = start_line

        start_line, end_line = sorted((start_line, end_line))
        bucket_start = max(start_line, 1)
        bucket_end = max(end_line, 1)
        bucket_start = (bucket_start - 1) // bucket_size
        bucket_end = (bucket_end - 1) // bucket_size
        return f"{path}:{bucket_start}-{bucket_end}"

    # write_file / str_replace are content-sensitive: same path may be updated
    # with different payloads during iteration. Using only salient fields (path)
    # can collapse distinct calls, so we hash full args to reduce false positives.
    if name in {"write_file", "str_replace"}:
        if fallback_key is not None:
            return fallback_key
        return json.dumps(args, sort_keys=True, default=str)

    salient_fields = ("path", "url", "query", "command", "pattern", "glob", "cmd")
    stable_args = {field: args[field] for field in salient_fields if args.get(field) is not None}
    if stable_args:
        return json.dumps(stable_args, sort_keys=True, default=str)

    if fallback_key is not None:
        return fallback_key

    return json.dumps(args, sort_keys=True, default=str)


def _typed_tool_calls(tool_calls: list[dict]) -> list[tuple[str, str]]:
    """Normalize raw tool calls to ``(name, stable_key)`` tuples."""
    typed: list[tuple[str, str]] = []
    for tc in tool_calls:
        name = tc.get("name", "")
        args, fallback_key = _normalize_tool_call_args(tc.get("args", {}))
        typed.append((name, _stable_tool_key(name, args, fallback_key)))
    return typed


def _hash_typed_calls(typed: list[tuple[str, str]]) -> str:
    """Order-independent hash of a multiset of ``(name, key)`` tuples."""
    normalized = sorted(f"{name}:{key}" for name, key in typed)
    blob = json.dumps(normalized, sort_keys=True, default=str)
    return hashlib.md5(blob.encode()).hexdigest()[:12]


def _hash_tool_calls(tool_calls: list[dict]) -> str:
    """Deterministic hash of a multiset of tool calls (order-independent)."""
    return _hash_typed_calls(_typed_tool_calls(tool_calls))


_WARNING_MSG = "[LOOP DETECTED] You are repeating the same tool calls. Stop calling tools and produce your final answer now. If you cannot complete the task, summarize what you accomplished so far."

_TOOL_FREQ_WARNING_MSG = (
    "[LOOP DETECTED] You have called {tool_name} {count} times without producing a final answer. Stop calling tools and produce your final answer now. If you cannot complete the task, summarize what you accomplished so far."
)

_HARD_STOP_MSG = "[FORCED STOP] Repeated tool calls exceeded the safety limit. Producing final answer with results collected so far."

_TOOL_FREQ_HARD_STOP_MSG = "[FORCED STOP] Tool {tool_name} called {count} times — exceeded the per-tool safety limit. Producing final answer with results collected so far."


class LoopDetectionMiddleware(AgentMiddleware[AgentState]):
    """Detects and breaks repetitive tool call loops.

    Two layers of detection:

    1. **Hash-based** — identical tool call *sets* repeat in a sliding window
       of recent assistant turns.
    2. **Frequency-based** — same tool *name* appears many times in a sliding
       window of recent calls, AND those calls have low argument diversity
       (so genuine breadth-first research over many distinct files isn't
       flagged as a loop).

    Args:
        warn_threshold: Number of identical tool call sets before injecting
            a warning message. Default: 3.
        hard_limit: Number of identical tool call sets before stripping
            tool_calls entirely. Default: 5.
        window_size: Size of the sliding window for tracking calls.
            Default: 20.
        max_tracked_threads: Maximum number of threads to track before
            evicting the least recently used. Default: 100.
        tool_freq_warn: Number of same-name calls within the frequency window
            before injecting a frequency warning. Default: 30.
        tool_freq_hard_limit: Number of same-name calls within the window
            before forcing a stop. Default: 50.
        tool_freq_window: Sliding window size for the frequency layer (last
            N tool calls per thread, across all tool names). Default: 80.
        tool_freq_diversity_floor: If ``distinct(stable_keys) / count`` for a
            tool name in the window is at or above this ratio, the calls are
            treated as legitimate breadth-first work and no warning fires.
            Default: 0.5 (i.e. fire only when at least half the calls are
            repeats of one another).
    """

    def __init__(
        self,
        warn_threshold: int = _DEFAULT_WARN_THRESHOLD,
        hard_limit: int = _DEFAULT_HARD_LIMIT,
        window_size: int = _DEFAULT_WINDOW_SIZE,
        max_tracked_threads: int = _DEFAULT_MAX_TRACKED_THREADS,
        tool_freq_warn: int = _DEFAULT_TOOL_FREQ_WARN,
        tool_freq_hard_limit: int = _DEFAULT_TOOL_FREQ_HARD_LIMIT,
        tool_freq_window: int = _DEFAULT_TOOL_FREQ_WINDOW,
        tool_freq_diversity_floor: float = _DEFAULT_TOOL_FREQ_DIVERSITY_FLOOR,
    ):
        super().__init__()
        if tool_freq_window < tool_freq_warn:
            raise ValueError("tool_freq_window must be >= tool_freq_warn")
        if not 0.0 <= tool_freq_diversity_floor <= 1.0:
            raise ValueError("tool_freq_diversity_floor must be in [0.0, 1.0]")

        self.warn_threshold = warn_threshold
        self.hard_limit = hard_limit
        self.window_size = window_size
        self.max_tracked_threads = max_tracked_threads
        self.tool_freq_warn = tool_freq_warn
        self.tool_freq_hard_limit = tool_freq_hard_limit
        self.tool_freq_window = tool_freq_window
        self.tool_freq_diversity_floor = tool_freq_diversity_floor
        self._lock = threading.Lock()
        # Per-thread tracking using OrderedDict for LRU eviction
        self._history: OrderedDict[str, list[str]] = OrderedDict()
        self._warned: dict[str, set[str]] = defaultdict(set)
        # Per-thread sliding window of recent (tool_name, stable_key) pairs.
        # Capped at tool_freq_window so it self-clears as the conversation
        # advances — long-running threads don't accumulate stale counts.
        self._tool_history: dict[str, deque[tuple[str, str]]] = {}
        self._tool_freq_warned: dict[str, set[str]] = defaultdict(set)

    def _get_thread_id(self, runtime: Runtime) -> str:
        """Extract thread_id from runtime context for per-thread tracking."""
        thread_id = runtime.context.get("thread_id") if runtime.context else None
        if thread_id:
            return thread_id
        return "default"

    def _evict_if_needed(self) -> None:
        """Evict least recently used threads if over the limit.

        Must be called while holding self._lock.
        """
        while len(self._history) > self.max_tracked_threads:
            evicted_id, _ = self._history.popitem(last=False)
            self._warned.pop(evicted_id, None)
            self._tool_history.pop(evicted_id, None)
            self._tool_freq_warned.pop(evicted_id, None)
            logger.debug("Evicted loop tracking for thread %s (LRU)", evicted_id)

    def _track_and_check(self, state: AgentState, runtime: Runtime) -> tuple[str | None, bool]:
        """Track tool calls and check for loops.

        Two detection layers:
          1. **Hash-based** (existing): catches identical tool call sets.
          2. **Frequency-based** (new): catches the same *tool type* being
             called many times with varying arguments (e.g. ``read_file``
             on 40 different files).

        Returns:
            (warning_message_or_none, should_hard_stop)
        """
        messages = state.get("messages", [])
        if not messages:
            return None, False

        last_msg = messages[-1]
        if getattr(last_msg, "type", None) != "ai":
            return None, False

        tool_calls = getattr(last_msg, "tool_calls", None)
        if not tool_calls:
            return None, False

        thread_id = self._get_thread_id(runtime)
        typed_calls = _typed_tool_calls(tool_calls)
        call_hash = _hash_typed_calls(typed_calls)

        with self._lock:
            # Touch / create entry (move to end for LRU)
            if thread_id in self._history:
                self._history.move_to_end(thread_id)
            else:
                self._history[thread_id] = []
                self._evict_if_needed()

            history = self._history[thread_id]
            history.append(call_hash)
            if len(history) > self.window_size:
                history[:] = history[-self.window_size :]

            count = history.count(call_hash)
            tool_names = [tc.get("name", "?") for tc in tool_calls]

            # --- Layer 1: hash-based (identical call sets) ---
            if count >= self.hard_limit:
                logger.error(
                    "Loop hard limit reached — forcing stop",
                    extra={
                        "thread_id": thread_id,
                        "call_hash": call_hash,
                        "count": count,
                        "tools": tool_names,
                    },
                )
                return _HARD_STOP_MSG, True

            if count >= self.warn_threshold:
                warned = self._warned[thread_id]
                if call_hash not in warned:
                    warned.add(call_hash)
                    logger.warning(
                        "Repetitive tool calls detected — injecting warning",
                        extra={
                            "thread_id": thread_id,
                            "call_hash": call_hash,
                            "count": count,
                            "tools": tool_names,
                        },
                    )
                    return _WARNING_MSG, False

            # --- Layer 2: per-tool-type frequency in sliding window with diversity gate ---
            window = self._tool_history.get(thread_id)
            if window is None:
                window = deque(maxlen=self.tool_freq_window)
                self._tool_history[thread_id] = window
            for name, key in typed_calls:
                if name:
                    window.append((name, key))

            return self._check_tool_frequency(thread_id, window)

    def _check_tool_frequency(
        self,
        thread_id: str,
        window: deque[tuple[str, str]],
    ) -> tuple[str | None, bool]:
        """Tally same-name calls within the window, gated on argument diversity."""
        keys_by_name: dict[str, list[str]] = defaultdict(list)
        for name, key in window:
            keys_by_name[name].append(key)

        for name, keys in keys_by_name.items():
            count = len(keys)
            if count < self.tool_freq_warn:
                continue
            distinct = len(set(keys))
            diversity_ratio = distinct / count
            if diversity_ratio >= self.tool_freq_diversity_floor:
                # Broad research / breadth-first work, not a loop.
                continue

            if count >= self.tool_freq_hard_limit:
                logger.error(
                    "Tool frequency hard limit reached — forcing stop",
                    extra={
                        "thread_id": thread_id,
                        "tool_name": name,
                        "count": count,
                        "distinct": distinct,
                        "diversity_ratio": round(diversity_ratio, 3),
                    },
                )
                return _TOOL_FREQ_HARD_STOP_MSG.format(tool_name=name, count=count), True

            warned = self._tool_freq_warned[thread_id]
            if name in warned:
                continue
            warned.add(name)
            logger.warning(
                "Tool frequency warning — repetitive calls to same tool type",
                extra={
                    "thread_id": thread_id,
                    "tool_name": name,
                    "count": count,
                    "distinct": distinct,
                    "diversity_ratio": round(diversity_ratio, 3),
                },
            )
            return _TOOL_FREQ_WARNING_MSG.format(tool_name=name, count=count), False

        return None, False

    @staticmethod
    def _append_text(content: str | list | None, text: str) -> str | list:
        """Append *text* to AIMessage content, handling str, list, and None.

        When content is a list of content blocks (e.g. Anthropic thinking mode),
        we append a new ``{"type": "text", ...}`` block instead of concatenating
        a string to a list, which would raise ``TypeError``.
        """
        if content is None:
            return text
        if isinstance(content, list):
            return [*content, {"type": "text", "text": f"\n\n{text}"}]
        if isinstance(content, str):
            return content + f"\n\n{text}"
        # Fallback: coerce unexpected types to str to avoid TypeError
        return str(content) + f"\n\n{text}"

    @staticmethod
    def _build_hard_stop_update(last_msg, content: str | list) -> dict:
        """Clear tool-call metadata so forced-stop messages serialize as plain assistant text."""
        update = {
            "tool_calls": [],
            "content": content,
        }

        additional_kwargs = dict(getattr(last_msg, "additional_kwargs", {}) or {})
        for key in ("tool_calls", "function_call"):
            additional_kwargs.pop(key, None)
        update["additional_kwargs"] = additional_kwargs

        response_metadata = deepcopy(getattr(last_msg, "response_metadata", {}) or {})
        if response_metadata.get("finish_reason") == "tool_calls":
            response_metadata["finish_reason"] = "stop"
        update["response_metadata"] = response_metadata

        return update

    def _apply(self, state: AgentState, runtime: Runtime) -> dict | None:
        warning, hard_stop = self._track_and_check(state, runtime)

        if hard_stop:
            # Strip tool_calls from the last AIMessage to force text output
            messages = state.get("messages", [])
            last_msg = messages[-1]
            content = self._append_text(last_msg.content, warning or _HARD_STOP_MSG)
            stripped_msg = last_msg.model_copy(update=self._build_hard_stop_update(last_msg, content))
            return {"messages": [stripped_msg]}

        if warning:
            # Inject as HumanMessage instead of SystemMessage to avoid
            # Anthropic's "multiple non-consecutive system messages" error.
            # Anthropic models require system messages only at the start of
            # the conversation; injecting one mid-conversation crashes
            # langchain_anthropic's _format_messages(). HumanMessage works
            # with all providers. See #1299.
            return {"messages": [HumanMessage(content=warning)]}

        return None

    @override
    def after_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._apply(state, runtime)

    @override
    async def aafter_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._apply(state, runtime)

    def reset(self, thread_id: str | None = None) -> None:
        """Clear tracking state. If thread_id given, clear only that thread."""
        with self._lock:
            if thread_id:
                self._history.pop(thread_id, None)
                self._warned.pop(thread_id, None)
                self._tool_history.pop(thread_id, None)
                self._tool_freq_warned.pop(thread_id, None)
            else:
                self._history.clear()
                self._warned.clear()
                self._tool_history.clear()
                self._tool_freq_warned.clear()
