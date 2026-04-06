"""
Tests for the relations router.
"""

import pytest


@pytest.mark.asyncio
class TestRelationsRouter:
    """Test cases for /api/relations endpoints."""

    async def test_get_relations_for_object_empty(self, test_client):
        """Test getting relations for an object with no relations."""
        response = await test_client.get("/api/v1/relations/object/test-object-1")
        assert response.status_code == 200
        data = response.json()
        assert "relations" in data
        assert data["relations"] == []

    async def test_get_relations_for_object_with_data(self, test_client):
        """Test getting relations for an object."""
        # Create two objects and a relation between them
        obj1 = await test_client.post("/api/v1/objects", json={
            "title": "Object 1", "content": "Content 1", "type": "note",
        })
        obj2 = await test_client.post("/api/v1/objects", json={
            "title": "Object 2", "content": "Content 2", "type": "note",
        })
        assert obj1.status_code == 201
        assert obj2.status_code == 201

        relation_data = {
            "source_id": obj1.json()["id"],
            "source_type": "object",
            "target_id": obj2.json()["id"],
            "target_type": "object",
            "relation_type": "references",
        }
        create_resp = await test_client.post("/api/v1/relations", json=relation_data)
        assert create_resp.status_code == 200

        # Get relations for source object
        response = await test_client.get(f"/api/v1/relations/object/{obj1.json()['id']}")
        assert response.status_code == 200
        data = response.json()
        assert "relations" in data
        assert len(data["relations"]) >= 1

    async def test_create_relation_success(self, test_client):
        """Test creating a relation."""
        # Create two objects first
        obj1 = await test_client.post("/api/v1/objects", json={
            "title": "Source", "content": "Source content", "type": "note",
        })
        obj2 = await test_client.post("/api/v1/objects", json={
            "title": "Target", "content": "Target content", "type": "note",
        })

        relation_data = {
            "source_id": obj1.json()["id"],
            "source_type": "object",
            "target_id": obj2.json()["id"],
            "target_type": "object",
            "relation_type": "references",
        }
        response = await test_client.post("/api/v1/relations", json=relation_data)
        assert response.status_code == 200

    async def test_create_relation_invalid_type(self, test_client):
        """Test creating a relation with invalid type."""
        obj1 = await test_client.post("/api/v1/objects", json={
            "title": "Source", "content": "Source", "type": "note",
        })
        obj2 = await test_client.post("/api/v1/objects", json={
            "title": "Target", "content": "Target", "type": "note",
        })

        # Missing required fields should give 422
        response = await test_client.post("/api/v1/relations", json={
            "source_id": obj1.json()["id"],
            "source_type": "object",
            "target_id": obj2.json()["id"],
            # missing target_type
        })
        assert response.status_code in [422, 400]

    async def test_create_bidirectional_relation(self, test_client):
        """Test creating a bidirectional relation."""
        obj1 = await test_client.post("/api/v1/objects", json={
            "title": "A", "content": "A content", "type": "note",
        })
        obj2 = await test_client.post("/api/v1/objects", json={
            "title": "B", "content": "B content", "type": "note",
        })

        relation_data = {
            "source_id": obj1.json()["id"],
            "source_type": "object",
            "target_id": obj2.json()["id"],
            "target_type": "object",
            "relation_type": "related_to",
        }
        response = await test_client.post("/api/v1/relations", json=relation_data)
        assert response.status_code == 200

    async def test_delete_relation_success(self, test_client):
        """Test deleting a relation."""
        obj1 = await test_client.post("/api/v1/objects", json={
            "title": "A", "content": "A", "type": "note",
        })
        obj2 = await test_client.post("/api/v1/objects", json={
            "title": "B", "content": "B", "type": "note",
        })

        relation_data = {
            "source_id": obj1.json()["id"],
            "source_type": "object",
            "target_id": obj2.json()["id"],
            "target_type": "object",
            "relation_type": "references",
        }
        create_resp = await test_client.post("/api/v1/relations", json=relation_data)
        assert create_resp.status_code == 200
        relation_id = create_resp.json()["id"]

        response = await test_client.delete(f"/api/v1/relations/{relation_id}")
        assert response.status_code == 200

    async def test_update_relation_success(self, test_client):
        """Test updating a relation."""
        obj1 = await test_client.post("/api/v1/objects", json={
            "title": "A", "content": "A", "type": "note",
        })
        obj2 = await test_client.post("/api/v1/objects", json={
            "title": "B", "content": "B", "type": "note",
        })

        relation_data = {
            "source_id": obj1.json()["id"],
            "source_type": "object",
            "target_id": obj2.json()["id"],
            "target_type": "object",
            "relation_type": "references",
        }
        create_resp = await test_client.post("/api/v1/relations", json=relation_data)
        assert create_resp.status_code == 200
        relation_id = create_resp.json()["id"]

        update_data = {"relation_type": "depends_on"}
        response = await test_client.put(f"/api/v1/relations/{relation_id}", json=update_data)
        assert response.status_code == 200

    async def test_delete_relation_not_found(self, test_client):
        """Test deleting a non-existent relation."""
        response = await test_client.delete("/api/v1/relations/non-existent")
        assert response.status_code == 200  # Delete is idempotent in the service
