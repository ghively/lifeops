"""Main orchestrator for the Phase 1 agent runtime."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.config import BASE_DIR
from app.services.agent.agent_loop import AgentLoop
from app.services.agent.collaboration import AgentCollaborationService
from app.services.agent.identity import DEFAULT_AGENT_FILES, IdentityLoader
from app.services.agent.llm_router import LLMRouter
from app.services.agent.memory import MemoryManager
from app.services.agent.memory_curation import MemoryCurationService
from app.services.agent.models import AgentMessage, StreamingEvent, SubAgentResult, SubAgentTask, ToolResult
from app.services.agent.scheduler import AgentScheduler
from app.services.agent.session import SessionManager
from app.services.agent.streaming import stream_sse
from app.services.agent.templates import AgentTemplateService
from app.services.agent.tool_registry import ToolRegistry
from app.services.agent.webhooks import AgentWebhookService

logger = logging.getLogger(__name__)


class AgentRuntime:
    def __init__(self, agents_root: Optional[Path] = None):
        self.agents_root = Path(agents_root or (BASE_DIR.parent / "agents"))
        self.identity_loader = IdentityLoader(self.agents_root)
        self.llm_router = LLMRouter()
        self.memory_manager = MemoryManager(self.agents_root)
        self.session_manager = SessionManager()
        self.tool_registry = ToolRegistry()
        self.collaboration_service = AgentCollaborationService(self.identity_loader)
        self.memory_curation = MemoryCurationService(self.agents_root, self.identity_loader, self.llm_router)
        self.templates = AgentTemplateService()
        self.scheduler = AgentScheduler()
        self.webhooks = AgentWebhookService()
        self.agent_loop = AgentLoop(
            self.llm_router,
            self.tool_registry,
            collaboration_service=self.collaboration_service,
            sub_agent_runner=self.run_sub_agent_task,
        )
        self.collaboration_service.bind_runtime(self)
        self.scheduler.bind_runtime(self, self.memory_curation)
        self.webhooks.bind_runtime(self)

    async def start(self) -> None:
        await self.tool_registry.mcp_manager.initialize()
        await self.scheduler.start()

    async def stop(self) -> None:
        await self.scheduler.stop()
        await self.tool_registry.mcp_manager.shutdown()

    async def chat(
        self,
        *,
        agent_id: str,
        message: str,
        session_id: Optional[str] = None,
        shared_context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[StreamingEvent, None]:
        session = await self._get_or_create_session(agent_id, session_id)
        await self.session_manager.add_message(session.id, AgentMessage(role="user", content=message))

        assistant_chunks: List[str] = []
        tool_results: List[ToolResult] = []
        try:
            async for event in self._run_agent_events(
                agent_id=agent_id,
                message=message,
                session_id=session.id,
                shared_context=shared_context,
            ):
                if event.type == "text_delta" and event.delta:
                    assistant_chunks.append(event.delta)
                elif event.type == "tool_result":
                    tool_results.append(ToolResult(**event.data))
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
                AgentMessage(role="assistant", content=assistant_text, tool_results=tool_results),
            )
            self.memory_manager.add_working_memory(agent_id, f"User: {message}\nAssistant: {assistant_text}")
            await self.session_manager.maybe_generate_title(session.id, llm_router=self.llm_router)

    async def flush_session_memory(self, agent_id: str) -> None:
        await self.memory_manager.flush_working_memory(agent_id)

    def chat_sse(self, *, agent_id: str, message: str, session_id: Optional[str] = None, shared_context: Optional[Dict[str, Any]] = None):
        return stream_sse(self.chat(agent_id=agent_id, message=message, session_id=session_id, shared_context=shared_context))

    def list_agents(self) -> List[Dict[str, str]]:
        return self.identity_loader.list_agents()

    def create_agent(self, agent_id: str, *, template_id: Optional[str] = None) -> Dict[str, str]:
        path = self.identity_loader.ensure_agent(agent_id)
        if template_id:
            template = self.templates.get_template(template_id)
            for name, content in template.files.items():
                self.identity_loader.update_file(agent_id, name, content)
        return {"id": agent_id, "path": str(path)}

    def get_agent(self, agent_id: str) -> Dict[str, object]:
        identity = self.identity_loader.load(agent_id)
        return {"id": agent_id, "path": str(self.identity_loader.agent_dir(agent_id)), "identity": identity.model_dump()}

    async def list_sessions(self, agent_id: Optional[str] = None) -> List[Dict[str, object]]:
        sessions = await self.session_manager.list_sessions(agent_id)
        return [session.model_dump() for session in sessions]

    async def get_session_messages(self, session_id: str) -> List[Dict[str, object]]:
        history = await self.session_manager.load_history(session_id, limit=200)
        return [message.model_dump() for message in history]

    async def delete_session(self, session_id: str) -> None:
        await self.session_manager.delete_session(session_id)

    def delete_agent(self, agent_id: str) -> None:
        self.identity_loader.delete_agent(agent_id)

    def get_file(self, agent_id: str, name: str) -> str:
        return self.identity_loader.get_file(agent_id, name)

    def update_file(self, agent_id: str, name: str, content: str) -> None:
        self.identity_loader.update_file(agent_id, name, content)

    def file_names(self) -> List[str]:
        return list(DEFAULT_AGENT_FILES.keys())

    def list_templates(self) -> List[Dict[str, Any]]:
        return [template.model_dump() for template in self.templates.list_templates()]

    async def create_scheduled_task(self, **payload) -> Dict[str, Any]:
        task = await self.scheduler.create_task(**payload)
        return task.model_dump()

    async def list_scheduled_tasks(self, agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return [task.model_dump() for task in await self.scheduler.list_tasks(agent_id)]

    async def delete_scheduled_task(self, task_id: str) -> None:
        await self.scheduler.delete_task(task_id)

    async def run_scheduled_task(self, task_id: str) -> Dict[str, Any]:
        return await self.scheduler.trigger_task(task_id)

    async def curate_memory(self, agent_id: str, *, frequency: str = "daily") -> Dict[str, object]:
        return await self.memory_curation.curate_agent_memory(agent_id, frequency=frequency)

    async def create_webhook(self, **payload) -> Dict[str, Any]:
        webhook = await self.webhooks.create_webhook(**payload)
        return webhook.model_dump()

    async def list_webhooks(self, agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return [webhook.model_dump() for webhook in await self.webhooks.list_webhooks(agent_id)]

    async def delete_webhook(self, webhook_id: str) -> None:
        await self.webhooks.delete_webhook(webhook_id)

    async def handle_incoming_webhook(self, *, hook_id: str, body: bytes, signature: str, event_type: Optional[str] = None) -> Dict[str, Any]:
        return await self.webhooks.verify_and_handle(hook_id=hook_id, body=body, signature=signature, event_type=event_type)

    async def route_agent_message(self, **payload) -> Dict[str, Any]:
        return await self.collaboration_service.route_message(**payload)

    async def run_sub_agent_task(self, *, parent_agent_id: str, task: SubAgentTask, execution_depth: int) -> SubAgentResult:
        try:
            result = await asyncio.wait_for(
                self.run_background_task(
                    agent_id=task.agent_id,
                    message=task.prompt,
                    shared_context={**task.shared_context, "parent_agent_id": parent_agent_id},
                    allowed_tools=task.allowed_tools or None,
                    execution_depth=execution_depth,
                    metadata={"parent_agent_id": parent_agent_id, "subagent": True, "depth": execution_depth},
                ),
                timeout=task.timeout_seconds,
            )
            return SubAgentResult(
                agent_id=task.agent_id,
                success=True,
                content=result["content"],
                session_id=result["session_id"],
                tool_results=[ToolResult(**item) if not isinstance(item, ToolResult) else item for item in result["tool_results"]],
            )
        except asyncio.TimeoutError:
            return SubAgentResult(agent_id=task.agent_id, success=False, error=f"Sub-agent timed out after {task.timeout_seconds}s")
        except Exception as exc:
            logger.exception("Sub-agent execution failed for %s", task.agent_id)
            return SubAgentResult(agent_id=task.agent_id, success=False, error=str(exc))

    async def run_background_task(
        self,
        *,
        agent_id: str,
        message: str,
        session_id: Optional[str] = None,
        shared_context: Optional[Dict[str, Any]] = None,
        allowed_tools: Optional[List[str]] = None,
        execution_depth: int = 0,
        timeout_seconds: int = 120,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        session = await self._get_or_create_session(agent_id, session_id, metadata=metadata)
        await self.session_manager.add_message(session.id, AgentMessage(role="user", content=message, metadata=metadata or {}))
        assistant_chunks: List[str] = []
        tool_results: List[ToolResult] = []

        async def consume():
            async for event in self._run_agent_events(
                agent_id=agent_id,
                message=message,
                session_id=session.id,
                shared_context=shared_context,
                allowed_tools=allowed_tools,
                execution_depth=execution_depth,
            ):
                if event.type == "text_delta" and event.delta:
                    assistant_chunks.append(event.delta)
                elif event.type == "tool_result":
                    tool_results.append(ToolResult(**event.data))
                elif event.type == "done" and event.message and not assistant_chunks:
                    assistant_chunks.append(event.message)

        await asyncio.wait_for(consume(), timeout=timeout_seconds)

        assistant_text = "".join(assistant_chunks).strip()
        await self.session_manager.add_message(
            session.id,
            AgentMessage(role="assistant", content=assistant_text, tool_results=tool_results, metadata=metadata or {}),
        )
        return {
            "agent_id": agent_id,
            "session_id": session.id,
            "content": assistant_text,
            "tool_results": [result.model_dump() for result in tool_results],
        }

    async def _get_or_create_session(self, agent_id: str, session_id: Optional[str], metadata: Optional[Dict[str, Any]] = None):
        session = await self.session_manager.get_session(session_id) if session_id else None
        if not session:
            session = await self.session_manager.create_session(agent_id=agent_id, metadata=metadata)
        return session

    async def _run_agent_events(
        self,
        *,
        agent_id: str,
        message: str,
        session_id: str,
        shared_context: Optional[Dict[str, Any]] = None,
        allowed_tools: Optional[List[str]] = None,
        execution_depth: int = 0,
    ) -> AsyncGenerator[StreamingEvent, None]:
        identity = self.identity_loader.load(agent_id)
        if identity.mcp_servers:
            await self.tool_registry.mcp_manager.ensure_servers(identity.mcp_servers, persist=False)
        history = await self.session_manager.load_history(session_id)
        memories = await self.memory_manager.retrieve_relevant(agent_id, message)
        async for event in self.agent_loop.run(
            agent_id=agent_id,
            session_id=session_id,
            identity=identity,
            memory_entries=memories,
            history=history[:-1],
            user_message=message,
            execution_depth=execution_depth,
            shared_context=shared_context,
            allowed_tools=allowed_tools,
        ):
            yield event


agent_runtime = AgentRuntime()
