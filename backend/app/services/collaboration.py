"""Collaboration Service — Yjs-based real-time collaborative editing.

Uses a simplified CRDT approach with operation-based sync over WebSockets.
Each document (object_id) has a room that tracks connected users,
broadcasts edits, and persists to the existing Qdrant blocks store.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# --- User color palette for cursor rendering ---
CURSOR_COLORS = [
    "#e06c75",  # red
    "#98c379",  # green
    "#e5c07b",  # yellow
    "#61afef",  # blue
    "#c678dd",  # purple
    "#56b6c2",  # cyan
    "#d19a66",  # orange
    "#be5046",  # dark red
    "#7ec8e3",  # light blue
    "#c3e88d",  # lime
]


def user_color(user_id: str) -> str:
    """Assign a deterministic color to a user based on their ID."""
    idx = int(hashlib.md5(user_id.encode()).hexdigest(), 16) % len(CURSOR_COLORS)
    return CURSOR_COLORS[idx]


# --- Wire protocol message types ---
# Client -> Server
MSG_JOIN = "collab.join"
MSG_LEAVE = "collab.leave"
MSG_OP = "collab.op"            # CRDT operation
MSG_CURSOR = "collab.cursor"    # cursor/selection update
MSG_AWARENESS = "collab.awareness"  # generic awareness state
MSG_SNAPSHOT_REQ = "collab.snapshot_req"
MSG_ACK = "collab.ack"

# Server -> Client
MSG_WELCOME = "collab.welcome"
MSG_USER_JOINED = "collab.user_joined"
MSG_USER_LEFT = "collab.user_left"
MSG_OP_BROADCAST = "collab.op_broadcast"
MSG_CURSOR_BROADCAST = "collab.cursor_broadcast"
MSG_AWARENESS_BROADCAST = "collab.awareness_broadcast"
MSG_SNAPSHOT = "collab.snapshot"
MSG_ERROR = "collab.error"


@dataclass
class PresenceUser:
    """Represents a user connected to a collaboration room."""
    user_id: str
    display_name: str
    color: str
    cursor: Optional[Dict[str, Any]] = None  # { path: [0,0], offset: 5 }
    selection: Optional[Dict[str, Any]] = None  # { anchor, focus }
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        d: Dict[str, Any] = {
            "user_id": self.user_id,
            "display_name": self.display_name,
            "color": self.color,
        }
        if self.cursor:
            d["cursor"] = self.cursor
        if self.selection:
            d["selection"] = self.selection
        return d


@dataclass
class CROperation:
    """A CRDT operation for collaborative text editing.

    Uses a simple last-writer-wins register per block with
    lamport timestamps for ordering.
    """
    op_id: str
    object_id: str
    block_id: str
    type: str  # "insert" | "delete" | "replace" | "update_props"
    path: List[int]       # Slate path (e.g. [2, 0] = block index 2, child 0)
    offset: int = 0
    content: str = ""
    length: int = 0
    lamport_ts: int = 0
    user_id: str = ""

    def to_dict(self) -> dict:
        return {
            "op_id": self.op_id,
            "object_id": self.object_id,
            "block_id": self.block_id,
            "type": self.type,
            "path": self.path,
            "offset": self.offset,
            "content": self.content,
            "length": self.length,
            "lamport_ts": self.lamport_ts,
            "user_id": self.user_id,
        }


class CollaborationRoom:
    """Manages a single document editing session."""

    def __init__(self, object_id: str):
        self.object_id = object_id
        self.connections: Dict[str, WebSocket] = {}  # user_id -> ws
        self.presence: Dict[str, PresenceUser] = {}
        self.lamport_clock: int = 0
        self.operation_log: List[CROperation] = []  # recent ops for late joiners
        self.pending_persist: bool = False
        self.last_activity: float = time.time()
        self._max_log_size = 500

    @property
    def user_count(self) -> int:
        return len(self.connections)

    async def add_user(self, user_id: str, display_name: str, ws: WebSocket):
        color = user_color(user_id)
        presence = PresenceUser(
            user_id=user_id,
            display_name=display_name,
            color=color,
        )
        self.connections[user_id] = ws
        self.presence[user_id] = presence
        self.last_activity = time.time()

        # Send welcome to joining user with current presence list
        await self._send(ws, {
            "type": MSG_WELCOME,
            "data": {
                "object_id": self.object_id,
                "user_id": user_id,
                "color": color,
                "users": [u.to_dict() for u in self.presence.values() if u.user_id != user_id],
                "pending_ops": [op.to_dict() for op in self.operation_log[-50:]],
            },
        })

        # Notify others
        await self._broadcastExclude(user_id, {
            "type": MSG_USER_JOINED,
            "data": presence.to_dict(),
        })

        logger.info("User %s joined room %s (%d users)", user_id, self.object_id, self.user_count)

    async def remove_user(self, user_id: str):
        self.connections.pop(user_id, None)
        self.presence.pop(user_id, None)
        self.last_activity = time.time()

        # Notify remaining users
        await self._broadcastAll({
            "type": MSG_USER_LEFT,
            "data": {"user_id": user_id, "object_id": self.object_id},
        })

        logger.info("User %s left room %s (%d users)", user_id, self.object_id, self.user_count)

    async def handle_operation(self, op: CROperation):
        """Process a CRDT operation and broadcast to others."""
        self.lamport_clock += 1
        op.lamport_ts = self.lamport_clock
        self.operation_log.append(op)
        self.last_activity = time.time()
        self.pending_persist = True

        # Trim log
        if len(self.operation_log) > self._max_log_size:
            self.operation_log = self.operation_log[-self._max_log_size:]

        # Broadcast to all OTHER users
        await self._broadcastExclude(op.user_id, {
            "type": MSG_OP_BROADCAST,
            "data": op.to_dict(),
        })

        # Ack to sender
        ws = self.connections.get(op.user_id)
        if ws:
            await self._send(ws, {
                "type": MSG_ACK,
                "data": {"op_id": op.op_id, "lamport_ts": op.lamport_ts},
            })

    async def handle_cursor(self, user_id: str, cursor: Optional[dict], selection: Optional[dict]):
        """Update cursor/selection for a user and broadcast."""
        presence = self.presence.get(user_id)
        if not presence:
            return
        presence.cursor = cursor
        presence.selection = selection
        presence.last_seen = time.time()

        await self._broadcastExclude(user_id, {
            "type": MSG_CURSOR_BROADCAST,
            "data": {
                "user_id": user_id,
                "cursor": cursor,
                "selection": selection,
            },
        })

    async def handle_awareness(self, user_id: str, state: dict):
        """Handle generic awareness state update."""
        presence = self.presence.get(user_id)
        if not presence:
            return
        presence.last_seen = time.time()

        await self._broadcastExclude(user_id, {
            "type": MSG_AWARENESS_BROADCAST,
            "data": {"user_id": user_id, "state": state},
        })

    def get_snapshot(self) -> dict:
        """Get current room state snapshot."""
        return {
            "object_id": self.object_id,
            "users": [u.to_dict() for u in self.presence.values()],
            "lamport_clock": self.lamport_clock,
            "pending_ops": len(self.operation_log),
        }

    async def _send(self, ws: WebSocket, message: dict):
        try:
            await ws.send_json(message)
        except Exception:
            logger.debug("Failed to send to websocket", exc_info=True)

    async def _broadcastAll(self, message: dict):
        disconnected = []
        for uid, ws in self.connections.items():
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(uid)
        for uid in disconnected:
            await self.remove_user(uid)

    async def _broadcastExclude(self, exclude_user_id: str, message: dict):
        disconnected = []
        for uid, ws in self.connections.items():
            if uid == exclude_user_id:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(uid)
        for uid in disconnected:
            await self.remove_user(uid)


class CollaborationManager:
    """Manages all collaboration rooms across the application."""

    def __init__(self):
        self.rooms: Dict[str, CollaborationRoom] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._idle_timeout: int = 3600  # 1 hour idle room cleanup

    @property
    def active_connection_count(self) -> int:
        return sum(room.user_count for room in self.rooms.values())

    async def start(self):
        """Start background cleanup task."""
        self._cleanup_task = asyncio.create_task(self._idle_cleanup_loop())
        logger.info("CollaborationManager started")

    async def stop(self):
        """Stop background tasks."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("CollaborationManager stopped")

    def get_room(self, object_id: str) -> Optional[CollaborationRoom]:
        return self.rooms.get(object_id)

    def get_or_create_room(self, object_id: str) -> CollaborationRoom:
        if object_id not in self.rooms:
            self.rooms[object_id] = CollaborationRoom(object_id)
            logger.info("Created collaboration room for object %s", object_id)
        return self.rooms[object_id]

    async def join_room(self, object_id: str, user_id: str, display_name: str, ws: WebSocket) -> CollaborationRoom:
        room = self.get_or_create_room(object_id)
        await room.add_user(user_id, display_name, ws)
        return room

    async def leave_room(self, object_id: str, user_id: str):
        room = self.rooms.get(object_id)
        if not room:
            return
        await room.remove_user(user_id)
        # Clean up empty rooms
        if room.user_count == 0:
            # Persist before removing
            if room.pending_persist:
                logger.info("Room %s is empty, marking for cleanup", object_id)
            del self.rooms[object_id]
            logger.info("Removed empty room %s", object_id)

    def get_presence(self, object_id: str) -> List[dict]:
        """Get presence data for a document."""
        room = self.rooms.get(object_id)
        if not room:
            return []
        return [u.to_dict() for u in room.presence.values()]

    async def _idle_cleanup_loop(self):
        """Periodically clean up idle rooms."""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                now = time.time()
                to_remove = [
                    oid for oid, room in self.rooms.items()
                    if room.user_count == 0 and (now - room.last_activity) > self._idle_timeout
                ]
                for oid in to_remove:
                    del self.rooms[oid]
                    logger.info("Cleaned up idle room %s", oid)
                if to_remove:
                    logger.info("Cleaned up %d idle rooms", len(to_remove))
            except asyncio.CancelledError:
                break
            except Exception:
                logger.error("Error in idle cleanup", exc_info=True)


# Singleton
collaboration_manager = CollaborationManager()
