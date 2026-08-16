import pytest

from app.services.agent.mcp_client import MCPClientManager
from app.services.agent.models import MCPServerConfig


class FakeTool:
    def __init__(self, name: str, description: str, input_schema: dict):
        self.name = name
        self.description = description
        self.inputSchema = input_schema


class FakeTextContent:
    def __init__(self, text: str):
        self.text = text

    def model_dump(self):
        return {"type": "text", "text": self.text}


class FakeToolResult:
    def __init__(self, text: str, *, is_error: bool = False, structured_content=None):
        self.content = [FakeTextContent(text)]
        self.isError = is_error
        self.structuredContent = structured_content


class FakeListToolsResult:
    def __init__(self, tools):
        self.tools = tools


class FakeSession:
    def __init__(self, *, tools=None, call_result=None, call_error=None, ping_error=None):
        self._tools = tools or []
        self._call_result = call_result or FakeToolResult("ok")
        self._call_error = call_error
        self._ping_error = ping_error

    async def initialize(self):
        return None

    async def list_tools(self):
        return FakeListToolsResult(self._tools)

    async def call_tool(self, name, arguments=None):
        if self._call_error:
            raise self._call_error
        return self._call_result

    async def send_ping(self):
        if self._ping_error:
            raise self._ping_error
        return None


@pytest.mark.asyncio
async def test_mcp_manager_connects_discovers_and_executes(monkeypatch):
    manager = MCPClientManager()
    session = FakeSession(
        tools=[FakeTool("search", "Search docs", {"type": "object", "properties": {"q": {"type": "string"}}})],
        call_result=FakeToolResult("match found", structured_content={"hits": 1}),
    )

    async def fake_open_session(config, exit_stack):
        return session

    monkeypatch.setattr(manager, "_open_session", fake_open_session)

    await manager.configure_server(
        MCPServerConfig(name="docs", transport="stdio", command="npx"),
        persist=False,
    )
    status = await manager.connect_server("docs")

    assert status.connected is True
    tools = manager.list_tool_definitions()
    assert [tool.name for tool in tools] == ["mcp__docs__search"]
    result = await manager.execute_tool("mcp__docs__search", {"q": "mcp"})
    assert result.success is True
    assert result.content == "match found"
    assert result.data["server_name"] == "docs"
    assert result.data["structured_content"] == {"hits": 1}


@pytest.mark.asyncio
async def test_mcp_manager_handles_tool_failure(monkeypatch):
    manager = MCPClientManager()
    session = FakeSession(
        tools=[FakeTool("broken", "Broken tool", {"type": "object", "properties": {}})],
        call_error=RuntimeError("server crashed"),
    )

    async def fake_open_session(config, exit_stack):
        return session

    monkeypatch.setattr(manager, "_open_session", fake_open_session)

    await manager.configure_server(
        MCPServerConfig(name="broken-server", transport="stdio", command="npx"),
        persist=False,
    )
    await manager.connect_server("broken-server")
    result = await manager.execute_tool("mcp__broken-server__broken", {})

    assert result.success is False
    assert result.error == "server crashed"
    status = await manager.get_server_status("broken-server")
    assert status.state == "error"


@pytest.mark.asyncio
async def test_mcp_manager_disconnect_clears_tools(monkeypatch):
    manager = MCPClientManager()
    session = FakeSession(
        tools=[FakeTool("list", "List files", {"type": "object", "properties": {}})],
    )

    async def fake_open_session(config, exit_stack):
        return session

    monkeypatch.setattr(manager, "_open_session", fake_open_session)

    await manager.configure_server(
        MCPServerConfig(name="fs", transport="stdio", command="npx"),
        persist=False,
    )
    await manager.connect_server("fs")
    assert manager.list_tool_definitions()

    status = await manager.disconnect_server("fs")
    assert status.connected is False
    assert manager.list_tool_definitions() == []


@pytest.mark.asyncio
async def test_mcp_manager_health_check_marks_error(monkeypatch):
    manager = MCPClientManager()
    session = FakeSession(
        tools=[FakeTool("status", "Status", {"type": "object", "properties": {}})],
        ping_error=RuntimeError("ping failed"),
    )

    async def fake_open_session(config, exit_stack):
        return session

    monkeypatch.setattr(manager, "_open_session", fake_open_session)

    await manager.configure_server(
        MCPServerConfig(name="remote", transport="http", url="http://localhost:3001/mcp"),
        persist=False,
    )
    await manager.connect_server("remote")
    statuses = await manager.health_check("remote")

    assert statuses[0].state == "error"
    assert statuses[0].error == "ping failed"
