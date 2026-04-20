import pytest

from app.database.sqlite import sqlite_manager
from app.services.agent.audit import AgentAuditLogger


@pytest.fixture
async def initialized_sqlite(tmp_path):
    original_db_path = sqlite_manager.db_path
    original_connection = sqlite_manager.connection
    sqlite_manager.db_path = str(tmp_path / "test_audit.db")
    sqlite_manager.connection = None
    await sqlite_manager.initialize()
    try:
        yield
    finally:
        await sqlite_manager.close()
        sqlite_manager.connection = original_connection
        sqlite_manager.db_path = original_db_path


@pytest.mark.asyncio
async def test_audit_logger_creates_and_queries_events(initialized_sqlite):
    logger = AgentAuditLogger(retention_days=90)
    await logger.log_event(
        agent_id="agent-a",
        session_id="session-1",
        user_id="user-1",
        event_type="tool.call",
        details={"tool_name": "write_file"},
    )
    await logger.log_event(
        agent_id="agent-a", session_id="session-1", user_id="user-1", event_type="tool.result", details={"success": True}
    )

    payload = await logger.list_events("agent-a", page=1, page_size=10)
    assert payload["total"] == 2
    assert payload["items"][0]["event_type"] in {"tool.call", "tool.result"}


@pytest.mark.asyncio
async def test_audit_logger_retention_purge(initialized_sqlite):
    logger = AgentAuditLogger(retention_days=0)
    await logger.log_event(agent_id="agent-a", session_id="session-1", user_id="user-1", event_type="tool.call", details={})
    await logger.purge_expired()
    payload = await logger.list_events("agent-a", page=1, page_size=10)
    assert payload["total"] == 0
