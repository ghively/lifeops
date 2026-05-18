"""Settings Router - Application settings and configuration."""

import json
import logging
import re
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel

from app.config import settings as app_settings
from app.database.sqlite import sqlite_manager
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import read_rate_limit, write_rate_limit

router = APIRouter()
logger = logging.getLogger(__name__)

SENSITIVE_SETTINGS = {"openclaw_token", "jwt_secret_key", "llm_api_key"}

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
    all_settings = await _load_settings()
    return {k: v for k, v in all_settings.items() if k not in SENSITIVE_SETTINGS}


class SettingsUpdate(BaseModel):
    """Settings update request body."""

    openclaw_url: Optional[str] = None
    openclaw_token: Optional[str] = None
    openclaw_enabled: Optional[bool] = None
    backup_snapshots: Optional[bool] = None
    backup_markdown: Optional[bool] = None
    backup_git: Optional[bool] = None
    git_repo_url: Optional[str] = None
    snapshot_interval_hours: Optional[int] = None
    markdown_export_interval_hours: Optional[int] = None
    git_sync_interval_minutes: Optional[int] = None
    embedding_model: Optional[str] = None
    image_embedding_model: Optional[str] = None
    max_context_tokens: Optional[int] = None
    auto_index: Optional[bool] = None

    def to_update_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v is not None}


@router.put("")
@write_rate_limit
async def update_settings(data: SettingsUpdate, request: Request, current_user: dict = Depends(get_current_user)):
    """Update application settings."""
    current = await _load_settings()
    current.update(data.to_update_dict())
    for key, value in current.items():
        await sqlite_manager.upsert_setting(key, value)
    logger.info("Settings updated")
    return current


# ---- Per-user preferences ---------------------------------------------------
# Arbitrary {key: value} bag scoped to the authenticated user. Distinct from
# the typed system settings above.

PREFERENCE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
MAX_PREFERENCE_VALUE_BYTES = 16 * 1024  # JSON-serialized
MAX_PREFERENCES_PER_USER = 200


def _validate_preference_key(key: str) -> None:
    if not isinstance(key, str) or not PREFERENCE_KEY_PATTERN.match(key):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid preference key. Must be 1-64 chars of "
                "[A-Za-z0-9_.-]."
            ),
        )


def _validate_preference_value(key: str, value: Any) -> None:
    try:
        encoded = json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Preference value for '{key}' is not JSON-serializable",
        ) from exc
    if len(encoded.encode("utf-8")) > MAX_PREFERENCE_VALUE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Preference value for '{key}' exceeds "
                f"{MAX_PREFERENCE_VALUE_BYTES} bytes when JSON-encoded"
            ),
        )


@router.get("/preferences")
@read_rate_limit
async def get_preferences(request: Request, current_user: dict = Depends(get_current_user)):
    """Return the authenticated user's preference bag."""
    return await sqlite_manager.list_user_preferences(current_user["id"])


@router.put("/preferences")
@write_rate_limit
async def update_preferences(
    data: Dict[str, Any],
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Merge arbitrary key/value pairs into the user's preference bag."""
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    for key, value in data.items():
        _validate_preference_key(key)
        _validate_preference_value(key, value)

    if data:
        existing_keys = set(
            (await sqlite_manager.list_user_preferences(current_user["id"])).keys()
        )
        added_keys = [k for k in data if k not in existing_keys]
        if len(existing_keys) + len(added_keys) > MAX_PREFERENCES_PER_USER:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot store more than {MAX_PREFERENCES_PER_USER} preference keys per user",
            )

    await sqlite_manager.upsert_user_preferences(current_user["id"], data)
    return await sqlite_manager.list_user_preferences(current_user["id"])


@router.delete("/preferences/{key}")
@write_rate_limit
async def delete_preference(
    key: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Remove a single preference key for the authenticated user."""
    _validate_preference_key(key)
    removed = await sqlite_manager.delete_user_preference(current_user["id"], key)
    if not removed:
        raise HTTPException(status_code=404, detail="Preference not found")
    return {"message": "Preference removed", "key": key}


@router.get("/watched-folders")
@read_rate_limit
async def get_watched_folders(request: Request, current_user: dict = Depends(get_current_user)):
    """Get list of watched folders."""
    folders = await sqlite_manager.fetchall("""
        SELECT id, path, recursive, include_patterns, exclude_patterns, enabled, file_count, created_at
        FROM watched_folders
        ORDER BY created_at DESC
        """)
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


@router.get("/openclaw-health")
@read_rate_limit
async def openclaw_health(request: Request, current_user: dict = Depends(get_current_user)):
    """Check OpenClaw gateway connectivity."""
    from app.services.openclaw import openclaw_service

    return await openclaw_service.health_check()


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
