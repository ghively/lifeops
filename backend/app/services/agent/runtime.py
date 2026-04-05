"""Main orchestrator for the Phase 1 agent runtime."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional

from app.config import BASE_DIR
from app.services.agent.agent_loop import AgentLoop
from app.services.agent.identity import DEFAULT_AGENT_FILES, IdentityLoader
from app.services.agent.llm_router import LLMRouter
from app.services.agent.memory import MemoryManager
from app.services.agent.models import AgentMessage, StreamingEvent
from app.services.agent.session import SessionManager
from app.services.agent.streaming import stream_sse
from app.services.agent.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class AgentRuntime:
    def __init__(self, agents_root: Optional[Path] = None):
        self.agents_root = Path(agents_root or (BASE_DIR.parent / "agents"))
        self.identity_loader = IdentityLoader(self.agents_root)
        self.llm_router = LLMRouter()
        self.memory_manager = MemoryManager(self.agents_root)
        self.session_manager = SessionManager()
        self.tool_registry = ToolRegistry()
        self.agent_loop = AgentLoop(self.llm_router, self.tool_registry)

    async def chat(
        self,
        *,
        agent_id: str,
        message: str,
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[StreamingEvent, None]:
        identity = self.identity_loader.load(agent_id)
        session = await self.session_manager.get_session(session_id) if session_id else None
        if not session:
            session = await self.session_manager.create_session(agent_id=agent_id)
        await self.session_manager.add_message(session.id, AgentMessage(role="user", content=message))
        history = await self.session_manager.load_history(session.id)
        memories = await self.memory_manager.retrieve_relevant(agent_id, message)

        assistant_chunks: List[str] = []
        tool_results = []
        try:
            async for event in self.agent_loop.run(
                agent_id=agent_id,
                session_id=session.id,
                identity=identity,
                memory_entries=memories,
                history=history[:-1],
                user_message=message,
            ):
                if event.type == "text_delta" and event.delta:
                    assistant_chunks.append(event.delta)
                elif event.type == "tool_result":
                    tool_results.append(event.data)
                elif event.type == "done" and event.message:
                    if not assistant_chunks:
                        assistant_chunks.append(event.message)
                yield event
        except Exception as exc:
            logger.exception("Agent runtime error for %s", agent_id)
            yield StreamingEvent(type="error", session_id=session.id, agent_id=agent_id, message=str(exc))
            yield StreamingEvent(type="done", session_id=session.id, agent_id=agent_id, message="")
            return

        assistant_text = "".join(assistant_chunks).strip()
        if assistant_text or tool_results:
            await self.session_manager.add_message(
                session.id,
                AgentMessage(role="assistant", content=assistant_text, tool_results=[]),
            )
            self.memory_manager.add_working_memory(agent_id, f"User: {message}\nAssistant: {assistant_text}")
            await self.session_manager.maybe_generate_title(session.id, llm_router=self.llm_router)

    async def flush_session_memory(self, agent_id: str) -> None:
        await self.memory_manager.flush_working_memory(agent_id)

    def chat_sse(self, *, agent_id: str, message: str, session_id: Optional[str] = None):
        return stream_sse(self.chat(agent_id=agent_id, message=message, session_id=session_id))

    def list_agents(self) -> List[Dict[str, str]]:
        return self.identity_loader.list_agents()

    def create_agent(self, agent_id: str) -> Dict[str, str]:
        path = self.identity_loader.ensure_agent(agent_id)
        return {"id": agent_id, "path": str(path)}

    def get_agent(self, agent_id: str) -> Dict[str, object]:
        identity = self.identity_loader.load(agent_id)
        return {"id": agent_id, "path": str(self.identity_loader.agent_dir(agent_id)), "identity": identity.model_dump()}

    def delete_agent(self, agent_id: str) -> None:
        self.identity_loader.delete_agent(agent_id)

    def get_file(self, agent_id: str, name: str) -> str:
        return self.identity_loader.get_file(agent_id, name)

    def update_file(self, agent_id: str, name: str, content: str) -> None:
        self.identity_loader.update_file(agent_id, name, content)

    def file_names(self) -> List[str]:
        return list(DEFAULT_AGENT_FILES.keys())


agent_runtime = AgentRuntime()
