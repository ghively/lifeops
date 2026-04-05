"""SSE helpers for agent runtime."""
from __future__ import annotations

import json
from typing import AsyncGenerator

from app.services.agent.models import StreamingEvent


def format_sse(event: StreamingEvent) -> bytes:
    payload = event.model_dump(exclude_none=True)
    return f"event: {event.type}\ndata: {json.dumps(payload)}\n\n".encode("utf-8")


async def stream_sse(events: AsyncGenerator[StreamingEvent, None]) -> AsyncGenerator[bytes, None]:
    async for event in events:
        yield format_sse(event)
