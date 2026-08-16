"""Structured logging with trace propagation (BUILD_SPEC section 78).

Start simple: JSON lines, trace IDs, and semantic operation names. That is
enough to answer "why did Hermes do that?" without standing up Grafana, Tempo,
and Prometheus for a single-user system (section 105).

Trace context lives in a ContextVar so it follows async work without every
function taking a trace argument.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

# --- trace context ----------------------------------------------------------

_trace_id: ContextVar[str | None] = ContextVar("lifeops_trace_id", default=None)
_client_id: ContextVar[str | None] = ContextVar("lifeops_client_id", default=None)
_session_id: ContextVar[str | None] = ContextVar("lifeops_session_id", default=None)

#: Field names whose values are never written to a log line, at any level.
#: BUILD_SPEC section 24: never log API keys, tokens, cookies, passwords,
#: card data, or MFA codes.
_REDACTED_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "token",
        "bot_token",
        "access_token",
        "refresh_token",
        "password",
        "secret",
        "cookie",
        "cookies",
        "authorization",
        "card_number",
        "cvv",
        "mfa_code",
        "otp",
    }
)

_REDACTED = "<redacted>"


def new_trace_id() -> str:
    return uuid.uuid4().hex


def current_trace_id() -> str | None:
    return _trace_id.get()


@contextmanager
def trace_context(
    *,
    trace_id: str | None = None,
    client_id: str | None = None,
    session_id: str | None = None,
) -> Iterator[str]:
    """Bind trace identifiers for the duration of a request."""
    resolved = trace_id or new_trace_id()
    tokens = [
        _trace_id.set(resolved),
        _client_id.set(client_id),
        _session_id.set(session_id),
    ]
    try:
        yield resolved
    finally:
        _trace_id.reset(tokens[0])
        _client_id.reset(tokens[1])
        _session_id.reset(tokens[2])


def redact(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip sensitive values from a structured payload, recursively."""
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        if key.lower() in _REDACTED_KEYS:
            cleaned[key] = _REDACTED
        elif isinstance(value, dict):
            cleaned[key] = redact(value)
        else:
            cleaned[key] = value
    return cleaned


# --- formatter --------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    _RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
        "message",
        "asctime",
        "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "component": record.name,
            "message": record.getMessage(),
        }

        for field, var in (
            ("trace_id", _trace_id),
            ("client_id", _client_id),
            ("session_id", _session_id),
        ):
            value = var.get()
            if value:
                payload[field] = value

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in self._RESERVED and not key.startswith("_")
        }
        if extras:
            payload.update(redact(extras))

        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(*, level: str = "INFO", json_output: bool = True) -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())

    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stderr)
    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )
    root.addHandler(handler)

    # The Bolt driver logs every query at DEBUG, which would put personal
    # values into the log stream.
    logging.getLogger("neo4j").setLevel(logging.WARNING)


# --- semantic operations ----------------------------------------------------

logger = logging.getLogger("lifeops.operation")


@contextmanager
def operation(name: str, **fields: Any) -> Iterator[dict[str, Any]]:
    """Time and log one semantic operation, e.g. ``task.transition``.

    Yields a mutable dict; anything added to it is logged on completion, which
    lets a caller record a result it does not know until the work is done.
    """
    started = time.perf_counter()
    context: dict[str, Any] = dict(fields)
    try:
        yield context
    except Exception as exc:
        logger.warning(
            "%s failed", name,
            extra={
                "operation": name,
                "result": "error",
                "error_type": type(exc).__name__,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                **redact(context),
            },
        )
        raise
    else:
        logger.info(
            "%s", name,
            extra={
                "operation": name,
                "result": "ok",
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                **redact(context),
            },
        )
