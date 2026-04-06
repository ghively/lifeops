from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.models import AgentUsageSnapshot
from app.services.agent.rate_limiter import AgentRateLimitExceeded


@pytest.mark.asyncio
async def test_runtime_chat_returns_rate_limit_payload(test_client):
    """Test that rate limit exceeded returns 429 with retry_after_seconds in body."""
    snapshot = AgentUsageSnapshot(
        agent_id="test-agent",
        user_id="test-user-id",
        minute_requests=30,
        minute_limit=30,
        daily_tokens=100,
        daily_token_limit=1000,
        daily_requests=5,
        retry_after_seconds=12,
        date="2026-04-05",
    )

    with patch(
        "app.routers.agent_chat.agent_runtime.check_chat_rate_limits",
        new_callable=AsyncMock,
        side_effect=AgentRateLimitExceeded("Too many requests", snapshot, retry_after_seconds=12),
    ):
        response = await test_client.post(
            "/api/v1/agents/runtime/chat",
            json={"agent_id": "test-agent", "message": "hello"},
        )

    assert response.status_code == 429
    body = response.json()
    assert body.get("retry_after_seconds") == 12
    assert body.get("detail") == "Too many requests"
