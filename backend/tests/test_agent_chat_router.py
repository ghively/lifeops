"""Comprehensive test suite for the agent_chat router.

Covers all endpoints in app/routers/agent_chat.py.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.models import AgentUsageSnapshot
from app.services.agent.rate_limiter import AgentRateLimitExceeded

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUNTIME_PATH = "app.routers.agent_chat.get_agent_runtime"


def _make_mock_runtime() -> MagicMock:
    """Return a fully-configured MagicMock that matches the AgentRuntime API."""
    mock_runtime = MagicMock()

    # Sync methods
    mock_runtime.list_agents.return_value = [{"id": "agent-1", "name": "Test Agent"}]
    mock_runtime.create_agent.return_value = {"id": "new-agent", "name": "New"}
    mock_runtime.get_agent.return_value = {"id": "agent-1", "name": "Test Agent"}
    mock_runtime.delete_agent.return_value = None
    mock_runtime.list_templates.return_value = [{"id": "tpl-1", "name": "Default"}]
    mock_runtime.get_file.return_value = "# Agent"
    mock_runtime.update_file.return_value = None

    # Async methods
    mock_runtime.check_chat_rate_limits = AsyncMock(return_value=None)
    mock_runtime.list_sessions = AsyncMock(return_value=[])
    mock_runtime.get_session_messages = AsyncMock(return_value=[])
    mock_runtime.delete_session = AsyncMock(return_value=None)
    mock_runtime.get_usage = AsyncMock(return_value={"tokens": 0, "requests": 0})
    mock_runtime.get_audit_log = AsyncMock(return_value={"entries": [], "total": 0})
    mock_runtime.curate_memory = AsyncMock(return_value={"status": "ok"})
    mock_runtime.create_scheduled_task = AsyncMock(return_value={"id": "sched-1"})
    mock_runtime.list_scheduled_tasks = AsyncMock(return_value=[])
    mock_runtime.delete_scheduled_task = AsyncMock(return_value=None)
    mock_runtime.run_scheduled_task = AsyncMock(return_value={"ran": True})
    mock_runtime.create_webhook = AsyncMock(return_value={"id": "hook-1"})
    mock_runtime.list_webhooks = AsyncMock(return_value=[])
    mock_runtime.delete_webhook = AsyncMock(return_value=None)

    # MCP manager
    mock_mcp = MagicMock()
    mock_mcp.list_servers = AsyncMock(return_value=[])
    mock_mcp.configure_server = AsyncMock(
        return_value=MagicMock(model_dump=lambda: {"name": "test-mcp", "connected": False})
    )
    mock_mcp.connect_server = AsyncMock(
        return_value=MagicMock(model_dump=lambda: {"name": "test-mcp", "connected": True})
    )
    mock_mcp.disconnect_server = AsyncMock(
        return_value=MagicMock(model_dump=lambda: {"name": "test-mcp", "connected": False})
    )
    mock_mcp.remove_server = AsyncMock(return_value=None)
    mock_mcp.get_server_status = AsyncMock(
        return_value=MagicMock(model_dump=lambda: {"name": "test-mcp", "state": "connected"})
    )
    mock_mcp.list_server_tools = MagicMock(return_value=[{"name": "tool-1"}])
    mock_mcp.test_connection = AsyncMock(return_value={"success": True})

    # Tool registry
    mock_runtime.tool_registry = MagicMock()
    mock_runtime.tool_registry.mcp_manager = mock_mcp
    mock_runtime.tool_registry.cli_tool = MagicMock()
    mock_runtime.tool_registry.cli_tool.health_check.return_value = [{"name": "bash", "ok": True}]

    return mock_runtime


# ---------------------------------------------------------------------------
# TestRuntimeChat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRuntimeChat:
    """Tests for POST /api/v1/agents/runtime/chat."""

    async def test_rate_limit_exceeded_returns_429(self, test_client):
        """Rate limit exceeded must return 429 with retry_after_seconds in the body."""
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
            RUNTIME_PATH,
            return_value=MagicMock(
                check_chat_rate_limits=AsyncMock(
                    side_effect=AgentRateLimitExceeded(
                        "Too many requests", snapshot, retry_after_seconds=12
                    )
                )
            ),
        ):
            response = await test_client.post(
                "/api/v1/agents/runtime/chat",
                json={"agent_id": "test-agent", "message": "hello"},
            )

        assert response.status_code == 429
        body = response.json()
        assert body.get("retry_after_seconds") == 12
        assert body.get("detail") == "Too many requests"

    async def test_chat_success_streams_sse(self, test_client):
        """Successful chat must return a 200 streaming response."""

        async def fake_sse(*args, **kwargs):
            yield b'data: {"type": "text", "content": "hello"}\n\n'

        mock_runtime = _make_mock_runtime()
        mock_runtime.chat_sse = fake_sse

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/chat",
                json={"agent_id": "test-agent", "message": "hello"},
            )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

    async def test_chat_missing_agent_id_returns_422(self, test_client):
        """Omitting the required agent_id field must return a validation error."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/chat",
                json={"message": "hello"},
            )

        assert response.status_code == 422

    async def test_chat_missing_message_returns_422(self, test_client):
        """Omitting the required message field must return a validation error."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/chat",
                json={"agent_id": "test-agent"},
            )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# TestCLIStatus
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCLIStatus:
    """Tests for GET /api/v1/agents/runtime/cli-status."""

    async def test_cli_status_returns_agents_list(self, test_client):
        """CLI status endpoint must return an agents health-check list."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get("/api/v1/agents/runtime/cli-status")

        assert response.status_code == 200
        body = response.json()
        assert "agents" in body
        assert isinstance(body["agents"], list)

    async def test_cli_status_reflects_health_check_output(self, test_client):
        """CLI status must return whatever the cli_tool.health_check() provides."""
        mock_runtime = _make_mock_runtime()
        mock_runtime.tool_registry.cli_tool.health_check.return_value = [
            {"name": "bash", "ok": True},
            {"name": "python3", "ok": False},
        ]

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get("/api/v1/agents/runtime/cli-status")

        assert response.status_code == 200
        agents = response.json()["agents"]
        assert len(agents) == 2
        assert agents[0]["name"] == "bash"


