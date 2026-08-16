"""Structured audit logging for the agent runtime."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.database.sqlite import sqlite_manager
from app.services.agent.models import AgentAuditEvent
from app.utils.time import utc_now_iso


class AgentAuditLogger:
    def __init__(self, retention_days: int = 90):
        self.retention_days = retention_days

    async def log_event(
        self,
        *,
        agent_id: str,
        event_type: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> AgentAuditEvent:
        event = AgentAuditEvent(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            session_id=session_id,
            user_id=user_id,
            event_type=event_type,
            details=details or {},
            created_at=utc_now_iso(),
        )
        await sqlite_manager.create_agent_audit_event(event.model_dump())
        return event

    async def list_events(self, agent_id: str, *, page: int = 1, page_size: int = 50) -> Dict[str, Any]:
        return await sqlite_manager.list_agent_audit_events(agent_id, page=page, page_size=page_size)

    async def purge_expired(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        await sqlite_manager.purge_agent_audit_events(cutoff.replace(microsecond=0).isoformat().replace("+00:00", "Z"))
