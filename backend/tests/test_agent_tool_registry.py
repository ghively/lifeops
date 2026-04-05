import json

import pytest

from app.services.agent.tool_registry import ToolRegistry


@pytest.mark.asyncio
async def test_tool_registry_lists_native_and_cli_tools(tmp_path):
    registry = ToolRegistry()
    names = {tool.name for tool in registry.list_tools()}
    assert "create_object" in names
    assert "search_knowledge" in names
    assert "codex" in names
    assert "mcp_tool_stub" in names

    result = await registry.execute("write_file", {"path": str(tmp_path / "note.txt"), "content": "hello"})
    assert result.success is True
    read_result = await registry.execute("read_file", {"path": str(tmp_path / "note.txt")})
    assert read_result.content == "hello"

    schema = registry.get("create_object").openai_schema()
    assert schema["function"]["name"] == "create_object"
