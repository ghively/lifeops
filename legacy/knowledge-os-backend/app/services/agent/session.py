"""SQLite-backed session persistence for agent runtime."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Dict, List, Optional

from app.database.sqlite import sqlite_manager
from app.services.agent.models import AgentMessage, AgentSession, ToolResult
from app.utils.time import utc_now_iso

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(self, window_size: int = 20):
        self.window_size = window_size

    async def create_session(
        self, agent_id: str, title: Optional[str] = None, metadata: Optional[Dict] = None
    ) -> AgentSession:
        session = AgentSession(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            title=title,
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
            metadata=metadata or {},
        )
        await sqlite_manager.execute(
            """
            INSERT INTO agent_sessions (id, agent_id, agent_name, title, created_at, updated_at, message_count, metadata, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.id,
                session.agent_id,
                session.agent_id,
                session.title,
                session.created_at,
                session.updated_at,
                session.message_count,
                json.dumps(session.metadata),
                "active",
            ),
        )
        return session

    async def get_session(self, session_id: str) -> Optional[AgentSession]:
        row = await sqlite_manager.fetchone(
            "SELECT * FROM agent_sessions WHERE id = ?",
            (session_id,),
        )
        if not row:
            return None
        return AgentSession(
            id=row["id"],
            agent_id=row.get("agent_id") or row.get("agent_name"),
            title=row.get("title") or row.get("summary"),
            created_at=row.get("created_at") or row.get("started_at") or utc_now_iso(),
            updated_at=row.get("updated_at") or row.get("started_at") or utc_now_iso(),
            message_count=row.get("message_count") or row.get("messages_count") or 0,
            metadata=self._json_loads(row.get("metadata")),
        )

    async def list_sessions(self, agent_id: Optional[str] = None) -> List[AgentSession]:
        if agent_id:
            rows = await sqlite_manager.fetchall(
                "SELECT * FROM agent_sessions WHERE COALESCE(agent_id, agent_name) = ? ORDER BY COALESCE(updated_at, started_at) DESC",
                (agent_id,),
            )
        else:
            rows = await sqlite_manager.fetchall(
                "SELECT * FROM agent_sessions ORDER BY COALESCE(updated_at, started_at) DESC",
            )
        sessions = []
        for row in rows:
            sessions.append(
                AgentSession(
                    id=row["id"],
                    agent_id=row.get("agent_id") or row.get("agent_name"),
                    title=row.get("title") or row.get("summary"),
                    created_at=row.get("created_at") or row.get("started_at") or utc_now_iso(),
                    updated_at=row.get("updated_at") or row.get("started_at") or utc_now_iso(),
                    message_count=row.get("message_count") or row.get("messages_count") or 0,
                    metadata=self._json_loads(row.get("metadata")),
                )
            )
        return sessions

    async def delete_session(self, session_id: str) -> None:
        await sqlite_manager.execute("DELETE FROM agent_messages WHERE session_id = ?", (session_id,))
        await sqlite_manager.execute("DELETE FROM agent_sessions WHERE id = ?", (session_id,))

    async def add_message(self, session_id: str, message: AgentMessage) -> AgentMessage:
        message.id = message.id or str(uuid.uuid4())
        message.created_at = message.created_at or utc_now_iso()
        await sqlite_manager.execute(
            """
            INSERT INTO agent_messages (
                id, session_id, role, name, content, tool_calls, tool_results, tokens_in, tokens_out, created_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.id,
                session_id,
                message.role,
                message.name,
                message.content,
                json.dumps(message.tool_calls),
                json.dumps([item.model_dump() for item in message.tool_results]),
                message.tokens_in,
                message.tokens_out,
                message.created_at,
                json.dumps(message.metadata),
            ),
        )
        await sqlite_manager.execute(
            """
            UPDATE agent_sessions
            SET updated_at = ?, message_count = COALESCE(message_count, messages_count, 0) + 1,
                messages_count = COALESCE(messages_count, message_count, 0) + 1
            WHERE id = ?
            """,
            (utc_now_iso(), session_id),
        )
        return message

    async def load_history(self, session_id: str, limit: Optional[int] = None) -> List[AgentMessage]:
        rows = await sqlite_manager.fetchall(
            """
            SELECT * FROM agent_messages
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (session_id, limit or self.window_size),
        )
        history = []
        for row in reversed(rows):
            history.append(
                AgentMessage(
                    id=row["id"],
                    role=row["role"],
                    content=row["content"],
                    name=row.get("name"),
                    tool_calls=self._json_loads(row.get("tool_calls")) or [],
                    tool_results=[ToolResult(**item) for item in (self._json_loads(row.get("tool_results")) or [])],
                    tokens_in=row.get("tokens_in") or 0,
                    tokens_out=row.get("tokens_out") or 0,
                    created_at=row.get("created_at"),
                    metadata=self._json_loads(row.get("metadata")) or {},
                )
            )
        return history

    async def maybe_generate_title(self, session_id: str, llm_router=None) -> Optional[str]:
        session = await self.get_session(session_id)
        if not session or session.title:
            return session.title if session else None
        history = await self.load_history(session_id, limit=2)
        if not history:
            return None
        user_text = history[0].content.strip().replace("\n", " ")
        title = user_text[:60] or "New Session"
        if llm_router and len(history) >= 2:
            try:
                response = await llm_router.complete(
                    [{"role": "user", "content": f"Summarize this chat in 6 words or less:\n\n{user_text}"}]
                )
                title = (response.get("content") or title).strip()[:80]
            except Exception:
                logger.debug("Title generation fallback for session %s", session_id, exc_info=True)
        await sqlite_manager.execute(
            "UPDATE agent_sessions SET title = ?, updated_at = ? WHERE id = ?", (title, utc_now_iso(), session_id)
        )
        return title

    def _json_loads(self, value):
        if not value:
            return None
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except Exception:
            return None
