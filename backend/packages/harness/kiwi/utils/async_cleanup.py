"""Async cleanup helpers used by code paths that run inside ``asyncio.run``.

Models created and used inside a worker thread's ``asyncio.run`` (memory
updater, subagent executor) must release their httpx clients before the loop
closes. Otherwise, idle connections in the pool stay bound to the dead loop
and crash subsequent callers in stream cleanup with
``RuntimeError: Event loop is closed``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def aclose_model_async_client(model: Any) -> None:
    """Close a chat model's underlying async HTTP client, best effort.

    Walks the common attribute names used by ``langchain_openai.ChatOpenAI``
    and similar wrappers (``async_client``, then private fallbacks) and calls
    the client's ``aclose`` (preferred) or ``close``. Awaits if the call
    returned a coroutine. Returns silently if no client is found, the close
    method is missing, or the close call raises — this is cleanup, not the
    primary work.
    """
    if model is None:
        return
    for attr in ("async_client", "_async_client", "_client"):
        client = getattr(model, attr, None)
        if client is None:
            continue
        close = getattr(client, "aclose", None) or getattr(client, "close", None)
        if not callable(close):
            continue
        try:
            result = close()
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            logger.debug("Failed to close model async client (%s)", attr, exc_info=True)
        return