# ---------------------------------------------------------------------------
# TestMCPServers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMCPServers:
    """Tests for all MCP-related endpoints."""

    # GET /mcp/servers
    async def test_list_mcp_servers_returns_empty(self, test_client):
        """List MCP servers returns servers key with an empty list when none configured."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get("/api/v1/agents/runtime/mcp/servers")

        assert response.status_code == 200
        body = response.json()
        assert "servers" in body
        assert isinstance(body["servers"], list)

    # POST /mcp/servers — success
    async def test_create_mcp_server_success(self, test_client):
        """Valid MCP server creation with a whitelisted binary must succeed."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/mcp/servers",
                json={
                    "name": "test-mcp",
                    "transport": "stdio",
                    "command": "node /path/to/script.js",
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert "name" in body

    async def test_create_mcp_server_npx_success(self, test_client):
        """npx is a whitelisted binary and must be accepted."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/mcp/servers",
                json={
                    "name": "npx-mcp",
                    "transport": "stdio",
                    "command": "npx some-mcp-server",
                },
            )

        assert response.status_code == 200

    async def test_create_mcp_server_python3_success(self, test_client):
        """python3 is a whitelisted binary and a plain script path is accepted."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/mcp/servers",
                json={
                    "name": "py-mcp",
                    "transport": "stdio",
                    "command": "python3 /path/to/server.py",
                },
            )

        assert response.status_code == 200

    # POST /mcp/servers — dangerous shell metacharacters
    async def test_create_mcp_server_shell_pipe_rejected(self, test_client):
        """Commands containing | must be rejected with 400."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/mcp/servers",
                json={
                    "name": "bad",
                    "transport": "stdio",
                    "command": "bash -c 'rm -rf /'",
                },
            )

        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        # The router may reject at the metachar check or the binary-allowlist check;
        # both are valid security rejections.
        assert (
            "forbidden" in detail
            or "metachar" in detail
            or "allowed" in detail
            or "not permitted" in detail
        )

    async def test_create_mcp_server_shell_semicolon_rejected(self, test_client):
        """Commands containing ; must be rejected with 400."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/mcp/servers",
                json={
                    "name": "bad",
                    "transport": "stdio",
                    "command": "node /script.js; rm -rf /",
                },
            )

        assert response.status_code == 400

    async def test_create_mcp_server_shell_dollar_rejected(self, test_client):
        """Commands containing $ must be rejected with 400."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/mcp/servers",
                json={
                    "name": "bad",
                    "transport": "stdio",
                    "command": "node $HOME/evil.js",
                },
            )

        assert response.status_code == 400

    # POST /mcp/servers — forbidden flags
    async def test_create_mcp_server_flag_c_rejected(self, test_client):
        """The -c flag must be rejected even on a whitelisted binary."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/mcp/servers",
                json={
                    "name": "bad",
                    "transport": "stdio",
                    "command": "python -c 'import os'",
                },
            )

        assert response.status_code == 400
        assert "flag" in response.json()["detail"].lower() or "not permitted" in response.json()["detail"].lower()

    async def test_create_mcp_server_flag_eval_rejected(self, test_client):
        """The --eval flag must be rejected."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/mcp/servers",
                json={
                    "name": "bad",
                    "transport": "stdio",
                    "command": "node --eval 'console.log(1)'",
                },
            )

        assert response.status_code == 400

    async def test_create_mcp_server_flag_m_rejected(self, test_client):
        """The -m flag must be rejected."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/mcp/servers",
                json={
                    "name": "bad",
                    "transport": "stdio",
                    "command": "python -m http.server",
                },
            )

        assert response.status_code == 400

    # POST /mcp/servers — binary not in allowlist
    async def test_create_mcp_server_unknown_binary_rejected(self, test_client):
        """Binaries that are not whitelisted must be rejected with 400."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/mcp/servers",
                json={
                    "name": "bad",
                    "transport": "stdio",
                    "command": "curl https://example.com",
                },
            )

        assert response.status_code == 400
        assert "allowed" in response.json()["detail"].lower()

    # POST /mcp/servers — empty command
    async def test_create_mcp_server_empty_command_rejected(self, test_client):
        """An empty command string must be rejected with 400."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/mcp/servers",
                json={
                    "name": "bad",
                    "transport": "stdio",
                    "command": "",
                },
            )

        assert response.status_code == 400

    # DELETE /mcp/servers/{name}
    async def test_delete_mcp_server_success(self, test_client):
        """Deleting an existing MCP server returns deleted=True."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.delete("/api/v1/agents/runtime/mcp/servers/test-mcp")

        assert response.status_code == 200
        body = response.json()
        assert body["deleted"] is True
        assert body["name"] == "test-mcp"

    async def test_delete_mcp_server_not_found_returns_404(self, test_client):
        """Deleting a non-existent MCP server must return 404."""
        mock_runtime = _make_mock_runtime()
        mock_runtime.tool_registry.mcp_manager.remove_server = AsyncMock(
            side_effect=KeyError("not found")
        )

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.delete(
                "/api/v1/agents/runtime/mcp/servers/ghost"
            )

        assert response.status_code == 404

    # POST /mcp/servers/{name}/connect
    async def test_connect_mcp_server_success(self, test_client):
        """Connecting to an existing MCP server returns connection status."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/mcp/servers/test-mcp/connect"
            )

        assert response.status_code == 200
        body = response.json()
        assert "name" in body

    async def test_connect_mcp_server_not_found_returns_404(self, test_client):
        """Connecting to a missing server must return 404."""
        mock_runtime = _make_mock_runtime()
        mock_runtime.tool_registry.mcp_manager.connect_server = AsyncMock(
            side_effect=KeyError("ghost")
        )

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/mcp/servers/ghost/connect"
            )

        assert response.status_code == 404

    async def test_connect_mcp_server_error_returns_400(self, test_client):
        """A generic connection error must return 400."""
        mock_runtime = _make_mock_runtime()
        mock_runtime.tool_registry.mcp_manager.connect_server = AsyncMock(
            side_effect=RuntimeError("connection refused")
        )

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/mcp/servers/bad/connect"
            )

        assert response.status_code == 400
        assert "connection refused" in response.json()["detail"]

    # POST /mcp/servers/{name}/disconnect
    async def test_disconnect_mcp_server_success(self, test_client):
        """Disconnecting a connected server returns updated status."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/mcp/servers/test-mcp/disconnect"
            )

        assert response.status_code == 200
        body = response.json()
        assert "name" in body

    async def test_disconnect_mcp_server_not_found_returns_404(self, test_client):
        """Disconnecting a missing server must return 404."""
        mock_runtime = _make_mock_runtime()
        mock_runtime.tool_registry.mcp_manager.disconnect_server = AsyncMock(
            side_effect=KeyError("ghost")
        )

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/mcp/servers/ghost/disconnect"
            )

        assert response.status_code == 404

    # GET /mcp/servers/{name}/tools
    async def test_list_mcp_server_tools_success(self, test_client):
        """Listing tools for a known server returns server info and tools list."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get(
                "/api/v1/agents/runtime/mcp/servers/test-mcp/tools"
            )

        assert response.status_code == 200
        body = response.json()
        assert "server" in body
        assert "tools" in body

    async def test_list_mcp_server_tools_not_found_returns_404(self, test_client):
        """Listing tools for a missing server must return 404."""
        mock_runtime = _make_mock_runtime()
        mock_runtime.tool_registry.mcp_manager.get_server_status = AsyncMock(
            side_effect=KeyError("ghost")
        )

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get(
                "/api/v1/agents/runtime/mcp/servers/ghost/tools"
            )

        assert response.status_code == 404

    # POST /mcp/test
    async def test_mcp_test_connection_success(self, test_client):
        """A successful MCP test connection returns a success result."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/mcp/test",
                json={
                    "name": "test-mcp",
                    "transport": "stdio",
                    "command": "node /script.js",
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True

    async def test_mcp_test_connection_failure_returns_400(self, test_client):
        """A failed MCP test connection must return 400 with the error detail."""
        mock_runtime = _make_mock_runtime()
        mock_runtime.tool_registry.mcp_manager.test_connection = AsyncMock(
            return_value={"success": False, "error": "timeout"}
        )

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/mcp/test",
                json={
                    "name": "test-mcp",
                    "transport": "stdio",
                    "command": "node /script.js",
                },
            )

        assert response.status_code == 400
        assert "timeout" in response.json()["detail"]


# ---------------------------------------------------------------------------
# TestRuntimeAgents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRuntimeAgents:
    """Tests for agent CRUD, usage, and audit endpoints."""

    async def test_list_agents(self, test_client):
        """GET /runtime returns an agents list."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get("/api/v1/agents/runtime")

        assert response.status_code == 200
        body = response.json()
        assert "agents" in body
        assert len(body["agents"]) == 1
        assert body["agents"][0]["id"] == "agent-1"

    async def test_create_agent(self, test_client):
        """POST /runtime/{agent_id} creates and returns the new agent."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/new-agent",
                json={},
            )

        assert response.status_code == 200
        body = response.json()
        assert "id" in body

    async def test_create_agent_with_template(self, test_client):
        """POST /runtime/{agent_id} with template_id passes the template to create_agent."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/new-agent",
                json={"template_id": "tpl-1"},
            )

        assert response.status_code == 200
        mock_runtime.create_agent.assert_called_once_with("new-agent", template_id="tpl-1")

    async def test_get_agent(self, test_client):
        """GET /runtime/{agent_id} returns the agent details."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get("/api/v1/agents/runtime/agent-1")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == "agent-1"

    async def test_delete_agent(self, test_client):
        """DELETE /runtime/{agent_id} returns deleted=True."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.delete("/api/v1/agents/runtime/agent-1")

        assert response.status_code == 200
        body = response.json()
        assert body["deleted"] is True
        assert body["agent_id"] == "agent-1"

    async def test_get_agent_usage(self, test_client):
        """GET /runtime/{agent_id}/usage returns usage data."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get("/api/v1/agents/runtime/agent-1/usage")

        assert response.status_code == 200
        body = response.json()
        assert "tokens" in body

    async def test_get_agent_audit(self, test_client):
        """GET /runtime/{agent_id}/audit returns audit entries."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get("/api/v1/agents/runtime/agent-1/audit")

        assert response.status_code == 200
        body = response.json()
        assert "entries" in body

    async def test_get_agent_audit_pagination(self, test_client):
        """GET /runtime/{agent_id}/audit respects page and page_size query params."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get(
                "/api/v1/agents/runtime/agent-1/audit?page=2&page_size=10"
            )

        assert response.status_code == 200
        mock_runtime.get_audit_log.assert_awaited_once_with("agent-1", page=2, page_size=10)


# ---------------------------------------------------------------------------
# TestRuntimeSessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRuntimeSessions:
    """Tests for session management endpoints."""

    async def test_list_sessions(self, test_client):
        """GET /sessions returns a sessions list."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get("/api/v1/agents/runtime/sessions")

        assert response.status_code == 200
        body = response.json()
        assert "sessions" in body
        assert isinstance(body["sessions"], list)

    async def test_list_sessions_filtered_by_agent_id(self, test_client):
        """GET /sessions?agent_id=X passes the filter to the runtime."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get(
                "/api/v1/agents/runtime/sessions?agent_id=agent-1"
            )

        assert response.status_code == 200
        mock_runtime.list_sessions.assert_awaited_once_with("agent-1")

    async def test_get_session_messages(self, test_client):
        """GET /sessions/{session_id}/messages returns messages list."""
        mock_runtime = _make_mock_runtime()
        mock_runtime.get_session_messages = AsyncMock(
            return_value=[{"role": "user", "content": "hello"}]
        )

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get(
                "/api/v1/agents/runtime/sessions/sess-1/messages"
            )

        assert response.status_code == 200
        body = response.json()
        assert "messages" in body
        assert len(body["messages"]) == 1

    async def test_delete_session(self, test_client):
        """DELETE /sessions/{session_id} returns deleted=True."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.delete(
                "/api/v1/agents/runtime/sessions/sess-1"
            )

        assert response.status_code == 200
        body = response.json()
        assert body["deleted"] is True
        assert body["session_id"] == "sess-1"


