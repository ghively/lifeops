"""Structured logging and trace context (BUILD_SPEC section 78)."""

from lifeops.observability.logging import (
    configure_logging,
    current_trace_id,
    new_trace_id,
    operation,
    trace_context,
)

__all__ = [
    "configure_logging",
    "current_trace_id",
    "new_trace_id",
    "operation",
    "trace_context",
]
