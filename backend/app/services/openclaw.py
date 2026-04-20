"""OpenClaw Service - Integration with OpenClaw gateway via /tools/invoke."""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from app.config import settings
from app.database.sqlite import sqlite_manager

logger = logging.getLogger(__name__)

# Cache for the gateway token read from OpenClaw config file.
_cached_gateway_token: Optional[str] = None
# Cooldown: skip 401 retry if the last retry also failed (monotonic timestamp).
_auth_retry_cooldown_until: float = 0.0
_AUTH_RETRY_COOLDOWN_SEC = 300  # 5 minutes


def _read_gateway_token_from_config() -> Optional[str]:
    """Read gateway auth token from ~/.openclaw/openclaw.json.

    This is a fallback when OPENCLAW_TOKEN env var and DB setting are both
    empty.  The OpenClaw gateway stores its config (including the auth token)
    in ~/.openclaw/openclaw.json under gateway.auth.token.
    """
    global _cached_gateway_token
    if _cached_gateway_token is not None:
        return _cached_gateway_token
    try:
        cfg_path = Path.home() / ".openclaw" / "openclaw.json"
        if cfg_path.is_file():
            with open(cfg_path, encoding="utf-8") as fh:
                cfg = json.load(fh)
            token = cfg.get("gateway", {}).get("auth", {}).get("token", "")
            if isinstance(token, str) and token.strip():
                _cached_gateway_token = token.strip()
                return _cached_gateway_token
    except Exception as exc:
        logger.debug("Could not read OpenClaw config for gateway token: %s", exc)
    return None


class OpenClawService:
    """Service for communicating with OpenClaw gateway using /tools/invoke."""

    async def _runtime_settings(self) -> Dict[str, Any]:
        url = await sqlite_manager.get_setting("openclaw_url", settings.openclaw_url)
        token = await sqlite_manager.get_setting("openclaw_token", "")
        # Always prefer: DB > openclaw.json config > env var.
        # The env var is lowest priority because it can become stale
        # (e.g. hardcoded in .env) while the config file stays in sync
        # with the running gateway.
        if not token:
            token = _read_gateway_token_from_config() or settings.openclaw_token
        return {
            "openclaw_url": url,
            "openclaw_token": token,
            "openclaw_enabled": await sqlite_manager.get_setting("openclaw_enabled", True),
        }

    async def _invoke_tool(self, tool: str, args: Optional[dict] = None, session_key: str = "main") -> Dict[str, Any]:
        """Invoke a tool on the OpenClaw gateway via /tools/invoke."""
        runtime = await self._runtime_settings()
        if not runtime["openclaw_enabled"]:
            return {"status": "disabled", "content": "OpenClaw integration disabled"}

        base_url = f"{runtime['openclaw_url'].rstrip('/')}/tools/invoke"
        payload = {
            "tool": tool,
            "action": "json",
            "args": args or {},
            "sessionKey": session_key,
        }

        def _make_headers(token: Optional[str] = None) -> dict:
            headers = {"Content-Type": "application/json"}
            t = token if token is not None else runtime["openclaw_token"]
            if t:
                headers["Authorization"] = f"Bearer {t}"
            return headers

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(base_url, headers=_make_headers(), json=payload)
                response.raise_for_status()
                data = response.json()
                if data.get("ok"):
                    return {"status": "ok", **data.get("result", {})}
                error = data.get("error", {})
                return {"status": "error", "content": error.get("message", str(error))}
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 401:
                    now = time.monotonic()
                    global _cached_gateway_token, _auth_retry_cooldown_until

                    # Sanity-check: if cooldown timestamp is corrupted (e.g. from a
                    # stale value after process restart), reset it.  A valid cooldown
                    # should never be more than _AUTH_RETRY_COOLDOWN_SEC in the future.
                    if _auth_retry_cooldown_until > now + _AUTH_RETRY_COOLDOWN_SEC:
                        logger.warning(
                            "OpenClaw cooldown timestamp corrupted (until %.0f, now %.0f), resetting",
                            _auth_retry_cooldown_until,
                            now,
                        )
                        _auth_retry_cooldown_until = 0.0

                    if now < _auth_retry_cooldown_until:
                        # Recently failed retry — don't hammer. Return error directly.
                        remaining = _auth_retry_cooldown_until - now
                        logger.warning("OpenClaw 401 in cooldown (%.0fs remaining), skipping retry", remaining)
                        return {"status": "error", "content": "HTTP 401 (auth retry cooldown active)"}

                    # Invalidate config cache and get fresh token from openclaw.json.
                    _cached_gateway_token = None
                    fresh_token = _read_gateway_token_from_config()
                    retry_ok = False

                    if fresh_token:
                        logger.info("Retrying /tools/invoke after 401 with refreshed config token")
                        try:
                            retry_resp = await client.post(base_url, headers=_make_headers(fresh_token), json=payload)
                            retry_resp.raise_for_status()
                            data = retry_resp.json()
                            if data.get("ok"):
                                retry_ok = True
                                # Persist fresh token to DB so future calls skip 401.
                                if fresh_token != runtime["openclaw_token"]:
                                    await sqlite_manager.set_setting("openclaw_token", fresh_token)
                                return {"status": "ok", **data.get("result", {})}
                        except Exception:
                            pass

                    if not retry_ok:
                        # Retry failed — enter cooldown and clear stale DB token
                        # so that after cooldown expires, the next call re-reads config.
                        _auth_retry_cooldown_until = now + _AUTH_RETRY_COOLDOWN_SEC
                        logger.warning(
                            "OpenClaw 401 retry also failed, entering %ds cooldown and clearing DB token",
                            _AUTH_RETRY_COOLDOWN_SEC,
                        )
                        if runtime["openclaw_token"]:
                            await sqlite_manager.set_setting("openclaw_token", "")

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

    async def assign_task(
        self, agent_name: str, task_id: str, task_content: str, context: Optional[Dict] = None
    ) -> Dict[str, Any]:
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

        try:
            result = await self._invoke_tool("session_status", args={})
            reachable = result.get("status") == "ok"
            return {"status": "ok" if reachable else "error", "reachable": reachable}
        except Exception as exc:
            return {"status": "error", "reachable": False, "error": str(exc)}


openclaw_service = OpenClawService()
