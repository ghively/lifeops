#!/usr/bin/env python3
"""
File Watcher Service for Knowledge OS

Watches configured folders for changes and notifies the backend API.
Can run as a separate service or integrated into the main backend.
"""

import os
import sys
import json
import time
import asyncio
import logging
from pathlib import Path
from typing import Set, Dict, List
from dataclasses import dataclass, asdict
from app.utils.time import utc_now_iso
from app.logging_config import configure_logging

import aiohttp
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent, FileDeletedEvent, FileMovedEvent

configure_logging()
logger = logging.getLogger('file_watcher')


@dataclass
class WatchedFolder:
    id: str
    path: str
    recursive: bool = True
    include_patterns: List[str] = None
    exclude_patterns: List[str] = None
    
    def __post_init__(self):
        if self.include_patterns is None:
            self.include_patterns = ['*']
        if self.exclude_patterns is None:
            self.exclude_patterns = ['.*', '__pycache__', 'node_modules', '.git']


class FileChangeHandler(FileSystemEventHandler):
    """Handles file system events and sends updates to backend."""
    
    def __init__(self, backend_url: str, folder_config: WatchedFolder):
        self.backend_url = backend_url
        self.folder_config = folder_config
        self.pending_events: asyncio.Queue = asyncio.Queue()
        self.session: aiohttp.ClientSession = None
        
    async def start(self):
        """Start the event processor."""
        self.session = aiohttp.ClientSession()
        asyncio.create_task(self._process_events())
        
    async def stop(self):
        """Stop the event processor."""
        if self.session:
            await self.session.close()
            
    async def _process_events(self):
        """Process pending file events."""
        while True:
            try:
                event = await asyncio.wait_for(self.pending_events.get(), timeout=1.0)
                await self._notify_backend(event)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing event: {e}")
                
    async def _notify_backend(self, event: Dict):
        """Send file change notification to backend."""
        if not self.session:
            return
            
        try:
            url = f"{self.backend_url}/api/files/notify"
            async with self.session.post(url, json=event) as response:
                if response.status == 200:
                    logger.debug(f"Notified backend about {event['event_type']}: {event['path']}")
                else:
                    logger.warning(f"Backend returned {response.status} for {event['path']}")
        except Exception as e:
            logger.error(f"Failed to notify backend: {e}")
            
    def _should_process(self, path: str) -> bool:
        """Check if file should be processed based on patterns."""
        filename = os.path.basename(path)
        
        # Check exclude patterns
        for pattern in self.folder_config.exclude_patterns:
            if pattern.startswith('.'):
                if filename.startswith(pattern):
                    return False
            elif pattern in filename:
                return False
                
        # Check include patterns
        for pattern in self.folder_config.include_patterns:
            if pattern == '*' or pattern in filename:
                return True
                
        return False
        
    def _create_event(self, event_type: str, src_path: str, dest_path: str = None) -> Dict:
        """Create event dictionary."""
        event = {
            'event_type': event_type,
            'path': src_path,
            'folder_id': self.folder_config.id,
            'timestamp': utc_now_iso(),
        }
        if dest_path:
            event['dest_path'] = dest_path
        return event
        
    def on_created(self, event):
        if not event.is_directory and self._should_process(event.src_path):
            logger.info(f"File created: {event.src_path}")
            asyncio.create_task(
                self.pending_events.put(
                    self._create_event('created', event.src_path)
                )
            )
            
    def on_modified(self, event):
        if not event.is_directory and self._should_process(event.src_path):
            logger.info(f"File modified: {event.src_path}")
            asyncio.create_task(
                self.pending_events.put(
                    self._create_event('modified', event.src_path)
                )
            )
            
    def on_deleted(self, event):
        if not event.is_directory and self._should_process(event.src_path):
            logger.info(f"File deleted: {event.src_path}")
            asyncio.create_task(
                self.pending_events.put(
                    self._create_event('deleted', event.src_path)
                )
            )
            
    def on_moved(self, event):
        if not event.is_directory and self._should_process(event.src_path):
            logger.info(f"File moved: {event.src_path} -> {event.dest_path}")
            asyncio.create_task(
                self.pending_events.put(
                    self._create_event('moved', event.src_path, event.dest_path)
                )
            )


class FileWatcherService:
    """Main file watcher service that manages multiple folder observers."""
    
    def __init__(self, backend_url: str, config_path: str = None):
        self.backend_url = backend_url
        self.config_path = config_path or '/app/data/watched_folders.json'
        self.observers: Dict[str, Observer] = {}
        self.handlers: Dict[str, FileChangeHandler] = {}
        self.folders: Dict[str, WatchedFolder] = {}
        
    def load_config(self) -> List[WatchedFolder]:
        """Load watched folders from config file."""
        if not os.path.exists(self.config_path):
            logger.warning(f"Config file not found: {self.config_path}")
            return []
            
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
                return [WatchedFolder(**folder) for folder in data.get('folders', [])]
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return []
            
    def save_config(self):
        """Save watched folders to config file."""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            data = {
                'folders': [asdict(folder) for folder in self.folders.values()]
            }
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            
    async def start_watching(self, folder: WatchedFolder):
        """Start watching a folder."""
        if folder.id in self.observers:
            logger.warning(f"Already watching folder: {folder.path}")
            return
            
        if not os.path.exists(folder.path):
            logger.error(f"Folder does not exist: {folder.path}")
            return
            
        handler = FileChangeHandler(self.backend_url, folder)
        await handler.start()
        
        observer = Observer()
        observer.schedule(handler, folder.path, recursive=folder.recursive)
        observer.start()
        
        self.observers[folder.id] = observer
        self.handlers[folder.id] = handler
        self.folders[folder.id] = folder
        
        logger.info(f"Started watching: {folder.path} (recursive={folder.recursive})")
        
    async def stop_watching(self, folder_id: str):
        """Stop watching a folder."""
        if folder_id not in self.observers:
            return
            
        observer = self.observers.pop(folder_id)
        handler = self.handlers.pop(folder_id)
        
        observer.stop()
        observer.join()
        await handler.stop()
        
        self.folders.pop(folder_id, None)
        
        logger.info(f"Stopped watching folder: {folder_id}")
        
    async def refresh_folders(self):
        """Refresh watched folders from config."""
        folders = self.load_config()
        current_ids = set(self.folders.keys())
        new_ids = {f.id for f in folders}
        
        # Stop watching removed folders
        for folder_id in current_ids - new_ids:
            await self.stop_watching(folder_id)
            
        # Start watching new folders
        for folder in folders:
            if folder.id not in self.folders:
                await self.start_watching(folder)
                
    async def run(self):
        """Main service loop."""
        logger.info("Starting File Watcher Service")
        
        # Initial load
        await self.refresh_folders()
        
        # Watch for config changes
        while True:
            try:
                await asyncio.sleep(int(os.getenv('WATCH_INTERVAL', '5')))
                await self.refresh_folders()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                
    async def shutdown(self):
        """Shutdown the service."""
        logger.info("Shutting down File Watcher Service")
        
        for folder_id in list(self.observers.keys()):
            await self.stop_watching(folder_id)


async def main():
    """Main entry point."""
    backend_url = os.getenv('BACKEND_URL', 'http://localhost:8000')
    config_path = os.getenv('CONFIG_PATH', '/app/data/watched_folders.json')
    
    service = FileWatcherService(backend_url, config_path)
    
    try:
        await service.run()
    except KeyboardInterrupt:
        await service.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
