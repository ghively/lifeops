import json
from unittest.mock import AsyncMock

import pytest

from app.services.agent.tool_registry import ToolRegistry
from app.services.agent.models import ToolDefinition, ToolResult


@pytest.mark.asyncio
async def test_tool_registry_lists_native_and_cli_tools(tmp_path):
    registry = ToolRegistry()
    names = {tool.name for tool in registry.list_tools()}
    assert "create_object" in names
    assert "search_knowledge" in names
    assert "codex" in names

    result = await registry.execute("write_file", {"path": str(tmp_path / "note.txt"), "content": "hello"})
    assert result.success is True
    read_result = await registry.execute("read_file", {"path": str(tmp_path / "note.txt")})
    assert read_result.content == "hello"

    schema = registry.get("create_object").openai_schema()
    assert schema["function"]["name"] == "create_object"


@pytest.mark.asyncio
async def test_tool_registry_includes_mcp_tools():
    registry = ToolRegistry()
    registry.mcp_manager.list_tool_definitions = lambda server_name=None: [
        ToolDefinition(
            name="mcp__filesystem__read",
            description="[MCP:filesystem] Read",
            parameters_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            safety_level="external",
            source="mcp",
        )
    ]
    registry.mcp_manager.execute_tool = AsyncMock(
        return_value=ToolResult(tool_name="mcp__filesystem__read", content="ok", data={"server_name": "filesystem"})
    )

    names = {tool.name for tool in registry.list_tools()}
    assert "mcp__filesystem__read" in names

    schemas = registry.list_openai_tools()
    assert any(schema["function"]["name"] == "mcp__filesystem__read" for schema in schemas)

    result = await registry.execute("mcp__filesystem__read", {"path": "/tmp/demo"})
    assert result.content == "ok"
