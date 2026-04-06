from unittest.mock import AsyncMock

import pytest

from app.services.agent.models import SubAgentTask
from app.services.agent.runtime import AgentRuntime


@pytest.mark.asyncio
async def test_run_sub_agent_task_passes_timeout_to_background_runner(tmp_path):
    runtime = AgentRuntime(tmp_path)
    runtime.run_background_task = AsyncMock(
        return_value={"content": "done", "session_id": "session-1", "tool_results": []}
    )
    task = SubAgentTask(agent_id="worker", prompt="Handle this", timeout_seconds=45)

    result = await runtime.run_sub_agent_task(
        parent_agent_id="parent",
        task=task,
        execution_depth=1,
    )

    assert result.success is True
    runtime.run_background_task.assert_awaited_once()
    assert runtime.run_background_task.await_args.kwargs["timeout_seconds"] == 45
