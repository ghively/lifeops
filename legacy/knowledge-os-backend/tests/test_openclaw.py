"""Tests for the OpenClaw service short-circuit behavior (issue #152)."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_invoke_tool_skips_when_token_missing(caplog):
    """When no token is configured anywhere, the service must not hit the
    gateway — calling it just produces noisy 401 spam in the logs."""
    from app.services.openclaw import OpenClawService

    service = OpenClawService()

    async def runtime(*_args, **_kwargs):
        return {"openclaw_url": "http://localhost:18789", "openclaw_token": "", "openclaw_enabled": True}

    with patch.object(service, "_runtime_settings", runtime), patch(
        "httpx.AsyncClient"
    ) as fake_client:
        with caplog.at_level("WARNING"):
            result = await service._invoke_tool("session_status", args={})
        # No HTTP client should have been constructed for the call.
        fake_client.assert_not_called()

    assert result["status"] == "not_configured"
    # First call should log the warning…
    assert any("token is not configured" in m for m in caplog.messages)

    caplog.clear()
    with patch.object(service, "_runtime_settings", runtime), patch(
        "httpx.AsyncClient"
    ) as fake_client:
        with caplog.at_level("WARNING"):
            result = await service._invoke_tool("session_status", args={})
        fake_client.assert_not_called()

    # …and subsequent calls must stay silent (no log spam).
    assert not any("token is not configured" in m for m in caplog.messages)


@pytest.mark.asyncio
async def test_health_check_reports_not_configured_without_token():
    from app.services.openclaw import OpenClawService

    service = OpenClawService()

    async def runtime(*_args, **_kwargs):
        return {"openclaw_url": "http://localhost:18789", "openclaw_token": "", "openclaw_enabled": True}

    with patch.object(service, "_runtime_settings", runtime):
        result = await service.health_check()

    assert result["status"] == "not_configured"
    assert result["reachable"] is False
    assert "not configured" in result["error"]


@pytest.mark.asyncio
async def test_invoke_tool_skips_when_disabled():
    from app.services.openclaw import OpenClawService

    service = OpenClawService()

    async def runtime(*_args, **_kwargs):
        return {"openclaw_url": "http://localhost:18789", "openclaw_token": "tok", "openclaw_enabled": False}

    with patch.object(service, "_runtime_settings", runtime), patch(
        "httpx.AsyncClient"
    ) as fake_client:
        result = await service._invoke_tool("session_status", args={})
        fake_client.assert_not_called()

    assert result["status"] == "disabled"
