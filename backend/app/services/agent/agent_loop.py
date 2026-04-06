"""ReAct-style agent loop."""
from __future__ import annotations

import json
import logging
import asyncio
from math import floor
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.services.agent.audit import AgentAuditLogger
from app.services.agent.sandbox import ToolApprovalRequired, tool_approval_manager
from app.services.agent.security import AgentSecurityManager
from app.services.websocket_manager import WebSocketEvents, websocket_manager
from app.services.agent.models import AgentIdentity, AgentMessage, StreamingEvent, SubAgentResult, SubAgentTask, ToolResult

logger = logging.getLogger(__name__)


class AgentLoop:
    MODEL_CONTEXT_WINDOWS = {
        "gpt-4o-mini": 128000,
        "gpt-4o": 128000,
        "gpt-5": 200000,
    }

    def __init__(
        self,
        llm_router,
        tool_registry,
        collaboration_service=None,
        sub_agent_runner=None,
        security_manager: Optional[AgentSecurityManager] = None,
        audit_logger: Optional[AgentAuditLogger] = None,
        max_iterations: int = 10,
        max_tokens: int = 12000,
    ):
        self.llm_router = llm_router
        self.tool_registry = tool_registry
        self.collaboration_service = collaboration_service
        self.sub_agent_runner = sub_agent_runner
        self.security_manager = security_manager or AgentSecurityManager()
        self.audit_logger = audit_logger
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
        user_id: Optional[str] = None,
    ) -> AsyncGenerator[StreamingEvent, None]:
        sanitized_user_message = self.security_manager.sanitize_user_input(user_message)
        findings = await self.security_manager.maybe_log_injection_attempt(
            agent_id=agent_id,
            session_id=session_id,
            user_id=user_id,
            source="user_input",
            text=user_message,
        )
        if findings:
            yield StreamingEvent(type="security_warning", session_id=session_id, agent_id=agent_id, data={"patterns": findings})

        hardened_identity = identity.model_copy(deep=True)
        hardened_identity.system_prompt = self.security_manager.harden_system_prompt(identity.system_prompt)
        messages = self._build_messages(hardened_identity, memory_entries, history, sanitized_user_message, shared_context=shared_context)
        token_budget = self._estimate_messages_tokens(messages)
        token_usage = {"prompt_tokens": token_budget, "completion_tokens": 0, "total_tokens": token_budget}
        model_context_window = self._context_window_for_model(identity.model)
        allocation = self._budget_allocation(model_context_window)

        for iteration in range(self.max_iterations):
            warning = token_budget >= floor(model_context_window * 0.9)
            yield StreamingEvent(
                type="thinking",
                session_id=session_id,
                agent_id=agent_id,
                data={"iteration": iteration + 1, "tokens": token_budget, "budget": allocation, "warning": warning},
            )
            response = await self.llm_router.complete(
                messages,
                tools=self._list_tools(hardened_identity, execution_depth=execution_depth, allowed_tools=allowed_tools),
                config=identity.llm,
            )
            usage = response.get("usage") or {}
            token_usage["prompt_tokens"] = max(token_usage["prompt_tokens"], int(usage.get("prompt_tokens") or token_budget))
            token_usage["completion_tokens"] += int(usage.get("completion_tokens") or 0)
            token_usage["total_tokens"] = token_usage["prompt_tokens"] + token_usage["completion_tokens"]
            tool_calls = response.get("tool_calls") or []
            if tool_calls:
                assistant_message = {"role": "assistant", "content": response.get("content", ""), "tool_calls": tool_calls}
                messages.append(assistant_message)
                parsed_calls = []
                for tool_call in tool_calls:
                    function = tool_call.get("function", {})
                    tool_name = function.get("name")
                    try:
                        arguments = json.loads(function.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        arguments = {}
                    parsed_calls.append((tool_call, tool_name, arguments))
                    yield StreamingEvent(
                        type="tool_start",
                        session_id=session_id,
                        agent_id=agent_id,
                        tool_name=tool_name,
                        data={"arguments": arguments, "tool_call_id": tool_call.get("id")},
                    )

                results = await asyncio.gather(
                    *[
                        self._execute_tool_call(
                            agent_id=agent_id,
                            session_id=session_id,
                            identity=hardened_identity,
                            execution_depth=execution_depth,
                            allowed_tools=allowed_tools,
                            tool_call=tool_call,
                            tool_name=tool_name,
                            arguments=arguments,
                            user_id=user_id,
                        )
                        for tool_call, tool_name, arguments in parsed_calls
                    ],
                    return_exceptions=True,
                )
                normalized_results = []
                for (tool_call, tool_name, arguments), raw_result in zip(parsed_calls, results):
                    if isinstance(raw_result, Exception):
                        normalized_results.append((tool_call, tool_name, arguments, self._tool_result_from_exception(tool_name or "tool", raw_result), []))
                        continue
                    normalized_results.append(raw_result)

                for tool_call, tool_name, _arguments, result, emitted_events in normalized_results:
                    for event in emitted_events:
                        yield event
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
                        data={**result.model_dump(), "tool_call_id": tool_call.get("id")},
                    )
                token_budget = self._estimate_messages_tokens(messages)
                if token_budget > min(self.max_tokens, model_context_window):
                    raise RuntimeError("Token budget exceeded during tool loop")
                continue

            content = response.get("content", "")
            for chunk in self._collect_stream(content):
                yield StreamingEvent(type="text_delta", session_id=session_id, agent_id=agent_id, delta=chunk)
            yield StreamingEvent(type="done", session_id=session_id, agent_id=agent_id, message=content, data={"token_usage": token_usage, "budget": allocation})
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

    def _context_window_for_model(self, model: str) -> int:
        return self.MODEL_CONTEXT_WINDOWS.get(model, self.max_tokens)

    def _budget_allocation(self, context_window: int) -> Dict[str, int]:
        return {
            "system_prompt": floor(context_window * 0.25),
            "memory": floor(context_window * 0.25),
            "history": floor(context_window * 0.40),
            "response": floor(context_window * 0.10),
            "context_window": context_window,
        }

    def _tool_result_from_exception(self, tool_name: str, exc: Exception) -> ToolResult:
        logger.exception("Agent tool execution crashed for %s", tool_name)
        return ToolResult(tool_name=tool_name, success=False, error=str(exc), content="")

    def _subagent_result_from_exception(self, task: SubAgentTask, exc: Exception) -> SubAgentResult:
        return SubAgentResult(
            agent_id=task.agent_id,
            success=False,
            content="",
            error=str(exc),
            tool_results=[self._tool_result_from_exception("spawn_subagents", exc)],
        )

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

    async def _execute_tool_call(
        self,
        *,
        agent_id: str,
        session_id: str,
        identity: AgentIdentity,
        execution_depth: int,
        allowed_tools: Optional[List[str]],
        tool_call: Dict[str, Any],
        tool_name: str,
        arguments: Dict[str, Any],
        user_id: Optional[str],
    ):
        emitted_events: List[StreamingEvent] = []
        try:
            if tool_name == "message_agent":
                result = await self._execute_agent_message(agent_id=agent_id, arguments=arguments, execution_depth=execution_depth)
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
                    emitted_events.extend(subagent_events)
            else:
                result = await self.tool_registry.execute(
                    tool_name,
                    arguments,
                    allowed_tools=allowed_tools,
                    context={"agent_id": agent_id, "session_id": session_id, "user_id": user_id},
                    identity=identity,
                )
        except ToolApprovalRequired as approval:
            emitted_events.append(StreamingEvent(type="approval_required", session_id=session_id, agent_id=agent_id, tool_name=tool_name, data=approval.request))
            if user_id:
                await websocket_manager.broadcast(WebSocketEvents.agent_approval_required(user_id, approval.request))
            approved = await tool_approval_manager.wait_for_decision(approval.request["request_id"], timeout_seconds=approval.request.get("timeout_seconds", 60))
            if not approved:
                result = ToolResult(tool_name=tool_name, success=False, error="Tool execution rejected by user", content="")
            else:
                result = await self.tool_registry.execute(
                    tool_name,
                    arguments,
                    allowed_tools=allowed_tools,
                    context={"agent_id": agent_id, "session_id": session_id, "user_id": user_id, "approval_granted": True},
                    identity=identity,
                )
        findings = await self.security_manager.maybe_log_injection_attempt(
            agent_id=agent_id,
            session_id=session_id,
            user_id=user_id,
            source=f"tool:{tool_name}",
            text=result.content or result.error or "",
        )
        if findings:
            emitted_events.append(StreamingEvent(type="security_warning", session_id=session_id, agent_id=agent_id, tool_name=tool_name, data={"patterns": findings}))
        return tool_call, tool_name, arguments, result, emitted_events

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

        results = await asyncio.gather(*(run_task(task) for task in tasks), return_exceptions=True)
        payload = []
        for task, result in zip(tasks, results):
            if isinstance(result, Exception):
                result = self._subagent_result_from_exception(task, result)
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
