"""Backup Service - Handles all backup operations"""
import asyncio
import os
import uuid
import subprocess
import logging
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.database.qdrant_client import qdrant_manager
from app.database.sqlite import sqlite_manager
from app.utils.time import utc_now_iso

logger = logging.getLogger(__name__)


class BackupService:
    """Service for handling backups"""
    
    def __init__(self):
        self.backup_path = settings.backup_path
        self.running = False
    
    async def start(self):
        """Start the backup service"""
        self.running = True
        os.makedirs(self.backup_path, exist_ok=True)
        logger.info(f"Backup service started (path: {self.backup_path})")
    
    async def stop(self):
        """Stop the backup service"""
        self.running = False
        logger.info("Backup service stopped")
    
    async def run_backup(self, backup_type: str):
        """Run a backup of the specified type"""
        backup_id = str(uuid.uuid4())
        await sqlite_manager.execute(
            """
            INSERT INTO backup_log (id, type, status, details, started_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (backup_id, backup_type, "running", "", utc_now_iso()),
        )
        if backup_type == "snapshot":
            details = await self._create_qdrant_snapshot()
        elif backup_type == "markdown":
            details = await self._export_markdown()
        elif backup_type == "git":
            details = await self._git_sync()
        else:
            details = "Unsupported backup type"
        await sqlite_manager.execute(
            """
            UPDATE backup_log
            SET status = ?, details = ?, completed_at = ?
            WHERE id = ?
            """,
            ("completed", details or "", utc_now_iso(), backup_id),
        )
    
    async def _create_qdrant_snapshot(self):
        """Create a Qdrant snapshot"""
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            snapshot_dir = os.path.join(self.backup_path, "snapshots")
            os.makedirs(snapshot_dir, exist_ok=True)
            
            qdrant_host = settings.qdrant_host
            qdrant_port = settings.qdrant_port
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"http://{qdrant_host}:{qdrant_port}/snapshots"
                )
                
                if response.status_code == 200:
                    logger.info(f"Qdrant snapshot created: {timestamp}")
                    return f"snapshot:{timestamp}"
                else:
                    logger.warning(f"Qdrant snapshot failed: {response.text}")
                    return response.text

        except Exception as e:
            logger.error(f"Error creating Qdrant snapshot: {e}")
            return str(e)
    
    async def _export_markdown(self):
        """Export all objects to markdown files"""
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            export_dir = os.path.join(self.backup_path, "markdown", timestamp)
            os.makedirs(export_dir, exist_ok=True)
            
            client = qdrant_manager.get_async_client()
            
            collections = ["objects", "blocks"]
            for collection in collections:
                collection_dir = os.path.join(export_dir, collection)
                os.makedirs(collection_dir, exist_ok=True)
                
                results = await client.scroll(
                    collection_name=collection,
                    limit=10000,
                    with_payload=True,
                    with_vectors=False
                )
                
                for result in results[0]:
                    payload = result.payload
                    title = payload.get("title", "untitled")
                    content = payload.get("content", "")
                    
                    filename = f"{result.id}.md"
                    filepath = os.path.join(collection_dir, filename)
                    
                    with open(filepath, "w", encoding="utf-8") as file_handle:
                        file_handle.write("---\n")
                        file_handle.write(f"id: {result.id}\n")
                        file_handle.write(f"collection: {collection}\n")
                        file_handle.write("---\n\n")
                        file_handle.write(f"# {title}\n\n")
                        file_handle.write(content or "")

            logger.info(f"Markdown export completed: {export_dir}")
            return export_dir

        except Exception as e:
            logger.error(f"Error exporting markdown: {e}")
            return str(e)
    
    async def _git_sync(self):
        """Sync to Git repository"""
        try:
            git_repo = await sqlite_manager.get_setting("git_repo_url", settings.git_repo_url)
            if not git_repo:
                logger.warning("No Git repository configured")
                return "No Git repository configured"
            
            git_dir = os.path.join(self.backup_path, "git")
            os.makedirs(git_dir, exist_ok=True)
            
            if not os.path.exists(os.path.join(git_dir, ".git")):
                await asyncio.to_thread(
                    subprocess.run,
                    ["git", "clone", git_repo, "."],
                    cwd=git_dir,
                    check=True,
                )
            
            await asyncio.to_thread(
                subprocess.run,
                ["git", "pull"],
                cwd=git_dir,
                check=True,
            )
            
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            export_subdir = os.path.join(git_dir, "exports", timestamp)
            
            await self._export_markdown_to_dir(export_subdir)
            
            await asyncio.to_thread(
                subprocess.run,
                ["git", "add", "."],
                cwd=git_dir,
                check=True,
            )
            await asyncio.to_thread(
                subprocess.run,
                ["git", "commit", "-m", f"Auto-export {timestamp}"],
                cwd=git_dir,
                check=False,
            )
            await asyncio.to_thread(
                subprocess.run,
                ["git", "push"],
                cwd=git_dir,
                check=True,
            )

            logger.info("Git sync completed")
            return f"git:{timestamp}"

        except Exception as e:
            logger.error(f"Error syncing to Git: {e}")
            return str(e)
    
    async def _export_markdown_to_dir(self, export_dir: str):
        """Export markdown to a specific directory"""
        os.makedirs(export_dir, exist_ok=True)
        
        client = qdrant_manager.get_async_client()
        
        collections = ["objects", "blocks"]
        for collection in collections:
            collection_dir = os.path.join(export_dir, collection)
            os.makedirs(collection_dir, exist_ok=True)
            
            results = await client.scroll(
                collection_name=collection,
                limit=10000,
                with_payload=True,
                with_vectors=False
            )
            
            for result in results[0]:
                payload = result.payload
                title = payload.get("title", "untitled")
                content = payload.get("content", "")
                
                filename = f"{result.id}.md"
                filepath = os.path.join(collection_dir, filename)
                
                with open(filepath, "w", encoding="utf-8") as file_handle:
                    file_handle.write("---\n")
                    file_handle.write(f"id: {result.id}\n")
                    file_handle.write(f"collection: {collection}\n")
                    file_handle.write("---\n\n")
                    file_handle.write(f"# {title}\n\n")
                    file_handle.write(content or "")


# Global backup service instance
backup_service = BackupService()
