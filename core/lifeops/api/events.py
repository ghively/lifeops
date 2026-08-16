"""WebSocket event stream — live change notifications for the Console.

The transport half of ``lifeops.events.EventBus``: each connected client gets
a subscription queue and receives every published event as a JSON object
(``{"type": "task_changed", ...}``). In-process only; no broker (BUILD_SPEC
section 106).

Clients authenticate with the same bearer token as the HTTP API, passed as
``?token=`` because browser WebSocket APIs cannot set headers. When Console
auth is disabled (no password configured), the stream is open like the rest
of the API.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

#: Policy-close code for an unauthenticated stream (4400s are application-defined).
_WS_UNAUTHENTICATED = 4401


def _bearer_token(websocket: WebSocket) -> str | None:
    header = websocket.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return websocket.query_params.get("token")


@router.websocket("/events")
async def events_stream(websocket: WebSocket) -> None:
    container: Any = websocket.app.state.container
    auth = getattr(container, "auth", None)
    if auth is not None and auth.enabled and not auth.validate(_bearer_token(websocket)):
        await websocket.close(code=_WS_UNAUTHENTICATED)
        return

    await websocket.accept()
    queue = container.events.subscribe()
    try:
        while True:
            # Wait on the next event *and* the next client frame so a
            # disconnect is noticed promptly instead of on the next publish.
            incoming = asyncio.ensure_future(websocket.receive_text())
            outgoing = asyncio.ensure_future(queue.get())
            done, pending = await asyncio.wait(
                {incoming, outgoing}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            if incoming in done:
                # Client frames carry no meaning yet; a disconnect raises.
                incoming.result()
            if outgoing in done:
                await websocket.send_json(outgoing.result())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        container.events.unsubscribe(queue)
