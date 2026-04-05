"""ReAct-style agent loop."""
from __future__ import annotations

import json
import logging
import asyncio
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.services.agent.models import AgentIdentity, AgentMessage, StreamingEvent, SubAgentTask, ToolResult

logger = logging.getLogger(__name__)


class AgentLoop:
    def __init__(
        self,
        llm_router,
        tool_registry,
        collaboration_service=None,
        sub_agent_runner=None,
        max_iterations: int = 10,
        max_tokens: int = 12000,
    ):
        self.llm_router = llm_router
        self.tool_registry = tool_registry
        self.collaboration_service = collaboration_service
        self.sub_agent_runner = sub_agent_runner
        self.max_iterations = max_iterations
        self.max_tokens = max_tokens

    async def run(
        self,
        *,
        agent_id: str,
        session_id: str,
        identity: AgentIdentity,
        memory_entries: List[Any],
        history: List[AgentMessage],
        user_message: str,
        execution_depth: int = 0,
        shared_context: Optional[Dict[str, Any]] = None,
        allowed_tools: Optional[List[str]] = None,
    ) -> AsyncGenerator[StreamingEvent, None]:
        messages = self._build_messages(identity, memory_entries, history, user_message, shared_context=shared_context)
        token_budget = self._estimate_messages_tokens(messages)

        for iteration in range(self.max_iterations):
            yield StreamingEvent(type="thinking", session_id=session_id, agent_id=agent_id, data={"iteration": iteration + 1, "tokens": token_budget})
            response = await self.llm_router.complete(
                messages,
                tools=self._list_tools(identity, execution_depth=execution_depth, allowed_tools=allowed_tools),
                config=identity.llm,
            )
            tool_calls = response.get("tool_calls") or []
            if tool_calls:
                assistant_message = {"role": "assistant", "content": response.get("content", ""), "tool_calls": tool_calls}
                messages.append(assistant_message)
                for tool_call in tool_calls:
                    function = tool_call.get("function", {})
                    tool_name = function.get("name")
                    try:
                        arguments = json.loads(function.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        arguments = {}
                    yield StreamingEvent(type="tool_start", session_id=session_id, agent_id=agent_id, tool_name=tool_name, data={"arguments": arguments})
                    if tool_name == "message_agent":
                        result = await self._execute_agent_message(
                            agent_id=agent_id,
                            arguments=arguments,
                            execution_depth=execution_depth,
                        )
                    elif tool_name == "spawn_subagents":
                        result = await self._execute_sub_agents(
                            agent_id=agent_id,
                            session_id=session_id,
                            arguments=arguments,
                            execution_depth=execution_depth,
                            emit_event=lambda event: event,
                        )
                        if isinstance(result, tuple):
                            result, subagent_events = result
                            for event in subagent_events:
                                yield event
                    else:
                        result = await self.tool_registry.execute(tool_name, arguments, allowed_tools=allowed_tools)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.get("id"),
                        "name": tool_name,
                        "content": result.content or result.error or "",
                    })
                    yield StreamingEvent(
                        type="tool_result",
                        session_id=session_id,
                        agent_id=agent_id,
                        tool_name=tool_name,
                        data=result.model_dump(),
                    )
                token_budget = self._estimate_messages_tokens(messages)
                if token_budget > self.max_tokens:
                    raise RuntimeError("Token budget exceeded during tool loop")
                continue

            content = response.get("content", "")
            for chunk in self._collect_stream(content):
                yield StreamingEvent(type="text_delta", session_id=session_id, agent_id=agent_id, delta=chunk)
            yield StreamingEvent(type="done", session_id=session_id, agent_id=agent_id, message=content)
            return

        raise RuntimeError("Max agent iterations exceeded")

    def _collect_stream(self, content: str) -> List[str]:
        if not content:
            return []
        chunk_size = 120
        return [content[index:index + chunk_size] for index in range(0, len(content), chunk_size)]

    def _build_messages(
        self,
        identity: AgentIdentity,
        memory_entries: List[Any],
        history: List[AgentMessage],
        user_message: str,
        *,
        shared_context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = [{"role": "system", "content": identity.system_prompt}]
        if self.collaboration_service:
            collaboration_context = self.collaboration_service.build_context_block(user_message, shared_context=shared_context)
            if collaboration_context:
                messages.append({"role": "system", "content": collaboration_context})
        if memory_entries:
            memory_blob = "\n\n".join(entry.content for entry in memory_entries)
            messages.append({"role": "system", "content": f"Relevant memory:\n{memory_blob}"})
        for item in history:
            payload = {"role": item.role, "content": item.content}
            if item.role == "tool" and item.name:
                payload["name"] = item.name
            messages.append(payload)
        messages.append({"role": "user", "content": user_message})
        return messages

    def _estimate_messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        return sum(self.llm_router.count_tokens(message.get("content", "")) for message in messages)

    def _list_tools(self, identity: AgentIdentity, *, execution_depth: int, allowed_tools: Optional[List[str]]) -> List[Dict[str, Any]]:
        tools = self.tool_registry.list_openai_tools(allowed_tools=allowed_tools)
        if not allowed_tools or "message_agent" in set(allowed_tools):
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "message_agent",
                        "description": "Send a message to another runtime agent and receive its response.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "agent_id": {"type": "string"},
                                "message": {"type": "string"},
                                "shared_context": {"type": "object"},
                                "timeout_seconds": {"type": "integer", "default": 90},
                            },
                            "required": ["agent_id", "message"],
                        },
                    },
                }
            )
        if execution_depth == 0 and (not allowed_tools or "spawn_subagents" in set(allowed_tools)):
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "spawn_subagents",
                        "description": "Delegate one or more tasks to runtime sub-agents in parallel.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "tasks": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "agent_id": {"type": "string"},
                                            "prompt": {"type": "string"},
                                            "allowed_tools": {"type": "array", "items": {"type": "string"}},
                                            "shared_context": {"type": "object"},
                                            "timeout_seconds": {"type": "integer", "default": 90},
                                        },
                                        "required": ["agent_id", "prompt"],
                                    },
                                }
                            },
                            "required": ["tasks"],
                        },
                    },
                }
            )
        return tools

    async def _execute_agent_message(self, *, agent_id: str, arguments: Dict[str, Any], execution_depth: int) -> ToolResult:
        if self.collaboration_service is None:
            return ToolResult(tool_name="message_agent", success=False, error="Collaboration is unavailable", content="")
        result = await self.collaboration_service.route_message(
            from_agent_id=agent_id,
            to_agent_id=str(arguments.get("agent_id") or ""),
            message=str(arguments.get("message") or ""),
            shared_context=arguments.get("shared_context") or {},
            timeout_seconds=int(arguments.get("timeout_seconds") or 90),
        )
        return ToolResult(
            tool_name="message_agent",
            content=result["response"],
            data=result,
        )

    async def _execute_sub_agents(
        self,
        *,
        agent_id: str,
        session_id: str,
        arguments: Dict[str, Any],
        execution_depth: int,
        emit_event=None,
    ):
        if execution_depth >= 1:
            return ToolResult(tool_name="spawn_subagents", success=False, error="Sub-agent depth limit reached", content="")
        if self.sub_agent_runner is None:
            return ToolResult(tool_name="spawn_subagents", success=False, error="Sub-agent runner is unavailable", content="")

        tasks = [SubAgentTask(**item) for item in (arguments.get("tasks") or [])]
        subagent_events: List[StreamingEvent] = []
        if not tasks:
            return ToolResult(tool_name="spawn_subagents", success=False, error="No sub-agent tasks provided", content="")

        async def run_task(task: SubAgentTask):
            subagent_events.append(
                StreamingEvent(
                    type="subagent_start",
                    session_id=session_id,
                    agent_id=agent_id,
                    data={"agent_id": task.agent_id, "prompt": task.prompt},
                )
            )
            return await self.sub_agent_runner(
                parent_agent_id=agent_id,
                task=task,
                execution_depth=execution_depth + 1,
            )

        results = await asyncio.gather(*(run_task(task) for task in tasks))
        payload = []
        for result in results:
            subagent_events.append(
                StreamingEvent(
                    type="subagent_result",
                    session_id=session_id,
                    agent_id=agent_id,
                    data=result.model_dump(),
                )
            )
            payload.append(result.model_dump())
        return (
            ToolResult(
                tool_name="spawn_subagents",
                content=json.dumps(payload),
                data={"results": payload},
            ),
            subagent_events,
        )
