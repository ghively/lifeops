"""
Tests for the objects router.
"""

import pytest
from qdrant_client import models as qdrant_models


@pytest.mark.asyncio
class TestObjectsRouter:
    """Test cases for /api/objects endpoints."""

    async def test_list_objects_empty(self, test_client):
        """Test listing objects when none exist."""
        response = await test_client.get("/api/v1/objects")
        assert response.status_code == 200
        data = response.json()
        assert "objects" in data
        assert data["objects"] == []
        assert data["total"] == 0

    async def test_list_objects_with_data(self, test_client):
        """Test listing objects with existing data."""
        # Create an object first
        create_resp = await test_client.post("/api/v1/objects", json={
            "title": "Test Object",
            "content": "Test content",
            "type": "note",
        })
        assert create_resp.status_code == 200

        response = await test_client.get("/api/v1/objects")
        assert response.status_code == 200
        data = response.json()
        assert "objects" in data
        assert data["total"] >= 1

    async def test_list_objects_with_filters(self, test_client):
        """Test listing objects with query filters."""
        response = await test_client.get(
            "/api/v1/objects",
            params={"type": "note", "limit": 10}
        )
        assert response.status_code == 200
        data = response.json()
        assert "objects" in data

    async def test_get_object_success(self, test_client):
        """Test getting a specific object by ID."""
        # Create an object first
        create_resp = await test_client.post("/api/v1/objects", json={
            "title": "Test Object",
            "content": "Test content",
            "type": "note",
        })
        assert create_resp.status_code == 200
        obj_id = create_resp.json()["id"]

        response = await test_client.get(f"/api/v1/objects/{obj_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == obj_id
        assert data["title"] == "Test Object"

    async def test_get_object_not_found(self, test_client):
        """Test getting a non-existent object."""
        response = await test_client.get("/api/v1/objects/non-existent-id")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    async def test_create_object_success(self, test_client):
        """Test creating a new object."""
        object_data = {
            "title": "New Object",
            "content": "New content",
            "type": "note",
        }
        response = await test_client.post("/api/v1/objects", json=object_data)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["title"] == object_data["title"]
        assert data["content"] == object_data["content"]

    async def test_create_object_missing_required(self, test_client):
        """Test creating an object with missing required fields."""
        object_data = {"content": "Content without title"}
        response = await test_client.post("/api/v1/objects", json=object_data)
        assert response.status_code in [422, 400]

    async def test_update_object_success(self, test_client):
        """Test updating an existing object."""
        # Create an object first
        create_resp = await test_client.post("/api/v1/objects", json={
            "title": "Original Title",
            "content": "Original content",
            "type": "note",
        })
        assert create_resp.status_code == 200
        obj_id = create_resp.json()["id"]

        update_data = {"title": "Updated Title", "content": "Updated content"}
        response = await test_client.put(f"/api/v1/objects/{obj_id}", json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == obj_id
        assert data["title"] == "Updated Title"

    async def test_update_object_not_found(self, test_client):
        """Test updating a non-existent object."""
        response = await test_client.put("/api/v1/objects/non-existent", json={"title": "Updated"})
        assert response.status_code == 404

    async def test_delete_object_success(self, test_client):
        """Test deleting an object."""
        # Create an object first
        create_resp = await test_client.post("/api/v1/objects", json={
            "title": "To Delete",
            "content": "Will be deleted",
            "type": "note",
        })
        assert create_resp.status_code == 200
        obj_id = create_resp.json()["id"]

        response = await test_client.delete(f"/api/v1/objects/{obj_id}")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    async def test_delete_object_not_found(self, test_client):
        """Test deleting a non-existent object."""
        response = await test_client.delete("/api/v1/objects/non-existent")
        assert response.status_code == 404

    async def test_get_object_relations(self, test_client):
        """Test getting relations for an object."""
        response = await test_client.get("/api/v1/objects/test-object-1/relations")
        assert response.status_code == 200
        data = response.json()
        assert "relations" in data

    async def test_create_object_with_properties(self, test_client):
        """Test creating an object with properties."""
        object_data = {
            "title": "Tagged Object",
            "content": "Content",
            "type": "note",
            "properties": {
                "tags": ["tag1", "tag2", "tag3"],
                "status": "active"
            },
        }
        response = await test_client.post("/api/v1/objects", json=object_data)
        assert response.status_code == 200
        data = response.json()
        assert "properties" in data
        assert data["properties"]["tags"] == ["tag1", "tag2", "tag3"]

    async def test_create_object_with_all_fields(self, test_client):
        """Test creating an object with all optional fields."""
        object_data = {
            "title": "Complete Object",
            "content": "Content",
            "type": "note",
            "properties": {
                "tags": ["test"],
                "status": "active",
                "priority": "high",
            },
            "icon": "📝",
            "layout": "default",
        }
        response = await test_client.post("/api/v1/objects", json=object_data)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == object_data["title"]
        assert data["icon"] == object_data["icon"]
        assert data["layout"] == object_data["layout"]

    async def test_create_object_parses_tags_and_mentions(self, test_client_with_store):
        """Test creating an object parses tags and valid agent mentions from content."""
        client, store = test_client_with_store
        store["points"]["agent-1"] = qdrant_models.PointStruct(
            id="agent-1",
            vector=[0.1] * 384,
            payload={
                "id": "agent-1",
                "type": "agent",
                "title": "researcher",
                "content": "Research agent",
                "properties": {"agent_name": "researcher"},
            },
        )
        store["counters"]["objects"] += 1

        response = await client.post("/api/v1/objects", json={
            "title": "Mentioned Object",
            "content": "Working with #alpha #beta and @researcher plus @unknown and #alpha",
            "type": "note",
            "properties": {"tags": ["seed"]},
        })

        assert response.status_code == 200
        data = response.json()
        assert data["properties"]["tags"] == ["seed", "alpha", "beta"]
        assert data["properties"]["mentions"] == ["researcher"]

    async def test_update_object_parses_tags_and_mentions(self, test_client_with_store):
        """Test updating an object refreshes parsed tags and valid agent mentions."""
        client, store = test_client_with_store
        store["points"]["agent-1"] = qdrant_models.PointStruct(
            id="agent-1",
            vector=[0.1] * 384,
            payload={
                "id": "agent-1",
                "type": "agent",
                "title": "writer",
                "content": "Writing agent",
                "properties": {"agent_name": "writer"},
            },
        )
        store["counters"]["objects"] += 1

        create_resp = await client.post("/api/v1/objects", json={
            "title": "Original",
            "content": "Nothing parsed here",
            "type": "note",
        })
        object_id = create_resp.json()["id"]

        response = await client.put(f"/api/v1/objects/{object_id}", json={
            "content": "Updated with #release @writer @missing",
            "properties": {"tags": ["manual"]},
        })

        assert response.status_code == 200
        data = response.json()
        assert data["properties"]["tags"] == ["manual", "release"]
        assert data["properties"]["mentions"] == ["writer"]
