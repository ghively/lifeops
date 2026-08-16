"""Ephemeral activity buffer (BUILD_SPEC section 21, Phase 1 scope).

An in-memory ring of recent semantic operations, fed by the same
``lifeops.operation`` logger that ``observability.logging.operation`` writes
to. This is *not* the audit log: it survives exactly as long as the process
does, holds at most ``capacity`` entries, and exists so the Activity screen
can show "what just happened". Durable audit arrives in Phase 4 (section 62).
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any

#: Detail fields worth surfacing to the Console. Values like preference
#: values never appear here — ``operation`` fields are identifiers only.
_DETAIL_FIELDS = ("task_id", "person_id", "subject_id", "key")


class ActivityBuffer(logging.Handler):
    """A logging handler that keeps the newest N semantic operations."""

    def __init__(self, *, capacity: int = 200) -> None:
        super().__init__(level=logging.INFO)
        self._records: deque[dict[str, Any]] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        operation = getattr(record, "operation", None)
        if not operation:
            return
        entry: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "operation": operation,
            "result": getattr(record, "result", "ok"),
            "duration_ms": getattr(record, "duration_ms", None),
        }
        client_id = getattr(record, "client_id", None)
        if client_id:
            entry["client_id"] = client_id
        for field in _DETAIL_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                entry[field] = value
        self._records.append(entry)

    def recent(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """Newest first."""
        entries = list(self._records)
        entries.reverse()
        return entries[:limit]


def attach_activity_buffer(capacity: int = 200) -> ActivityBuffer:
    """Create a buffer and subscribe it to the semantic-operation logger."""
    buffer = ActivityBuffer(capacity=capacity)
    logging.getLogger("lifeops.operation").addHandler(buffer)
    return buffer


def detach_activity_buffer(buffer: ActivityBuffer) -> None:
    """Unsubscribe a buffer, e.g. on shutdown so handlers do not accumulate."""
    logging.getLogger("lifeops.operation").removeHandler(buffer)
