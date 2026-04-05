"""Settings Router - Application settings and configuration."""
import uuid
import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.config import settings as app_settings
from app.database.sqlite import sqlite_manager
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import read_rate_limit, write_rate_limit

router = APIRouter()
logger = logging.getLogger(__name__)

DEFAULT_SETTINGS: Dict[str, Any] = {
    "openclaw_url": app_settings.openclaw_url,
    "openclaw_token": app_settings.openclaw_token,
    "openclaw_enabled": True,
    "backup_snapshots": True,
    "backup_markdown": True,
    "backup_git": False,
    "git_repo_url": app_settings.git_repo_url,
    "snapshot_interval_hours": 24,
    "markdown_export_interval_hours": 168,
    "git_sync_interval_minutes": 30,
    "embedding_model": "all-MiniLM-L6-v2",
    "image_embedding_model": "openai/clip-vit-base-patch32",
    "max_context_tokens": 4000,
    "auto_index": True,
}


async def _load_settings() -> Dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    rows = await sqlite_manager.fetchall("SELECT key, value FROM settings")
    for row in rows:
        settings[row["key"]] = await sqlite_manager.get_setting(row["key"], settings.get(row["key"]))
    return settings


@router.get("")
@read_rate_limit
async def get_settings(request: Request, current_user: dict = Depends(get_current_user)):
    """Get application settings."""
    return await _load_settings()


@router.put("")
@write_rate_limit
async def update_settings(data: dict, request: Request, current_user: dict = Depends(get_current_user)):
    """Update application settings."""
    current = await _load_settings()
    current.update(data)
    for key, value in current.items():
        await sqlite_manager.upsert_setting(key, value)
    logger.info("Settings updated")
    return current


@router.get("/watched-folders")
@read_rate_limit
async def get_watched_folders(request: Request, current_user: dict = Depends(get_current_user)):
    """Get list of watched folders."""
    folders = await sqlite_manager.fetchall(
        """
        SELECT id, path, recursive, include_patterns, exclude_patterns, enabled, file_count, created_at
        FROM watched_folders
        ORDER BY created_at DESC
        """
    )
    for folder in folders:
        folder["recursive"] = bool(folder["recursive"])
        folder["enabled"] = bool(folder["enabled"])
    return {"folders": folders}


@router.post("/watched-folders")
@write_rate_limit
async def add_watched_folder(data: dict, request: Request, current_user: dict = Depends(get_current_user)):
    """Add a new watched folder."""
    path = data.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="path is required")

    folder = {
        "id": str(uuid.uuid4()),
        "path": path,
        "recursive": bool(data.get("recursive", True)),
        "include_patterns": data.get("include_patterns") or ["*"],
        "exclude_patterns": data.get("exclude_patterns") or [".git", "node_modules"],
        "enabled": bool(data.get("enabled", True)),
        "file_count": 0,
    }

    try:
        await sqlite_manager.execute(
            """
            INSERT INTO watched_folders (id, path, recursive, include_patterns, exclude_patterns, enabled, file_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                folder["id"],
                folder["path"],
                int(folder["recursive"]),
                json.dumps(folder["include_patterns"]),
                json.dumps(folder["exclude_patterns"]),
                int(folder["enabled"]),
                folder["file_count"],
            ),
        )
    except Exception as exc:
        logger.error("Failed to store watched folder: %s", exc)
        raise HTTPException(status_code=400, detail="Folder already exists or is invalid") from exc

    try:
        from app.services.file_watcher import file_watcher_service
        await file_watcher_service.add_folder(folder)
    except Exception as exc:
        logger.warning("Could not start watcher for %s: %s", path, exc)

    return folder


@router.delete("/watched-folders/{folder_id}")
@write_rate_limit
async def remove_watched_folder(
    folder_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Remove a watched folder."""
    folder = await sqlite_manager.fetchone(
        "SELECT id, path FROM watched_folders WHERE id = ?",
        (folder_id,),
    )
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    await sqlite_manager.execute("DELETE FROM watched_folders WHERE id = ?", (folder_id,))

    try:
        from app.services.file_watcher import file_watcher_service
        await file_watcher_service.remove_folder(folder_id)
    except Exception as exc:
        logger.warning("Could not stop watcher for %s: %s", folder_id, exc)

    return {"message": "Folder removed", "id": folder_id}


@router.post("/backup")
@write_rate_limit
async def trigger_backup(
    data: dict,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """Trigger a backup."""
    backup_type = data.get("type")
    if backup_type not in ["snapshot", "markdown", "git"]:
        raise HTTPException(status_code=400, detail="Invalid backup type")

    from app.services.backup import backup_service

    background_tasks.add_task(backup_service.run_backup, backup_type)
    return {"message": f"{backup_type} backup started"}
