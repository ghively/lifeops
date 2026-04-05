"""
Tests for the tasks router.
"""

import pytest


@pytest.mark.asyncio
class TestTasksRouter:
    """Test cases for /api/tasks endpoints."""

    async def test_list_tasks_empty(self, test_client):
        """Test listing tasks when none exist."""
        response = await test_client.get("/api/v1/tasks")
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        assert data["tasks"] == []
        assert "by_status" in data
        assert "by_priority" in data

    async def test_list_tasks_with_data(self, test_client):
        """Test listing tasks with existing data."""
        # Create a task object
        await test_client.post("/api/v1/objects", json={
            "title": "Test Task",
            "content": "Task description",
            "type": "task",
            "properties": {
                "status": "todo",
                "priority": "high",
            },
        })

        response = await test_client.get("/api/v1/tasks")
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        assert len(data["tasks"]) >= 1

    async def test_list_tasks_with_filters(self, test_client):
        """Test listing tasks with status filter."""
        response = await test_client.get("/api/v1/tasks", params={"status": "todo"})
        assert response.status_code == 200

    async def test_create_task_via_objects(self, test_client):
        """Test creating a task by posting to objects with type=task."""
        task_data = {
            "title": "New Task",
            "content": "Task content",
            "type": "task",
            "properties": {
                "status": "todo",
                "priority": "medium",
            },
        }
        response = await test_client.post("/api/v1/objects", json=task_data)
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "task"

    async def test_get_task_success(self, test_client):
        """Test getting a specific task."""
        # Create a task
        create_resp = await test_client.post("/api/v1/objects", json={
            "title": "Task to Get",
            "content": "Task content",
            "type": "task",
            "properties": {"status": "todo", "priority": "low"},
        })
        assert create_resp.status_code == 200
        task_id = create_resp.json()["id"]

        response = await test_client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == task_id

    async def test_get_task_not_found(self, test_client):
        """Test getting a non-existent task."""
        response = await test_client.get("/api/v1/tasks/non-existent")
        assert response.status_code == 404

    async def test_assign_task_success(self, test_client):
        """Test assigning a task to an agent."""
        # Create a task
        create_resp = await test_client.post("/api/v1/objects", json={
            "title": "Assignable Task",
            "content": "Do something",
            "type": "task",
            "properties": {"status": "todo", "priority": "high"},
        })
        assert create_resp.status_code == 200
        task_id = create_resp.json()["id"]

        response = await test_client.post(f"/api/v1/tasks/{task_id}/assign", json={
            "agent_name": "coder",
            "priority": "high",
            "include_context": False,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["agent_name"] == "coder"

    async def test_assign_task_missing_agent(self, test_client):
        """Test assigning a task without agent_name."""
        create_resp = await test_client.post("/api/v1/objects", json={
            "title": "Task", "content": "Do it", "type": "task",
            "properties": {"status": "todo", "priority": "low"},
        })
        task_id = create_resp.json()["id"]

        response = await test_client.post(f"/api/v1/tasks/{task_id}/assign", json={})
        assert response.status_code in [400, 422]

    async def test_assign_task_not_found(self, test_client):
        """Test assigning a non-existent task."""
        response = await test_client.post("/api/v1/tasks/non-existent/assign", json={
            "agent_name": "coder",
        })
        assert response.status_code == 404

    async def test_update_task_status(self, test_client):
        """Test updating task status."""
        create_resp = await test_client.post("/api/v1/objects", json={
            "title": "Status Task", "content": "Change my status", "type": "task",
            "properties": {"status": "todo", "priority": "low"},
        })
        task_id = create_resp.json()["id"]

        response = await test_client.post(f"/api/v1/tasks/{task_id}/status", json={
            "status": "in-progress",
            "agent_name": "coder",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in-progress"

    async def test_update_task_invalid_status(self, test_client):
        """Test updating task with invalid status."""
        create_resp = await test_client.post("/api/v1/objects", json={
            "title": "Bad Status", "content": "test", "type": "task",
            "properties": {"status": "todo", "priority": "low"},
        })
        task_id = create_resp.json()["id"]

        response = await test_client.post(f"/api/v1/tasks/{task_id}/status", json={
            "status": "invalid_status",
        })
        assert response.status_code == 400

    async def test_update_task_status_not_found(self, test_client):
        """Test updating status for non-existent task."""
        response = await test_client.post("/api/v1/tasks/non-existent/status", json={
            "status": "done",
        })
        assert response.status_code == 404

    async def test_get_task_context(self, test_client):
        """Test getting task context."""
        create_resp = await test_client.post("/api/v1/objects", json={
            "title": "Context Task", "content": "Build context", "type": "task",
            "properties": {"status": "todo", "priority": "low"},
        })
        task_id = create_resp.json()["id"]

        response = await test_client.get(f"/api/v1/tasks/{task_id}/context")
        assert response.status_code == 200
        data = response.json()
        assert "context" in data

    async def test_get_task_context_not_found(self, test_client):
        """Test getting context for non-existent task."""
        response = await test_client.get("/api/v1/tasks/non-existent/context")
        assert response.status_code == 200  # Context builder returns empty context


@pytest.mark.asyncio
class TestTaskAssignment:
    """Test cases for task assignment logic."""

    async def test_assign_with_context(self, test_client):
        """Test assigning a task with context included."""
        create_resp = await test_client.post("/api/v1/objects", json={
            "title": "Context Task", "content": "Needs context", "type": "task",
            "properties": {"status": "todo", "priority": "high"},
        })
        task_id = create_resp.json()["id"]

        response = await test_client.post(f"/api/v1/tasks/{task_id}/assign", json={
            "agent_name": "coder",
            "priority": "high",
            "include_context": True,
        })
        assert response.status_code == 200
        data = response.json()
        assert "context" in data

    async def test_assign_low_priority_heartbeat(self, test_client):
        """Test low priority task goes to heartbeat."""
        create_resp = await test_client.post("/api/v1/objects", json={
            "title": "Low Priority", "content": "Background task", "type": "task",
            "properties": {"status": "todo", "priority": "low"},
        })
        task_id = create_resp.json()["id"]

        response = await test_client.post(f"/api/v1/tasks/{task_id}/assign", json={
            "agent_name": "coder",
            "priority": "low",
            "include_context": False,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["assignment_type"] == "heartbeat"


@pytest.mark.asyncio
class TestTaskStatusUpdates:
    """Test cases for task status updates."""

    async def test_complete_task(self, test_client):
        """Test marking a task as done."""
        create_resp = await test_client.post("/api/v1/objects", json={
            "title": "Completable", "content": "Almost done", "type": "task",
            "properties": {"status": "in-progress", "priority": "medium"},
        })
        task_id = create_resp.json()["id"]

        response = await test_client.post(f"/api/v1/tasks/{task_id}/status", json={
            "status": "done",
            "agent_name": "coder",
        })
        assert response.status_code == 200
        assert response.json()["status"] == "done"

    async def test_update_with_current_action(self, test_client):
        """Test updating task with current action."""
        create_resp = await test_client.post("/api/v1/objects", json={
            "title": "Action Task", "content": "Working", "type": "task",
            "properties": {"status": "in-progress", "priority": "medium"},
        })
        task_id = create_resp.json()["id"]

        response = await test_client.post(f"/api/v1/tasks/{task_id}/status", json={
            "status": "in-progress",
            "current_action": "writing tests",
            "agent_name": "coder",
        })
        assert response.status_code == 200

    async def test_valid_statuses(self, test_client):
        """Test all valid status transitions."""
        create_resp = await test_client.post("/api/v1/objects", json={
            "title": "Status Test", "content": "test", "type": "task",
            "properties": {"status": "todo", "priority": "low"},
        })
        task_id = create_resp.json()["id"]

        for status in ["todo", "in-progress", "blocked", "review", "done"]:
            response = await test_client.post(f"/api/v1/tasks/{task_id}/status", json={
                "status": status,
            })
            assert response.status_code == 200, f"Failed for status: {status}"


@pytest.mark.asyncio
class TestTaskCounts:
    """Test cases for task count aggregation."""

    async def test_counts_by_status(self, test_client):
        """Test status count aggregation."""
        # Create tasks with different statuses
        for status in ["todo", "todo", "done"]:
            await test_client.post("/api/v1/objects", json={
                "title": f"Task-{status}",
                "content": f"Task with status {status}",
                "type": "task",
                "properties": {"status": status, "priority": "medium"},
            })

        response = await test_client.get("/api/v1/tasks")
        assert response.status_code == 200
        data = response.json()
        assert data["by_status"]["todo"] >= 2
        assert data["by_status"]["done"] >= 1

    async def test_counts_by_priority(self, test_client):
        """Test priority count aggregation."""
        for priority in ["high", "low", "high"]:
            await test_client.post("/api/v1/objects", json={
                "title": f"Task-{priority}",
                "content": f"Priority task",
                "type": "task",
                "properties": {"status": "todo", "priority": priority},
            })

        response = await test_client.get("/api/v1/tasks")
        assert response.status_code == 200
        data = response.json()
        assert data["by_priority"]["high"] >= 2


@pytest.mark.asyncio
class TestTaskContextBuilder:
    """Test cases for task context building."""

    async def test_build_empty_context(self, test_client):
        """Test building context for a task with no related data."""
        create_resp = await test_client.post("/api/v1/objects", json={
            "title": "Lonely Task", "content": "No relations", "type": "task",
            "properties": {"status": "todo", "priority": "low"},
        })
        task_id = create_resp.json()["id"]

        response = await test_client.get(f"/api/v1/tasks/{task_id}/context")
        assert response.status_code == 200
        data = response.json()
        assert "context" in data
