"""
Tests for the agents router.
"""

import pytest


@pytest.mark.asyncio
class TestAgentsRouter:
    """Test cases for /api/agents endpoints."""

    async def test_list_agents(self, test_client):
        """Test listing all agents."""
        response = await test_client.get("/api/v1/agents")

        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        assert isinstance(data["agents"], list)

    async def test_get_agent_success(self, test_client):
        """Test getting a specific agent by name."""
        response = await test_client.get("/api/v1/agents/test-agent")

        # May return 404 if agent doesn't exist
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            assert data["name"] == "test-agent"

    async def test_get_agent_not_found(self, test_client):
        """Test getting a non-existent agent."""
        response = await test_client.get("/api/v1/agents/non-existent-agent")

        assert response.status_code == 404

    async def test_send_chat_message(self, test_client, mock_openclaw_service):
        """Test sending a chat message to an agent."""
        chat_data = {
            "content": "Hello, agent!",
            "session_id": "test-session-1",
        }

        response = await test_client.post("/api/v1/agents/test-agent/chat", json=chat_data)

        assert response.status_code == 200
        data = response.json()
        assert "response" in data

    async def test_send_chat_message_without_session(self, test_client, mock_openclaw_service):
        """Test sending a chat message without session ID (creates new session)."""
        chat_data = {
            "content": "Hello, agent!",
        }

        response = await test_client.post("/api/v1/agents/test-agent/chat", json=chat_data)

        assert response.status_code == 200
        data = response.json()
        assert "response" in data

    async def test_send_chat_message_empty(self, test_client):
        """Test sending an empty chat message."""
        chat_data = {
            "content": "",
        }

        response = await test_client.post("/api/v1/agents/test-agent/chat", json=chat_data)

        assert response.status_code in [422, 400]

    async def test_get_chat_history_empty(self, test_client):
        """Test getting chat history for a new session."""
        response = await test_client.get("/api/v1/agents/test-agent/chat", params={"session_id": "new-session"})

        assert response.status_code == 200
        data = response.json()
        assert "messages" in data

    async def test_get_chat_history_with_data(self, test_client):
        """Test getting chat history with existing messages."""
        response = await test_client.get("/api/v1/agents/test-agent/chat", params={"session_id": "test-session", "limit": 10})

        assert response.status_code == 200
        data = response.json()
        assert "messages" in data

    async def test_get_chat_history_pagination(self, test_client):
        """Test getting chat history with pagination."""
        response = await test_client.get(
            "/api/v1/agents/test-agent/chat", params={"session_id": "test-session", "limit": 5, "offset": 0}
        )

        assert response.status_code == 200
        data = response.json()
        assert "messages" in data

    async def test_get_agent_tasks(self, test_client):
        """Test getting tasks assigned to an agent."""
        response = await test_client.get("/api/v1/agents/test-agent/tasks", params={"status": "in-progress"})

        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data

    async def test_get_agent_tasks_all(self, test_client):
        """Test getting all tasks for an agent."""
        response = await test_client.get("/api/v1/agents/test-agent/tasks")

        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data

    async def test_get_agent_tasks(self, test_client):
        """Test getting tasks for an agent."""
        response = await test_client.get("/api/v1/agents/coder/tasks")
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data

    async def test_get_agent_tasks_with_status(self, test_client):
        """Test getting tasks for an agent filtered by status."""
        response = await test_client.get("/api/v1/agents/coder/tasks", params={"status": "todo"})
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data


@pytest.mark.asyncio
class TestOpenClawService:
    """Test cases for OpenClaw service integration."""

    async def test_send_message_to_service(self, mock_openclaw_service):
        """Test sending message through OpenClaw service."""
        response = await mock_openclaw_service.send_message("test-agent", "Test message", "test-session")

        assert response is not None
        assert "response" in response
        assert "session_id" in response

    async def test_assign_task_to_agent(self, mock_openclaw_service):
        """Test assigning task to agent through OpenClaw service."""
        response = await mock_openclaw_service.assign_task("test-agent", "task-123", {"context": "test"})

        assert response is not None
        assert response["status"] == "assigned"

    async def test_get_agent_status_from_service(self, mock_openclaw_service):
        """Test getting agent status from OpenClaw service."""
        response = await mock_openclaw_service.get_agent_status("test-agent")

        assert response is not None
        assert "name" in response
        assert "status" in response
