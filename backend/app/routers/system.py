"""System observability endpoints."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.config import settings
from app.middleware.auth import get_current_user, get_optional_user
from app.middleware.rate_limit import read_rate_limit, write_rate_limit
from app.services.collaboration import collaboration_manager
from app.services.websocket_manager import websocket_manager

router = APIRouter()
logger = logging.getLogger(__name__)
ALLOWED_LOG_LEVELS = {"debug", "info", "warning", "error", "critical"}


def _read_log_entries() -> list[dict[str, Any]]:
    log_path = Path(settings.log_file_path)
    if not log_path.exists():
        return []

    entries: list[dict[str, Any]] = []
    with log_path.open("r", encoding="utf-8") as log_file:
        for line in log_file:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                entries.append(entry)
    return entries


@router.get("/logs")
@read_rate_limit
async def get_logs(
    request: Request,
    level: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    source: str | None = Query(default=None),
    search: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    """Read and filter structured logs."""
    del current_user

    level_filter = level.lower() if level else None
    source_filter = source.lower() if source else None
    search_filter = search.lower() if search else None

    matches: list[dict[str, Any]] = []
    for entry in reversed(_read_log_entries()):
        entry_level = str(entry.get("level", "")).lower()
        entry_source = str(entry.get("source", "")).lower()
        entry_message = str(entry.get("message", "")).lower()
        entry_logger = str(entry.get("logger", "")).lower()

        if level_filter and entry_level != level_filter:
            continue
        if source_filter and entry_source != source_filter:
            continue
        if search_filter and search_filter not in json.dumps(entry, sort_keys=True).lower():
            continue

        matches.append(
            {
                "timestamp": entry.get("timestamp"),
                "level": entry_level,
                "source": entry_source or "backend",
                "logger": entry_logger,
                "message": entry_message if search_filter else entry.get("message", ""),
                "request_id": entry.get("request_id"),
                "data": entry,
            }
        )
        if len(matches) >= limit:
            break

    for entry in matches:
        if search_filter:
            entry["message"] = entry["data"].get("message", "")

    return {"logs": matches, "count": len(matches)}


@router.post("/logs")
@write_rate_limit
async def ingest_frontend_log(
    payload: dict[str, Any],
    request: Request,
    current_user: dict | None = Depends(get_optional_user),
):
    """Persist warn/error frontend logs through the backend logger. Supports single or batch."""
    del request

    # Batch mode: multiple entries from localStorage flush
    batch = payload.get("batch")
    if isinstance(batch, list) and batch:
        for entry in batch[:100]:  # Cap at 100 per request
            _ingest_single_log(entry, current_user)
        return {"status": "ok", "count": len(batch[:100])}

    _ingest_single_log(payload, current_user)
    return {"status": "ok"}


def _ingest_single_log(payload: dict[str, Any], current_user: dict | None = None):
    level = str(payload.get("level", "error")).lower()
    if level not in ALLOWED_LOG_LEVELS:
        raise HTTPException(status_code=400, detail="Invalid log level")

    component = str(payload.get("component") or "frontend")
    message = str(payload.get("message") or "frontend log")

    extra = {
        "source": str(payload.get("source") or "frontend"),
        "component": component,
        "url": payload.get("url"),
        "user_agent": payload.get("user_agent"),
        "frontend_timestamp": payload.get("timestamp"),
        "frontend_extra": payload.get("extra"),
    }
    if current_user:
        extra["user_id"] = current_user.get("id")

    frontend_logger = logging.getLogger(f"frontend.{component}")
    log_method = getattr(frontend_logger, level, frontend_logger.error)
    log_method(message, extra=extra)


@router.get("/status")
@read_rate_limit
async def get_status(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Return lightweight backend runtime status."""
    del current_user

    metrics = request.app.state.metrics
    websocket_connections = websocket_manager.active_connection_count
    collaboration_connections = collaboration_manager.active_connection_count

    return {
        "version": request.app.version,
        "uptime_seconds": round(metrics.uptime_seconds, 3),
        "request_counts": {
            "total": metrics.request_count,
        },
        "error_counts": {
            "total": metrics.error_count,
        },
        "active_websocket_connections": {
            "system": websocket_connections,
            "collaboration": collaboration_connections,
            "total": websocket_connections + collaboration_connections,
        },
    }
