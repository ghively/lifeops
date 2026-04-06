import pytest

from app.database.sqlite import sqlite_manager
from app.services.agent.models import AgentMessage
from app.services.agent.session import SessionManager


@pytest.fixture
async def initialized_sqlite(tmp_path):
    original_db_path = sqlite_manager.db_path
    original_connection = sqlite_manager.connection
    sqlite_manager.db_path = str(tmp_path / "test_agent_session.db")
    sqlite_manager.connection = None
    await sqlite_manager.initialize()
    try:
        yield
    finally:
        await sqlite_manager.close()
        sqlite_manager.connection = original_connection
        sqlite_manager.db_path = original_db_path


@pytest.mark.asyncio
async def test_session_manager_persists_message_name_and_metadata(initialized_sqlite):
    manager = SessionManager()
    session = await manager.create_session("agent-a")

    await manager.add_message(
        session.id,
        AgentMessage(role="tool", name="read_file", content="done", metadata={"tool_call_id": "call-1"}),
    )

    history = await manager.load_history(session.id)

    assert history[0].name == "read_file"
    assert history[0].metadata == {"tool_call_id": "call-1"}
