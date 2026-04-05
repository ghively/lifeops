import pytest

from app.services.agent.agent_loop import AgentLoop
from app.services.agent.models import AgentIdentity, AgentMessage, LLMProviderConfig, ToolDefinition, ToolResult


class FakeLLMRouter:
    def __init__(self):
        self.calls = 0

    def count_tokens(self, text, model=None):
        return max(1, len(text) // 4)

    async def complete(self, messages, tools=None, config=None):
        self.calls += 1
        if self.calls == 1:
            return {
                "content": "",
                "tool_calls": [{
                    "id": "call-1",
                    "function": {"name": "search_knowledge", "arguments": "{\"query\": \"phase 1\"}"},
                }],
            }
        return {"content": "Final answer", "tool_calls": []}

    async def stream_complete(self, messages, tools=None, config=None):
        yield "Final "
        yield "answer"


class FakeToolRegistry:
    def list_openai_tools(self, *, allowed_tools=None):
        return [{"type": "function", "function": {"name": "search_knowledge", "parameters": {"type": "object"}}}]

    async def execute(self, name, arguments, *, allowed_tools=None):
        return ToolResult(tool_name=name, content="[]", data={"results": []})


@pytest.mark.asyncio
async def test_agent_loop_handles_tool_call_then_streams_text():
    loop = AgentLoop(FakeLLMRouter(), FakeToolRegistry())
    identity = AgentIdentity(
        agent_id="tester",
        name="Tester",
        system_prompt="You are a tester.",
        llm=LLMProviderConfig(),
    )
    events = []
    async for event in loop.run(
        agent_id="tester",
        session_id="session-1",
        identity=identity,
        memory_entries=[],
        history=[AgentMessage(role="user", content="hello")],
        user_message="Find phase 1",
    ):
        events.append(event)

    event_types = [event.type for event in events]
    assert "tool_start" in event_types
    assert "tool_result" in event_types
    assert event_types[-1] == "done"
    assert "".join(event.delta or "" for event in events if event.type == "text_delta") == "Final answer"
