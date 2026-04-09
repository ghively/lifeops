"""System observability endpoints."""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.config import settings
from app.middleware.auth import get_current_user, get_optional_user
from app.middleware.rate_limit import read_rate_limit, write_rate_limit
from app.services.collaboration import collaboration_manager
from app.services.websocket_manager import websocket_manager

# Smoke test imports (lazy to avoid circular)
from app.database.qdrant_client import qdrant_manager
from app.database.sqlite import sqlite_manager

import re
from datetime import datetime

router = APIRouter()
logger = logging.getLogger(__name__)
ALLOWED_LOG_LEVELS = {"debug", "info", "warning", "error", "critical"}

# Nginx combined log format regex
_NGINX_RE = re.compile(
    r'(?P<remote>[\w./:]+) - (?P<remote_user>\S+) '
    r'\[(?P<time>[^\]]+)\] "(?P<method>\w+) (?P<path>\S+) (?P<protocol>[^"]+)" '
    r'(?P<status>\d{3}) (?P<body_bytes>\d+) "(?P<referer>[^"]*)" "(?P<ua>[^"]*)"'
)

_NGINX_LOG_PATH = Path("/var/log/nginx/access.log")


def _parse_nginx_line(line: str) -> dict[str, Any] | None:
    m = _NGINX_RE.match(line.strip())
    if not m:
        return None
    d = m.groupdict()
    try:
        ts = datetime.strptime(d["time"], "%d/%b/%Y:%H:%M:%S %z")
        d["timestamp"] = ts.strftime("%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        d["timestamp"] = d["time"]
    d["status"] = int(d["status"])
    return d


def _read_nginx_error_lines(limit: int = 200) -> list[dict[str, Any]]:
    if not _NGINX_LOG_PATH.exists():
        return []
    entries: list[dict[str, Any]] = []
    try:
        with _NGINX_LOG_PATH.open("rb") as fh:
            fh.seek(0, 2)
            file_size = fh.tell()
            read_size = min(file_size, 1 * 1024 * 1024)
            fh.seek(file_size - read_size)
            fh.readline()  # skip partial
            for raw in fh:
                parsed = _parse_nginx_line(raw.decode("utf-8", errors="replace"))
                if parsed and parsed["status"] >= 400:
                    entries.append(parsed)
    except OSError:
        pass
    return entries[-limit:]


def _read_log_entries(limit: int = 500) -> list[dict[str, Any]]:
    """Read the last *limit* log entries from the structured JSON log file."""
    log_path = Path(settings.log_file_path)
    if not log_path.exists():
        return []

    # Read file in reverse to avoid loading entire file into memory
    entries: list[dict[str, Any]] = []
    try:
        with log_path.open("rb") as fh:
            # Seek near end of file (up to 2MB tail)
            fh.seek(0, 2)
            file_size = fh.tell()
            read_size = min(file_size, 2 * 1024 * 1024)
            fh.seek(file_size - read_size)
            # Skip partial first line
            fh.readline()
            for raw_line in fh:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(entry, dict):
                    entries.append(entry)
    except OSError:
        return []
    # Return only the most recent entries
    return entries[-limit:]


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


@router.get("/logs/unified")
@read_rate_limit
async def get_unified_logs(
    request: Request,
    level: str | None = Query(default=None),
    source: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    current_user: dict = Depends(get_current_user),
):
    """Unified log view: backend app.log + nginx 4xx/5xx access lines."""
    del current_user
    level_filter = level.lower() if level else None
    source_filter = source.lower() if source else None
    search_filter = search.lower() if search else None
    entries: list[dict[str, Any]] = []

    # 1. Backend logs
    for entry in _read_log_entries(limit=limit):
        e_level = str(entry.get("level", "")).lower()
        e_source = str(entry.get("source", "backend")).lower()
        if level_filter and e_level != level_filter:
            continue
        if source_filter and e_source != source_filter:
            continue
        if search_filter and search_filter not in json.dumps(entry, sort_keys=True).lower():
            continue
        entries.append({
            "timestamp": entry.get("timestamp"),
            "level": e_level,
            "source": e_source or "backend",
            "message": entry.get("message", ""),
            "logger": entry.get("logger"),
            "request_id": entry.get("request_id"),
            "data": entry,
        })

    # 2. Nginx access logs (4xx/5xx)
    for parsed in _read_nginx_error_lines(limit=limit):
        e_level = "error" if parsed["status"] >= 500 else "warning"
        if level_filter and e_level != level_filter:
            continue
        if source_filter and "nginx" != source_filter:
            continue
        if search_filter and search_filter not in json.dumps(parsed, sort_keys=True).lower():
            continue
        entries.append({
            "timestamp": parsed["timestamp"],
            "level": e_level,
            "source": "nginx",
            "message": f'{parsed["method"]} {parsed["path"]} → {parsed["status"]}',
            "logger": "access",
            "data": parsed,
        })

    entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return {"logs": entries[:limit], "count": min(len(entries), limit)}


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

    ALLOWED_LOG_LEVELS = {"debug", "info", "warning", "error", "critical"}
    safe_level = level if level in ALLOWED_LOG_LEVELS else "error"
    frontend_logger = logging.getLogger(f"frontend.{component}")
    log_method = getattr(frontend_logger, safe_level, frontend_logger.error)
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


@router.get("/smoke-test")
@read_rate_limit
async def smoke_test(
    request: Request,
    current_user: dict | None = Depends(get_optional_user),
):
    """Lightweight integration smoke test — verifies all core subsystems.

    Designed to complete in under 5 seconds. Each check is independent.
    Returns structured pass/fail per component.
    """
    del current_user
    results: dict[str, dict[str, Any]] = {}
    overall_start = time.monotonic()

    # 1. SQLite — write + read a test row
    try:
        import sqlite3
        db_path = settings.data_dir + "/knowledge_os.db"
        conn = sqlite3.connect(db_path, timeout=3)
        cur = conn.cursor()
        test_id = str(uuid.uuid4())[:8]
        cur.execute(
            "CREATE TABLE IF NOT EXISTS _smoke_test (id TEXT PRIMARY KEY, ts TEXT)"
        )
        cur.execute(
            "INSERT OR REPLACE INTO _smoke_test (id, ts) VALUES (?, datetime('now'))",
            (test_id,),
        )
        cur.execute("SELECT ts FROM _smoke_test WHERE id = ?", (test_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            results["sqlite"] = {"status": "pass", "message": f"write+read OK (id={test_id})"}
        else:
            results["sqlite"] = {"status": "fail", "message": "write succeeded but read returned nothing"}
    except Exception as exc:
        logger.error("Smoke test: sqlite failed", extra={"error": str(exc)})
        results["sqlite"] = {"status": "fail", "message": str(exc)}

    # 2. Qdrant — verify collections exist and search works
    try:
        client = qdrant_manager.get_client()
        collections = client.get_collections().collections
        collection_names = [c.name for c in collections]
        if not collection_names:
            results["qdrant"] = {"status": "fail", "message": "no collections found"}
        else:
            # Try a search on the first collection (empty query vector)
            test_col = collection_names[0]
            info = client.get_collection(test_col)
            vec_size = 0
            cfg = info.config.params.vectors
            if isinstance(cfg, dict):
                vec_size = cfg.get("size", 0)
            elif cfg is not None:
                vec_size = getattr(cfg, "size", 0)
            if vec_size > 0:
                client.search(test_col, query_vector=[0.0] * vec_size, limit=1)
            results["qdrant"] = {
                "status": "pass",
                "message": f"{len(collection_names)} collections, search on '{test_col}' OK",
            }
    except Exception as exc:
        logger.error("Smoke test: qdrant failed", extra={"error": str(exc)})
        results["qdrant"] = {"status": "fail", "message": str(exc)}

    # 3. File system permissions on /agents and /data
    try:
        from app.config import AGENTS_ROOT
        agents_ok = Path(AGENTS_ROOT).is_dir() and os.access(AGENTS_ROOT, os.R_OK | os.W_OK)
        data_ok = Path(settings.data_dir).is_dir() and os.access(settings.data_dir, os.R_OK | os.W_OK)
        issues = []
        if not agents_ok:
            issues.append(f"AGENTS_ROOT ({AGENTS_ROOT}) not readable/writable")
        if not data_ok:
            issues.append(f"data_dir ({settings.data_dir}) not readable/writable")
        if issues:
            results["filesystem"] = {"status": "fail", "message": "; ".join(issues)}
        else:
            results["filesystem"] = {"status": "pass", "message": "agents + data dirs OK"}
    except Exception as exc:
        results["filesystem"] = {"status": "fail", "message": str(exc)}

    # 4. LLM/Ollama connectivity (lightweight — just check if port is reachable)
    try:
        import urllib.request
        ollama_url = settings.llm_base_url or "http://localhost:11434"
        # Hit /api/tags with a short timeout — doesn't run any model
        req = urllib.request.Request(
            ollama_url.rstrip("/") + "/api/tags",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            models = json.loads(resp.read().decode())
            model_names = [m.get("name", "?") for m in models.get("models", [])]
            results["llm"] = {
                "status": "pass",
                "message": f"Ollama reachable, {len(model_names)} models available",
            }
    except Exception as exc:
        logger.warning("Smoke test: LLM check failed", extra={"error": str(exc)})
        results["llm"] = {
            "status": "warn",
            "message": f"Ollama not reachable: {exc}",
        }

    # 5. OpenClaw gateway connectivity (if configured)
    try:
        if settings.openclaw_url and settings.openclaw_url != "http://localhost:18789":
            import urllib.request
            req = urllib.request.Request(settings.openclaw_url.rstrip("/") + "/health")
            headers = {}
            if settings.openclaw_token:
                headers["Authorization"] = f"Bearer {settings.openclaw_token}"
            for k, v in headers.items():
                req.add_header(k, v)
            with urllib.request.urlopen(req, timeout=3) as resp:
                results["openclaw"] = {
                    "status": "pass",
                    "message": f"gateway reachable ({resp.status})",
                }
        else:
            results["openclaw"] = {"status": "skip", "message": "not configured (using default URL)"}
    except Exception as exc:
        results["openclaw"] = {"status": "warn", "message": f"gateway unreachable: {exc}"}

    duration_ms = round((time.monotonic() - overall_start) * 1000)
    all_pass = all(r.get("status") in ("pass", "skip") for r in results.values())

    return {
        "status": "pass" if all_pass else "fail",
        "duration_ms": duration_ms,
        "results": results,
    }
