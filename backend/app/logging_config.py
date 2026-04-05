"""Structured logging and lightweight observability helpers."""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog

from app.config import settings


COMPONENT_LOG_LEVELS = {
    "app.routers": logging.INFO,
    "app.services": logging.DEBUG,
    "app.database": logging.WARN,
    "uvicorn.access": logging.WARN,
}


def _rename_event_key(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    event_dict["message"] = event_dict.pop("event", "")
    return event_dict


def _add_source(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    event_dict.setdefault("source", "backend")
    return event_dict


def _drop_color_message_key(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    event_dict.pop("color_message", None)
    return event_dict


def _build_shared_processors() -> list[Any]:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.ExtraAdder(),
        _add_source,
        structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
    ]


def bind_request_context(request_id: str) -> None:
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)


def clear_request_context() -> None:
    structlog.contextvars.clear_contextvars()


class LogBroadcastHandler(logging.Handler):
    """Broadcast JSON log lines to subscribed websocket clients."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            rendered = self.format(record)
            payload = json.loads(rendered)
        except Exception:
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        from app.services.websocket_manager import WebSocketEvents, websocket_manager

        loop.create_task(websocket_manager.broadcast(WebSocketEvents.log_entry(payload)))


def configure_logging() -> None:
    """Configure stdlib logging and structlog once for the process."""
    if getattr(configure_logging, "_configured", False):
        return

    log_path = Path(settings.log_file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    shared_processors = _build_shared_processors()
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            _drop_color_message_key,
            _rename_event_key,
            structlog.processors.JSONRenderer(),
        ],
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            _drop_color_message_key,
            _rename_event_key,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    broadcast_handler = LogBroadcastHandler()
    broadcast_handler.setFormatter(formatter)

    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(broadcast_handler)

    for logger_name, level in COMPONENT_LOG_LEVELS.items():
        logging.getLogger(logger_name).setLevel(level)

    configure_logging._configured = True


@dataclass
class AppMetrics:
    """Small in-memory metrics store for the status endpoint."""

    started_at: float
    request_count: int = 0
    error_count: int = 0

    @classmethod
    def create(cls) -> "AppMetrics":
        return cls(started_at=time.time())

    @property
    def uptime_seconds(self) -> float:
        return max(0.0, time.time() - self.started_at)
