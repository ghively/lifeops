"""WebSocket Manager - Handles real-time communication."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any, DefaultDict, Dict, List, Optional, Set

from fastapi import WebSocket
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


# Channels broadcast to every authenticated user — app-wide events such as
# "an object was created" or "an agent went idle".
PUBLIC_CHANNELS = frozenset({"system", "logs", "objects", "tasks", "agents", "files"})

# Channels namespaced by a free-form identifier (e.g. agent name). We do not
# track per-agent ownership today, so these stay readable by any authenticated
# user. The `agent-approval:` channel is treated specially below because it
# is user-scoped by design.
PUBLIC_PREFIXES = ("agent:",)


class WebSocketMessage(BaseModel):
    """WebSocket message validation model."""

    type: str
    data: dict = {}


class WebSocketEvents:
    """WebSocket event factory."""

    @staticmethod
    def log_entry(entry: dict):
        return {"type": "log.entry", "channel": "logs", "data": entry}

    @staticmethod
    def object_created(object_id: str, object_type: str, title: str):
        return {"type": "object.created", "channel": "objects", "data": {"id": object_id, "type": object_type, "title": title}}

    @staticmethod
    def object_updated(object_id: str, changes: List[str]):
        return {"type": "object.updated", "channel": "objects", "data": {"id": object_id, "changes": changes}}

    @staticmethod
    def object_deleted(object_id: str):
        return {"type": "object.deleted", "channel": "objects", "data": {"id": object_id}}

    @staticmethod
    def block_created(block_id: str, object_id: str):
        return {"type": "block.created", "channel": f"object:{object_id}", "data": {"id": block_id, "object_id": object_id}}

    @staticmethod
    def block_updated(block_id: str, object_id: str):
        return {"type": "block.updated", "channel": f"object:{object_id}", "data": {"id": block_id, "object_id": object_id}}

    @staticmethod
    def block_deleted(block_id: str, object_id: str):
        return {"type": "block.deleted", "channel": f"object:{object_id}", "data": {"id": block_id, "object_id": object_id}}

    @staticmethod
    def task_assigned(task_id: str, agent_name: str, priority: str, route: str):
        return {
            "type": "task.assigned",
            "channel": "tasks",
            "data": {"id": task_id, "agent": agent_name, "priority": priority, "route": route},
        }

    @staticmethod
    def task_status_changed(task_id: str, status: str, agent_name: str):
        return {
            "type": "task.status_changed",
            "channel": "tasks",
            "data": {"id": task_id, "status": status, "agent": agent_name},
        }

    @staticmethod
    def task_progress_update(task_id: str, current_action: str, agent_name: str):
        return {
            "type": "task.progress_update",
            "channel": "tasks",
            "data": {"id": task_id, "current_action": current_action, "agent": agent_name},
        }

    @staticmethod
    def task_completed(task_id: str, agent_name: str):
        return {"type": "task.completed", "channel": "tasks", "data": {"id": task_id, "agent": agent_name}}

    @staticmethod
    def agent_status_changed(agent_name: str, status: str):
        return {"type": "agent.status_changed", "channel": "agents", "data": {"agent": agent_name, "status": status}}

    @staticmethod
    def agent_current_action(agent_name: str, current_action: str, task_id: str | None = None):
        return {
            "type": "agent.current_action",
            "channel": "agents",
            "data": {"agent": agent_name, "current_action": current_action, "task_id": task_id},
        }

    @staticmethod
    def chat_message(agent_name: str, content: str, session_id: str | None = None):
        return {
            "type": "chat.message",
            "channel": f"agent:{agent_name}",
            "data": {"agent": agent_name, "content": content, "session_id": session_id},
        }

    @staticmethod
    def file_indexed(file_id: str, path: str):
        return {"type": "file.indexed", "channel": "files", "data": {"id": file_id, "path": path}}

    @staticmethod
    def file_reindexed(file_id: str, path: str):
        return {"type": "file.indexed", "channel": "files", "data": {"id": file_id, "path": path, "reindexed": True}}

    @staticmethod
    def collab_user_joined(object_id: str, user_id: str, display_name: str, color: str):
        return {
            "type": "collab.user_joined",
            "channel": f"collab:{object_id}",
            "data": {"object_id": object_id, "user_id": user_id, "display_name": display_name, "color": color},
        }

    @staticmethod
    def collab_user_left(object_id: str, user_id: str):
        return {
            "type": "collab.user_left",
            "channel": f"collab:{object_id}",
            "data": {"object_id": object_id, "user_id": user_id},
        }

    @staticmethod
    def user_joined(object_id: str, user_id: str, user_name: str):
        return {
            "type": "user.joined",
            "channel": f"object:{object_id}",
            "data": {"object_id": object_id, "user_id": user_id, "user_name": user_name},
        }

    @staticmethod
    def user_left(object_id: str, user_id: str, user_name: str):
        return {
            "type": "user.left",
            "channel": f"object:{object_id}",
            "data": {"object_id": object_id, "user_id": user_id, "user_name": user_name},
        }

    @staticmethod
    def presence_update(object_id: str, users: list):
        return {"type": "presence.update", "channel": f"object:{object_id}", "data": {"object_id": object_id, "users": users}}

    @staticmethod
    def agent_approval_required(user_id: str, payload: dict):
        return {"type": "agent.approval_required", "channel": f"agent-approval:{user_id}", "data": payload}


class WebSocketManager:
    """Manages WebSocket connections and channel subscriptions."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.subscriptions: DefaultDict[WebSocket, Set[str]] = defaultdict(set)
        # Track the authenticated user behind each socket so channel
        # subscriptions can be authorized (issue #176).
        self.connection_users: Dict[WebSocket, Dict[str, Any]] = {}

    @property
    def active_connection_count(self) -> int:
        return len(self.active_connections)

    async def connect(self, websocket: WebSocket, user: Optional[Dict[str, Any]] = None):
        await websocket.accept()
        self.active_connections.add(websocket)
        self.subscriptions[websocket].add("system")
        if user is not None:
            self.connection_users[websocket] = user

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        self.subscriptions.pop(websocket, None)
        self.connection_users.pop(websocket, None)

    async def broadcast(self, message: dict):
        disconnected = set()
        channel = message.get("channel")
        for websocket in self.active_connections:
            subscriptions = self.subscriptions.get(websocket, {"system"})
            if channel and channel not in subscriptions and "system" not in subscriptions:
                continue
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.add(websocket)
        for websocket in disconnected:
            self.disconnect(websocket)

    async def _authorize_channel(self, user: Optional[Dict[str, Any]], channel: str) -> bool:
        """Return True if *user* may subscribe to *channel*.

        Anonymous sockets (no authenticated user) only get the public
        broadcast channels — anything namespaced is denied. See
        ``PUBLIC_CHANNELS`` / ``PUBLIC_PREFIXES`` for the unrestricted set.
        """
        if not isinstance(channel, str) or not channel:
            return False
        if channel in PUBLIC_CHANNELS:
            return True
        if any(channel.startswith(prefix) for prefix in PUBLIC_PREFIXES):
            return True

        user_id = (user or {}).get("id")
        if not user_id:
            return False

        if channel.startswith("agent-approval:"):
            target = channel.split(":", 1)[1]
            return target == str(user_id)

        if channel.startswith(("object:", "collab:")):
            object_id = channel.split(":", 1)[1]
            # Local import avoids a startup cycle: access.py depends on the
            # qdrant client which is initialized after this module is loaded.
            from app.services.access import user_can_access_object

            return await user_can_access_object(str(user_id), object_id)

        # Unknown namespaced channel — deny by default. New channel types
        # must opt in to this allow-list before clients can subscribe.
        return False

    async def handle_message(self, websocket: WebSocket, data: str):
        try:
            raw = json.loads(data)
            message = WebSocketMessage(**raw)
        except json.JSONDecodeError:
            await websocket.send_json({"type": "error", "data": {"message": "Invalid JSON"}})
            return
        except ValidationError:
            await websocket.send_json({"type": "error", "data": {"message": "Invalid message format"}})
            return

        if message.type == "ping":
            await websocket.send_json({"type": "pong", "data": {}})
            return

        if message.type == "subscribe":
            requested = message.data.get("channels", [])
            user = self.connection_users.get(websocket)
            granted: List[str] = []
            denied: List[str] = []
            for channel in requested:
                if await self._authorize_channel(user, channel):
                    self.subscriptions[websocket].add(channel)
                    granted.append(channel)
                else:
                    denied.append(channel)
            payload: Dict[str, Any] = {
                "channels": sorted(self.subscriptions[websocket]),
                "granted": granted,
            }
            if denied:
                payload["denied"] = denied
                logger.warning(
                    "Denied channel subscription user_id=%s channels=%s",
                    (user or {}).get("id"),
                    denied,
                )
            await websocket.send_json({"type": "subscribed", "data": payload})
            return

        if message.type == "unsubscribe":
            channels = message.data.get("channels", [])
            for channel in channels:
                self.subscriptions[websocket].discard(channel)
            await websocket.send_json({"type": "unsubscribed", "data": {"channels": channels}})
            return

        if message.type == "agent.approval_response":
            request_id = str(message.data.get("request_id") or "")
            approved = bool(message.data.get("approved"))
            from app.services.agent.sandbox import tool_approval_manager

            if not request_id or tool_approval_manager.get_payload(request_id) is None:
                await websocket.send_json({"type": "error", "data": {"message": "Unknown approval request"}})
                return
            tool_approval_manager.resolve(request_id, approved=approved)
            await websocket.send_json({"type": "agent.approval_ack", "data": {"request_id": request_id, "approved": approved}})


websocket_manager = WebSocketManager()
