"""ReAct-style agent loop."""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.services.agent.models import AgentIdentity, AgentMessage, StreamingEvent

logger = logging.getLogger(__name__)


class AgentLoop:
    def __init__(self, llm_router, tool_registry, max_iterations: int = 10, max_tokens: int = 12000):
        self.llm_router = llm_router
        self.tool_registry = tool_registry
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
    ) -> AsyncGenerator[StreamingEvent, None]:
        messages = self._build_messages(identity, memory_entries, history, user_message)
        token_budget = self._estimate_messages_tokens(messages)

        for iteration in range(self.max_iterations):
            yield StreamingEvent(type="thinking", session_id=session_id, agent_id=agent_id, data={"iteration": iteration + 1, "tokens": token_budget})
            response = await self.llm_router.complete(
                messages,
                tools=self.tool_registry.list_openai_tools(),
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
                    result = await self.tool_registry.execute(tool_name, arguments)
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
    ) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = [{"role": "system", "content": identity.system_prompt}]
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
