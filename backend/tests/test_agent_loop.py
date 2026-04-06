import pytest
from unittest.mock import AsyncMock

from app.services.agent.agent_loop import AgentLoop
from app.services.agent.models import AgentIdentity, AgentMessage, LLMProviderConfig, SubAgentResult, ToolResult


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

    async def execute(self, name, arguments, *, allowed_tools=None, context=None, identity=None):
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


class FakeParallelLLMRouter(FakeLLMRouter):
    async def complete(self, messages, tools=None, config=None):
        self.calls += 1
        if self.calls == 1:
            return {
                "content": "",
                "tool_calls": [
                    {"id": "call-1", "function": {"name": "search_knowledge", "arguments": "{\"query\": \"phase 1\"}"}},
                    {"id": "call-2", "function": {"name": "explode", "arguments": "{}"}},
                ],
            }
        return {"content": "Recovered answer", "tool_calls": []}


@pytest.mark.asyncio
async def test_agent_loop_converts_parallel_tool_exceptions_to_tool_results():
    loop = AgentLoop(FakeParallelLLMRouter(), FakeToolRegistry())
    identity = AgentIdentity(
        agent_id="tester",
        name="Tester",
        system_prompt="You are a tester.",
        llm=LLMProviderConfig(),
    )
    loop._execute_tool_call = AsyncMock(side_effect=[
        (
            {"id": "call-1"},
            "search_knowledge",
            {"query": "phase 1"},
            ToolResult(tool_name="search_knowledge", content="[]", data={"results": []}),
            [],
        ),
        RuntimeError("tool crashed"),
    ])

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

    tool_results = [event for event in events if event.type == "tool_result"]
    assert len(tool_results) == 2
    assert tool_results[1].data["success"] is False
    assert tool_results[1].data["error"] == "tool crashed"
    assert tool_results[1].data["tool_call_id"] == "call-2"
    assert events[-1].type == "done"


@pytest.mark.asyncio
async def test_execute_sub_agents_converts_parallel_failures_to_error_results():
    async def sub_agent_runner(*, parent_agent_id, task, execution_depth):
        if task.agent_id == "broken":
            raise RuntimeError("sub-agent crashed")
        return SubAgentResult(agent_id=task.agent_id, content=f"done:{task.prompt}")

    loop = AgentLoop(FakeLLMRouter(), FakeToolRegistry(), sub_agent_runner=sub_agent_runner)
    result, events = await loop._execute_sub_agents(
        agent_id="tester",
        session_id="session-1",
        arguments={"tasks": [{"agent_id": "worker-1", "prompt": "ok"}, {"agent_id": "broken", "prompt": "fail"}]},
        execution_depth=0,
    )

    assert result.success is True
    assert len(result.data["results"]) == 2
    assert result.data["results"][1]["success"] is False
    assert result.data["results"][1]["error"] == "sub-agent crashed"
    assert result.data["results"][1]["tool_results"][0]["success"] is False
    assert [event.type for event in events] == [
        "subagent_start",
        "subagent_start",
        "subagent_result",
        "subagent_result",
    ]