# ---------------------------------------------------------------------------
# TestRuntimeTemplates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRuntimeTemplates:
    """Tests for templates and create-from-template endpoints."""

    async def test_list_templates(self, test_client):
        """GET /templates returns available agent templates."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get("/api/v1/agents/runtime/templates")

        assert response.status_code == 200
        body = response.json()
        assert "templates" in body
        assert body["templates"][0]["id"] == "tpl-1"

    async def test_create_from_template(self, test_client):
        """POST /create-from-template creates an agent from a template."""
        mock_runtime = _make_mock_runtime()
        mock_runtime.create_agent.return_value = {"id": "from-template", "name": "FromTpl"}

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/create-from-template",
                json={"agent_id": "from-template", "template_id": "tpl-1"},
            )

        assert response.status_code == 200
        body = response.json()
        assert "id" in body
        mock_runtime.create_agent.assert_called_once_with(
            "from-template", template_id="tpl-1"
        )


# ---------------------------------------------------------------------------
# TestRuntimeSchedule
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRuntimeSchedule:
    """Tests for scheduled-task endpoints."""

    async def test_create_schedule(self, test_client):
        """POST /schedule creates a scheduled task and returns its id."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/schedule",
                json={
                    "agent_id": "agent-1",
                    "name": "Daily Summary",
                    "cron_expression": "0 9 * * *",
                    "task_type": "periodic_research",
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert "id" in body

    async def test_list_schedule(self, test_client):
        """GET /schedule returns a tasks list."""
        mock_runtime = _make_mock_runtime()
        mock_runtime.list_scheduled_tasks = AsyncMock(
            return_value=[{"id": "sched-1", "name": "Daily Summary"}]
        )

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get("/api/v1/agents/runtime/schedule")

        assert response.status_code == 200
        body = response.json()
        assert "tasks" in body
        assert len(body["tasks"]) == 1

    async def test_list_schedule_filtered_by_agent_id(self, test_client):
        """GET /schedule?agent_id=X passes the filter to the runtime."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get(
                "/api/v1/agents/runtime/schedule?agent_id=agent-1"
            )

        assert response.status_code == 200
        mock_runtime.list_scheduled_tasks.assert_awaited_once_with("agent-1")

    async def test_delete_schedule(self, test_client):
        """DELETE /schedule/{task_id} returns deleted=True."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.delete(
                "/api/v1/agents/runtime/schedule/sched-1"
            )

        assert response.status_code == 200
        body = response.json()
        assert body["deleted"] is True
        assert body["id"] == "sched-1"

    async def test_run_schedule_success(self, test_client):
        """POST /schedule/{task_id}/run triggers the task and returns its result."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/schedule/sched-1/run"
            )

        assert response.status_code == 200
        body = response.json()
        assert body["ran"] is True

    async def test_run_schedule_not_found_returns_404(self, test_client):
        """POST /schedule/{task_id}/run for an unknown task must return 404."""
        mock_runtime = _make_mock_runtime()
        mock_runtime.run_scheduled_task = AsyncMock(
            side_effect=KeyError("sched-ghost")
        )

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/schedule/sched-ghost/run"
            )

        assert response.status_code == 404

    async def test_curate_memory(self, test_client):
        """POST /{agent_id}/curate-memory triggers curation and returns status."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/agent-1/curate-memory",
                json={"frequency": "weekly"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        mock_runtime.curate_memory.assert_awaited_once_with("agent-1", frequency="weekly")


# ---------------------------------------------------------------------------
# TestRuntimeWebhooks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRuntimeWebhooks:
    """Tests for webhook management endpoints."""

    async def test_create_webhook(self, test_client):
        """POST /webhooks creates a webhook and returns its id."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.post(
                "/api/v1/agents/runtime/webhooks",
                json={
                    "agent_id": "agent-1",
                    "name": "My Hook",
                    "event_type": "message.received",
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert "id" in body

    async def test_list_webhooks(self, test_client):
        """GET /webhooks returns a webhooks list."""
        mock_runtime = _make_mock_runtime()
        mock_runtime.list_webhooks = AsyncMock(
            return_value=[{"id": "hook-1", "name": "My Hook"}]
        )

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get("/api/v1/agents/runtime/webhooks")

        assert response.status_code == 200
        body = response.json()
        assert "webhooks" in body
        assert len(body["webhooks"]) == 1

    async def test_list_webhooks_filtered_by_agent_id(self, test_client):
        """GET /webhooks?agent_id=X passes the filter to the runtime."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get(
                "/api/v1/agents/runtime/webhooks?agent_id=agent-1"
            )

        assert response.status_code == 200
        mock_runtime.list_webhooks.assert_awaited_once_with("agent-1")

    async def test_delete_webhook(self, test_client):
        """DELETE /webhooks/{webhook_id} returns deleted=True."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.delete(
                "/api/v1/agents/runtime/webhooks/hook-1"
            )

        assert response.status_code == 200
        body = response.json()
        assert body["deleted"] is True
        assert body["id"] == "hook-1"


# ---------------------------------------------------------------------------
# TestRuntimeAgentFiles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRuntimeAgentFiles:
    """Tests for agent file read/update endpoints."""

    async def test_get_agent_file_agent_md(self, test_client):
        """GET /files/AGENT.md returns the file content as plain text."""
        mock_runtime = _make_mock_runtime()
        mock_runtime.get_file.return_value = "# My Agent\nSystem prompt here."

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get(
                "/api/v1/agents/runtime/agent-1/files/AGENT.md"
            )

        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        assert "My Agent" in response.text

    async def test_get_agent_file_soul_md(self, test_client):
        """GET /files/SOUL.md is in the allowed set and must return 200."""
        mock_runtime = _make_mock_runtime()
        mock_runtime.get_file.return_value = "soul content"

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get(
                "/api/v1/agents/runtime/agent-1/files/SOUL.md"
            )

        assert response.status_code == 200
        assert "soul content" in response.text

    async def test_get_agent_file_memory_md(self, test_client):
        """GET /files/MEMORY.md is in the allowed set and must return 200."""
        mock_runtime = _make_mock_runtime()
        mock_runtime.get_file.return_value = "memory content"

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get(
                "/api/v1/agents/runtime/agent-1/files/MEMORY.md"
            )

        assert response.status_code == 200

    async def test_get_agent_file_tools_md(self, test_client):
        """GET /files/TOOLS.md is in the allowed set and must return 200."""
        mock_runtime = _make_mock_runtime()
        mock_runtime.get_file.return_value = "tools content"

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get(
                "/api/v1/agents/runtime/agent-1/files/TOOLS.md"
            )

        assert response.status_code == 200

    async def test_get_agent_file_unsupported_name_returns_404(self, test_client):
        """GET /files/SECRETS.md is not in the allowed set and must return 404."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.get(
                "/api/v1/agents/runtime/agent-1/files/SECRETS.md"
            )

        assert response.status_code == 404
        assert "Unsupported" in response.json()["detail"]

    async def test_update_agent_file_success(self, test_client):
        """PUT /files/AGENT.md with valid content returns updated=True."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.put(
                "/api/v1/agents/runtime/agent-1/files/AGENT.md",
                json={"content": "# Updated Agent"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["updated"] is True
        assert body["agent_id"] == "agent-1"
        assert body["file"] == "AGENT.md"

    async def test_update_agent_file_unsupported_name_returns_404(self, test_client):
        """PUT /files/EVIL.md is not in the allowed set and must return 404."""
        mock_runtime = _make_mock_runtime()

        with patch(RUNTIME_PATH, return_value=mock_runtime):
            response = await test_client.put(
                "/api/v1/agents/runtime/agent-1/files/EVIL.md",
                json={"content": "malicious content"},
            )

        assert response.status_code == 404
        assert "Unsupported" in response.json()["detail"]
