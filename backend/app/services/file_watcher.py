"""File Watcher Service - Watches folders for changes and indexes files."""
from __future__ import annotations
import asyncio
import ast
import json
import logging
import mimetypes
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.database.qdrant_client import qdrant_manager
from app.database.sqlite import sqlite_manager
from app.services.embedding import embedding_service
from app.services.websocket_manager import WebSocketEvents, websocket_manager
from app.utils import compute_file_hash
from app.utils.time import utc_now_iso

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {".md", ".txt", ".py", ".js", ".ts", ".tsx", ".json", ".yaml", ".yml", ".html", ".css", ".sh"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
CODE_EXTENSIONS = {".py", ".js", ".ts", ".tsx"}


class FileChangeHandler(FileSystemEventHandler):
    """Dispatch file changes into async service methods."""

    def __init__(self, watcher: "FileWatcherService", folder_id: str):
        self.watcher = watcher
        self.folder_id = folder_id

    def on_created(self, event):
        if not event.is_directory:
            self.watcher.schedule_process(event.src_path, self.folder_id)

    def on_modified(self, event):
        if not event.is_directory:
            self.watcher.schedule_process(event.src_path, self.folder_id)

    def on_deleted(self, event):
        if not event.is_directory:
            self.watcher.schedule_delete(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self.watcher.schedule_delete(event.src_path)
            self.watcher.schedule_process(event.dest_path, self.folder_id)


class FileWatcherService:
    """Service for watching file system changes."""

    def __init__(self):
        self.observers: Dict[str, Observer] = {}
        self.handlers: Dict[str, FileChangeHandler] = {}
        self.folders: Dict[str, dict] = {}
        self.loop = None

    async def start(self):
        self.loop = __import__("asyncio").get_running_loop()
        folders = await sqlite_manager.fetchall(
            """
            SELECT id, path, recursive, include_patterns, exclude_patterns, enabled, file_count
            FROM watched_folders WHERE enabled = 1
            """
        )
        for folder in folders:
            folder["recursive"] = bool(folder["recursive"])
            folder["enabled"] = bool(folder["enabled"])
            folder["include_patterns"] = json.loads(folder["include_patterns"] or '["*"]')
            folder["exclude_patterns"] = json.loads(folder["exclude_patterns"] or "[]")
            await self.add_folder(folder)
        logger.info("File watcher service started with %s folders", len(folders))

    async def stop(self):
        for folder_id in list(self.observers):
            await self.remove_folder(folder_id)
        logger.info("File watcher service stopped")

    async def add_folder(self, folder: dict):
        folder_id = folder["id"]
        path = folder["path"]
        if folder_id in self.observers or not os.path.isdir(path):
            return
        observer = Observer()
        handler = FileChangeHandler(self, folder_id)
        observer.schedule(handler, path, recursive=folder.get("recursive", True))
        observer.start()
        self.observers[folder_id] = observer
        self.handlers[folder_id] = handler
        self.folders[folder_id] = folder
        for file_path in self._scan_folder(folder):
            await self.process_file(file_path, folder_id)

    async def remove_folder(self, folder_id: str):
        observer = self.observers.pop(folder_id, None)
        if observer:
            observer.stop()
            observer.join()
        self.handlers.pop(folder_id, None)
        self.folders.pop(folder_id, None)

    def schedule_process(self, file_path: str, folder_id: str):
        if self.loop:
            __import__("asyncio").run_coroutine_threadsafe(self.process_file(file_path, folder_id), self.loop)

    def schedule_delete(self, file_path: str):
        if self.loop:
            __import__("asyncio").run_coroutine_threadsafe(self._remove_file_from_index(file_path), self.loop)

    def _scan_folder(self, folder: dict):
        base = Path(folder["path"])
        for path in base.rglob("*") if folder.get("recursive", True) else base.glob("*"):
            if path.is_file() and self._matches_patterns(path, folder):
                yield str(path)

    def _matches_patterns(self, path: Path, folder: dict) -> bool:
        relative = path.name
        exclude_patterns = folder.get("exclude_patterns") or []
        if any(pattern in str(path) for pattern in exclude_patterns):
            return False
        include_patterns = folder.get("include_patterns") or ["*"]
        if include_patterns == ["*"]:
            return True
        return any(path.match(pattern) or relative == pattern for pattern in include_patterns)

    async def process_file(self, file_path: str, folder_id: str | None = None):
        if not os.path.exists(file_path):
            return

        folder = self.folders.get(folder_id) if folder_id else None
        if folder and not self._matches_patterns(Path(file_path), folder):
            return

        checksum = compute_file_hash(file_path)
        stat = os.stat(file_path)
        sync_status = await sqlite_manager.fetchone(
            "SELECT checksum FROM file_sync_status WHERE file_path = ?",
            (file_path,),
        )
        if sync_status and sync_status["checksum"] == checksum:
            return

        extension = Path(file_path).suffix.lower()
        mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        index_status = "indexed"
        error_message = None
        object_id = str(uuid.uuid4())

        try:
            content_text = await self._extract_content(file_path, extension)
            file_id = await self._upsert_file_record(file_path, checksum, mime_type, content_text, object_id)
            if extension in IMAGE_EXTENSIONS:
                await self._upsert_image_record(file_path, object_id, file_id)
            if extension in CODE_EXTENSIONS:
                await self._upsert_code_records(file_path, object_id, file_id, content_text)
            await websocket_manager.broadcast(WebSocketEvents.file_indexed(file_id, file_path))
        except Exception as exc:
            logger.error("Failed to index %s: %s", file_path, exc)
            index_status = "error"
            error_message = str(exc)
            file_id = None

        await sqlite_manager.execute(
            """
            INSERT INTO file_sync_status (file_path, checksum, last_modified, index_status, error_message, object_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(file_path) DO UPDATE SET
                checksum = excluded.checksum,
                last_modified = excluded.last_modified,
                index_status = excluded.index_status,
                error_message = excluded.error_message,
                object_id = excluded.object_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (file_path, checksum, datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(), index_status, error_message, object_id),
        )

        if folder_id:
            count = await sqlite_manager.fetchone("SELECT COUNT(*) AS count FROM file_sync_status")
            await sqlite_manager.execute(
                "UPDATE watched_folders SET file_count = ? WHERE id = ?",
                (count["count"], folder_id),
            )

    def _extract_content_sync(self, file_path: str, extension: str) -> str:
        if extension == ".pdf":
            import fitz

            document = fitz.open(file_path)
            return "\n".join(page.get_text() for page in document)
        if extension == ".docx":
            import docx

            document = docx.Document(file_path)
            return "\n".join(paragraph.text for paragraph in document.paragraphs)
        if extension in IMAGE_EXTENSIONS:
            return ""
        with open(file_path, "r", encoding="utf-8", errors="ignore") as file_handle:
            return file_handle.read()

    async def _extract_content(self, file_path: str, extension: str) -> str:
        return await asyncio.to_thread(self._extract_content_sync, file_path, extension)

    async def _upsert_file_record(self, file_path: str, checksum: str, mime_type: str, content_text: str, object_id: str) -> str:
        client = qdrant_manager.get_async_client()
        existing = await client.scroll(
            collection_name="files",
            scroll_filter={"must": [{"key": "path", "match": {"value": file_path}}]},
            limit=1,
            with_payload=True,
            with_vectors=False,
        )
        file_id = str(existing[0][0].id) if existing[0] else str(uuid.uuid4())
        embedding = await embedding_service.embed_text(content_text[:10000] or Path(file_path).name)
        stat = os.stat(file_path)
        payload = {
            "id": file_id,
            "object_id": object_id,
            "path": file_path,
            "relative_path": file_path,
            "filename": Path(file_path).name,
            "extension": Path(file_path).suffix.lower(),
            "mime_type": mime_type,
            "size_bytes": stat.st_size,
            "content_text": content_text,
            "content_preview": content_text[:1000],
            "checksum": checksum,
            "last_modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "last_indexed": utc_now_iso(),
            "index_status": "indexed",
            "error_message": None,
            "metadata": {"title": Path(file_path).stem, "word_count": len(content_text.split()) if content_text else 0},
        }
        await client.upsert(collection_name="files", points=[{"id": file_id, "vector": embedding.tolist(), "payload": payload}])
        object_embedding = await embedding_service.embed_text(content_text[:10000] or Path(file_path).name)
        await client.upsert(
            collection_name="objects",
            points=[{
                "id": object_id,
                "vector": object_embedding.tolist(),
                "payload": {
                    "id": object_id,
                    "type": "file",
                    "title": Path(file_path).name,
                    "icon": "📎",
                    "content": content_text[:10000],
                    "layout": "default",
                    "properties": {
                        "file_path": file_path,
                        "file_size": stat.st_size,
                        "file_type": mime_type,
                        "checksum": checksum,
                        "is_watched": True,
                        "created_at": utc_now_iso(),
                        "updated_at": utc_now_iso(),
                    },
                },
            }],
        )
        return file_id

    async def _upsert_image_record(self, file_path: str, object_id: str, file_id: str):
        client = qdrant_manager.get_async_client()
        embedding = await embedding_service.embed_image(file_path)
        image_id = str(uuid.uuid4())
        await client.upsert(
            collection_name="images",
            points=[{
                "id": image_id,
                "vector": embedding.tolist(),
                "payload": {
                    "id": image_id,
                    "object_id": object_id,
                    "path": file_path,
                    "filename": Path(file_path).name,
                    "description": Path(file_path).stem,
                    "tags": [],
                    "source_object": object_id,
                    "source_file": file_id,
                },
            }],
        )

    async def _upsert_code_records(self, file_path: str, object_id: str, file_id: str, content: str):
        if Path(file_path).suffix.lower() != ".py":
            return
        client = qdrant_manager.get_async_client()
        tree = ast.parse(content or "")
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                snippet = ast.get_source_segment(content, node) or ""
                embedding = await embedding_service.embed_text(snippet or getattr(node, "name", ""))
                code_id = str(uuid.uuid4())
                payload = {
                    "id": code_id,
                    "file_id": file_id,
                    "object_id": object_id,
                    "file_path": file_path,
                    "language": "python",
                    "line_start": getattr(node, "lineno", 1),
                    "line_end": getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                    "content": snippet,
                    "docstring": ast.get_docstring(node) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else None,
                    "signature": getattr(node, "name", ""),
                    "type": "class" if isinstance(node, ast.ClassDef) else "function",
                    "name": getattr(node, "name", ""),
                    "class_name": None,
                }
                await client.upsert(collection_name="code", points=[{"id": code_id, "vector": embedding.tolist(), "payload": payload}])

    async def _remove_file_from_index(self, file_path: str):
        client = qdrant_manager.get_async_client()
        results = await client.scroll(
            collection_name="files",
            scroll_filter={"must": [{"key": "path", "match": {"value": file_path}}]},
            limit=10,
            with_payload=True,
            with_vectors=False,
        )
        object_ids: List[str] = []
        for point in results[0]:
            payload = dict(point.payload or {})
            object_id = payload.get("object_id")
            if object_id:
                object_ids.append(object_id)
            await client.delete(collection_name="files", points_selector=[str(point.id)])
        for object_id in object_ids:
            await client.delete(collection_name="objects", points_selector=[object_id])
        await sqlite_manager.execute("DELETE FROM file_sync_status WHERE file_path = ?", (file_path,))


file_watcher_service = FileWatcherService()
