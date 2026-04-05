"""OpenClaw Service - Integration with OpenClaw gateway via /tools/invoke."""
import logging
from typing import Any, Dict, Optional

import httpx

from app.config import settings
from app.database.sqlite import sqlite_manager

logger = logging.getLogger(__name__)


class OpenClawService:
    """Service for communicating with OpenClaw gateway using /tools/invoke."""

    async def _runtime_settings(self) -> Dict[str, Any]:
        return {
            "openclaw_url": await sqlite_manager.get_setting("openclaw_url", settings.openclaw_url),
            "openclaw_token": await sqlite_manager.get_setting("openclaw_token", settings.openclaw_token),
            "openclaw_enabled": await sqlite_manager.get_setting("openclaw_enabled", True),
        }

    async def _invoke_tool(self, tool: str, args: Optional[dict] = None, session_key: str = "main") -> Dict[str, Any]:
        """Invoke a tool on the OpenClaw gateway via /tools/invoke."""
        runtime = await self._runtime_settings()
        if not runtime["openclaw_enabled"]:
            return {"status": "disabled", "content": "OpenClaw integration disabled"}

        headers = {"Content-Type": "application/json"}
        if runtime["openclaw_token"]:
            headers["Authorization"] = f"Bearer {runtime['openclaw_token']}"

        payload = {
            "tool": tool,
            "action": "json",
            "args": args or {},
            "sessionKey": session_key,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    f"{runtime['openclaw_url'].rstrip('/')}/tools/invoke",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                if data.get("ok"):
                    return {"status": "ok", **data.get("result", {})}
                else:
                    error = data.get("error", {})
                    return {"status": "error", "content": error.get("message", str(error))}
            except httpx.HTTPStatusError as exc:
                logger.error("OpenClaw /tools/invoke HTTP %s: %s", exc.response.status_code, exc.response.text)
                return {"status": "error", "content": f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"}
            except Exception as exc:
                logger.error("OpenClaw /tools/invoke failed: %s", exc)
                return {"status": "error", "content": str(exc)}

    async def send_message(self, agent_name: str, content: str, session_id: str = "main") -> Dict[str, Any]:
        """Send a message to an agent via sessions_send."""
        try:
            result = await self._invoke_tool(
                "sessions_send",
                args={
                    "sessionKey": f"agent:{agent_name}:{session_id}",
                    "message": content,
                },
            )
            # sessions_send doesn't return content directly — it queues the message
            if result.get("status") == "ok":
                return {"status": "ok", "content": "Message sent to agent"}
            return result
        except Exception as exc:
            logger.error("OpenClaw send_message failed: %s", exc)
            return {"status": "error", "content": str(exc)}

    async def assign_task(self, agent_name: str, task_id: str, task_content: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """Assign a task to an agent."""
        ctx_text = "\n".join(f"  - {k}: {v}" for k, v in (context or {}).items()) if context else "None"
        message = (
            f"📋 New Task Assigned\n\n"
            f"Task ID: {task_id}\n"
            f"Title: {task_content}\n\n"
            f"Context:\n{ctx_text}\n\n"
            f"Please acknowledge this task and begin work."
        )
        try:
            result = await self._invoke_tool(
                "sessions_send",
                args={
                    "sessionKey": f"agent:{agent_name}:main",
                    "message": message,
                },
            )
            if result.get("status") == "ok":
                return {"status": "ok", "content": "Task assigned to agent"}
            return result
        except Exception as exc:
            logger.error("OpenClaw assign_task failed: %s", exc)
            return {"status": "error", "content": str(exc)}

    async def get_agent_status(self, agent_name: str) -> Dict[str, Any]:
        """Get agent status by listing sessions and finding the agent."""
        try:
            result = await self._invoke_tool("sessions_list", args={"limit": 50})
            if result.get("status") != "ok":
                return {"status": "offline"}

            # sessions_list returns sessions — find matching agent
            sessions = result.get("sessions", [])
            for session in sessions:
                session_key = session.get("sessionKey", "")
                if f"agent:{agent_name}:" in session_key:
                    last_message = session.get("lastMessage", "")
                    return {
                        "status": "active",
                        "current_action": last_message[:100] if last_message else None,
                        "last_seen": session.get("updatedAt"),
                    }

            return {"status": "offline"}
        except Exception as exc:
            logger.debug("OpenClaw get_agent_status fallback for %s: %s", agent_name, exc)
            return {"status": "offline"}

    async def health_check(self) -> Dict[str, Any]:
        """Check if the OpenClaw gateway is reachable."""
        runtime = await self._runtime_settings()
        if not runtime["openclaw_enabled"]:
            return {"status": "disabled", "reachable": False}

        headers = {"Content-Type": "application/json"}
        if runtime["openclaw_token"]:
            headers["Authorization"] = f"Bearer {runtime['openclaw_token']}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{runtime['openclaw_url'].rstrip('/')}/tools/invoke",
                    headers=headers,
                    json={"tool": "session_status", "action": "json", "args": {}},
                )
                if response.status_code == 200:
                    return {"status": "ok", "reachable": True}
                return {"status": "error", "reachable": False, "http_status": response.status_code}
        except Exception as exc:
            return {"status": "error", "reachable": False, "error": str(exc)}


openclaw_service = OpenClawService()
