"""In-process change-event bus for live Console updates (BUILD_SPEC section 4).

Deliberately minimal: an in-memory fan-out to WebSocket subscribers. No
external broker — Redis, Kafka, and RabbitMQ are prohibited (section 106), and
a single-user LifeOps process has exactly one publisher and a handful of
Console tabs as subscribers.

Events are *notifications*, not state. A missed event costs the Console one
refetch; it never corrupts anything. Delivery is therefore best-effort: a slow
subscriber's queue fills and events are dropped for that subscriber rather than
back-pressuring a mutation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Event types LifeOpsCore and the configuration surface publish.
TASK_CHANGED = "task_changed"
PREFERENCE_CHANGED = "preference_changed"
PERSON_CHANGED = "person_changed"
CONFIG_CHANGED = "config_changed"
MEMORY_CHANGED = "memory_changed"

#: Per-subscriber queue bound. A Console tab this far behind is reconnected or
#: refetching anyway; dropping beats unbounded memory growth.
_QUEUE_SIZE = 100


class EventBus:
    """Fan-out publisher for change events. Process-local and ephemeral."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_QUEUE_SIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def publish(self, event: dict[str, Any]) -> None:
        """Send an event to every subscriber. Never blocks, never raises."""
        if not self._subscribers:
            return
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.debug(
                    "dropping %s for a slow subscriber", event.get("type", "event")
                )
