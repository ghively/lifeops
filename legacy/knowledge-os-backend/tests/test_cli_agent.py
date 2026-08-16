import sys

import pytest

from app.services.agent.cli_agent import CLIAgentTool
from app.services.agent.models import CLIAgentConfig


@pytest.mark.asyncio
async def test_cli_agent_executes_async_subprocess(monkeypatch, tmp_path):
    cli = CLIAgentTool()
    monkeypatch.setitem(
        cli.AGENTS,
        "test_cli",
        CLIAgentConfig(
            name="test_cli",
            command=sys.executable,
            args=["-c", "import sys; print(sys.argv[-1])"],
            install_check=sys.executable,
            timeout=5,
            description="test cli",
        ),
    )
    monkeypatch.setattr(cli, "is_installed", lambda agent_name: True)

    result = await cli.execute("test_cli", "hello world", cwd=str(tmp_path))
    assert result.success is True
    assert "hello world" in result.content
