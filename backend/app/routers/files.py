"""Files Router - File management and indexing"""
import uuid
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Optional

from app.utils import compute_file_hash

from app.database.qdrant_client import qdrant_manager, QdrantManager
from app.database.sqlite import sqlite_manager
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import read_rate_limit, write_rate_limit
from app.services.websocket_manager import websocket_manager, WebSocketEvents
from app.services.embedding import embedding_service
from app.utils.time import utc_now_iso

class FileNotificationRequest(BaseModel):
    """File change notification request body."""
    event_type: str
    path: str
    folder_id: Optional[str] = None
    dest_path: Optional[str] = None


class IndexFileContentRequest(BaseModel):
    """Index file content request body."""
    path: str
    content: str = ""
    content_type: str = "text/plain"


router = APIRouter()
logger = logging.getLogger(__name__)

# Allowed base directories for file operations
_ALLOWED_BASE_DIRS: set[str] = set()


async def _get_allowed_dirs() -> set[str]:
    """Lazily load allowed watched directories from the database."""
    if not _ALLOWED_BASE_DIRS:
        from app.database.sqlite import sqlite_manager
        folders = await sqlite_manager.fetchall("SELECT path FROM watched_folders WHERE enabled = 1")
        for f in folders:
            _ALLOWED_BASE_DIRS.add(f["path"])
    return _ALLOWED_BASE_DIRS


def validate_file_path(path: str) -> str:
    """Validate a file path to prevent path traversal attacks."""
    import os
    if not path:
        raise HTTPException(status_code=400, detail="path is required")
    # Reject paths with .. components
    parts = path.replace("\\", "/").split("/")
    if ".." in parts:
        raise HTTPException(status_code=400, detail="Path traversal is not allowed")
    resolved = os.path.realpath(path)
    # Ensure the resolved path is within an allowed directory
    allowed = _ALLOWED_BASE_DIRS
    if not any(resolved.startswith(d) for d in allowed):
        raise HTTPException(status_code=400, detail="File path is outside allowed directories")
    return resolved


@router.get("")
@read_rate_limit
async def list_files(request: Request, current_user: dict = Depends(get_current_user)):
    """List all indexed files"""
    client = qdrant_manager.get_async_client()
    
    results = await client.scroll(
        collection_name="files",
        limit=1000,
        with_payload=True,
        with_vectors=False
    )
    
    files = []
    for result in results[0]:
        payload = result.payload
        payload["id"] = result.id
        files.append(payload)
    
    return {"files": files}


@router.get("/{file_id}")
@read_rate_limit
async def get_file(file_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Get file details"""
    client = qdrant_manager.get_async_client()
    
    results = await QdrantManager.safe_retrieve(client, 
        collection_name="files",
        ids=[file_id],
        with_payload=True,
        with_vectors=False
    )
    
    if not results:
        raise HTTPException(status_code=404, detail="File not found")
    
    payload = results[0].payload
    payload["id"] = results[0].id
    
    return payload


@router.post("/{file_id}/reindex")
@write_rate_limit
async def reindex_file(
    file_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """Reindex a file"""
    client = qdrant_manager.get_async_client()
    
    # Get existing file
    results = await QdrantManager.safe_retrieve(client, 
        collection_name="files",
        ids=[file_id],
        with_payload=True,
        with_vectors=False
    )
    
    if not results:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_data = results[0].payload
    file_path = file_data.get("path")
    
    # Trigger reindex in background
    background_tasks.add_task(_reindex_file_task, file_id, file_path)
    
    logger.info(f"Reindexing file: {file_id}")
    
    return {"message": "Reindexing started", "file_id": file_id}


async def _reindex_file_task(file_id: str, file_path: str):
    """Background task to reindex a file"""
    try:
        from app.services.file_watcher import file_watcher_service
        await file_watcher_service.process_file(file_path)
        
        # Broadcast event
        await websocket_manager.broadcast(
            WebSocketEvents.file_reindexed(file_id, file_path)
        )
        
        logger.info(f"File reindexed: {file_id}")
    except Exception as e:
        logger.error(f"Error reindexing file {file_id}: {e}")


@router.post("/notify")
@write_rate_limit
async def file_notification(data: FileNotificationRequest, request: Request, current_user: dict = Depends(get_current_user)):
    """Receive file change notifications from file watcher"""
    event_type = data.event_type
    path = data.path
    folder_id = data.folder_id
    
    if not event_type or not path:
        raise HTTPException(status_code=400, detail="event_type and path are required")
    
    path = validate_file_path(path)
    
    logger.info(f"File notification: {event_type} - {path}")
    
    # Process based on event type
    if event_type in ["created", "modified"]:
        # Index the file
        from app.services.file_watcher import file_watcher_service
        await file_watcher_service.process_file(path)
    elif event_type == "deleted":
        # Remove from index
        await _remove_file_from_index(path)
    elif event_type == "moved":
        # Update path in index
        dest_path = data.dest_path
        if dest_path:
            await _update_file_path(path, dest_path)
    
    return {"status": "ok"}


async def _remove_file_from_index(file_path: str):
    """Remove a file from the index"""
    client = qdrant_manager.get_async_client()
    
    # Find file by path
    results = await client.scroll(
        collection_name="files",
        scroll_filter={
            "must": [{"key": "path", "match": {"value": file_path}}]
        },
        limit=1,
        with_payload=False,
        with_vectors=False
    )
    
    if results[0]:
        await client.delete(
            collection_name="files",
            points_selector=[results[0][0].id]
        )
        logger.info(f"Removed file from index: {file_path}")


async def _update_file_path(old_path: str, new_path: str):
    """Update file path in index"""
    client = qdrant_manager.get_async_client()
    
    # Find file by old path
    results = await client.scroll(
        collection_name="files",
        scroll_filter={
            "must": [{"key": "path", "match": {"value": old_path}}]
        },
        limit=1,
        with_payload=True,
        with_vectors=False
    )
    
    if results[0]:
        file_id = results[0][0].id
        payload = results[0][0].payload
        payload["path"] = new_path
        
        await client.set_payload(
            collection_name="files",
            payload=payload,
            points=[file_id]
        )
        
        logger.info(f"Updated file path: {old_path} -> {new_path}")


@router.post("/{file_id}/content")
@write_rate_limit
async def index_file_content(
    file_id: str,
    data: IndexFileContentRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Index file content"""
    client = qdrant_manager.get_async_client()
    
    file_path = data.path
    content = data.content
    content_type = data.content_type
    
    if not file_path:
        raise HTTPException(status_code=400, detail="path is required")
    
    file_path = validate_file_path(file_path)
    
    # Compute SHA-256 hash
    file_hash = compute_file_hash(file_path) if file_path else ""
    
    # Generate embedding
    embedding = await embedding_service.embed_text(content)
    
    # Store in Qdrant
    await client.upsert(
        collection_name="files",
        points=[{
            "id": file_id,
            "vector": embedding.tolist(),
            "payload": {
                "id": file_id,
                "path": file_path,
                "name": file_path.split("/")[-1] if "/" in file_path else file_path,
                "content_type": content_type,
                "content_preview": content[:1000] if content else "",
                "hash": file_hash,
                "indexed_at": utc_now_iso(),
                "indexed": True
            }
        }]
    )
    
    logger.info(f"Indexed file: {file_id}")
    
    return {"message": "File indexed", "file_id": file_id}
