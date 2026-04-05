import pytest

from app.database.sqlite import sqlite_manager
from app.services.agent.models import AgentIdentity
from app.services.agent.rate_limiter import AgentRateLimiter


@pytest.fixture
async def initialized_sqlite(tmp_path):
    original_db_path = sqlite_manager.db_path
    original_connection = sqlite_manager.connection
    sqlite_manager.db_path = str(tmp_path / "test_rate_limiter.db")
    sqlite_manager.connection = None
    await sqlite_manager.initialize()
    try:
        yield
    finally:
        await sqlite_manager.close()
        sqlite_manager.connection = original_connection
        sqlite_manager.db_path = original_db_path


@pytest.mark.asyncio
async def test_rate_limiter_tracks_requests_and_tokens(initialized_sqlite):
    limiter = AgentRateLimiter()
    identity = AgentIdentity(agent_id="agent-a", name="Agent A", system_prompt="You are A.", rate_limits={"requests_per_minute": 2, "tokens_per_day": 100})

    first = await limiter.check_request_limit(agent_id="agent-a", user_id="user-1", identity=identity)
    assert first.minute_requests == 1

    await limiter.record_usage(agent_id="agent-a", user_id="user-1", tokens=30)
    usage = await limiter.get_usage(agent_id="agent-a", user_id="user-1", identity=identity)
    assert usage["current"]["daily_tokens"] == 30
    assert usage["current"]["daily_requests"] == 1


@pytest.mark.asyncio
async def test_rate_limiter_rejects_excess_requests(initialized_sqlite):
    limiter = AgentRateLimiter()
    identity = AgentIdentity(agent_id="agent-a", name="Agent A", system_prompt="You are A.", rate_limits={"requests_per_minute": 1})

    await limiter.check_request_limit(agent_id="agent-a", user_id="user-1", identity=identity)
    with pytest.raises(Exception) as exc:
        await limiter.check_request_limit(agent_id="agent-a", user_id="user-1", identity=identity)

    assert getattr(exc.value, "status_code", None) == 429


@pytest.mark.asyncio
async def test_rate_limiter_enforces_daily_token_budget(initialized_sqlite):
    limiter = AgentRateLimiter()
    identity = AgentIdentity(agent_id="agent-a", name="Agent A", system_prompt="You are A.", rate_limits={"tokens_per_day": 50})

    await limiter.record_usage(agent_id="agent-a", user_id="user-1", tokens=40)
    with pytest.raises(Exception) as exc:
        await limiter.enforce_daily_token_limit(agent_id="agent-a", user_id="user-1", identity=identity, projected_tokens=20)

    assert getattr(exc.value, "status_code", None) == 429
