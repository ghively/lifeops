import pytest

import app.services.agent.scheduler as scheduler_module
from app.services.agent.scheduler import AgentScheduler


@pytest.mark.asyncio
async def test_scheduler_crud_and_execution(mock_sqlite_manager):
    scheduler = AgentScheduler()

    class StubRuntime:
        async def run_background_task(self, **kwargs):
            return {"content": "scheduled run", "session_id": "sched-1", "tool_results": []}

    class StubCuration:
        async def curate_agent_memory(self, agent_id, *, frequency="daily"):
            return {"agent_id": agent_id, "frequency": frequency}

    scheduler.bind_runtime(StubRuntime(), StubCuration())

    scheduler_module.sqlite_manager = mock_sqlite_manager

    task = await scheduler.create_task(
        agent_id="researcher",
        name="Daily research",
        cron_expression="every 2 hours",
        task_type="periodic_research",
        config={"prompt": "Check new signals"},
    )
    assert task.id in mock_sqlite_manager._storage["agent_scheduled_tasks"]

    rows = await scheduler.list_tasks("researcher")
    assert len(rows) == 1
    assert rows[0].name == "Daily research"

    result = await scheduler.trigger_task(task.id)
    assert result["result"]["content"] == "scheduled run"
    assert mock_sqlite_manager._storage["agent_scheduled_tasks"][task.id]["last_run"] is not None

    await scheduler.delete_task(task.id)
    assert task.id not in mock_sqlite_manager._storage["agent_scheduled_tasks"]
