"""SSE helpers for agent runtime."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from app.services.agent.models import StreamingEvent

logger = logging.getLogger(__name__)


def format_sse(event: StreamingEvent) -> bytes:
    payload = event.model_dump(exclude_none=True)
    return f"event: {event.type}\ndata: {json.dumps(payload)}\n\n".encode("utf-8")


async def stream_sse(events: AsyncGenerator[StreamingEvent, None]) -> AsyncGenerator[bytes, None]:
    """H66: Wrap SSE streaming with proper CancelledError cleanup."""
    try:
        async for event in events:
            yield format_sse(event)
    except asyncio.CancelledError:
        logger.info("SSE stream cancelled by client, cleaning up")
        # Close the upstream generator if it supports aclose
        if hasattr(events, "aclose"):
            try:
                await events.aclose()
            except Exception:
                pass
        raise
    except Exception:
        logger.error("Unexpected error in SSE stream", exc_info=True)
        raise
