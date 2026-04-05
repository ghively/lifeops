"""
Tests for the blocks router.
"""

import pytest


@pytest.mark.asyncio
class TestBlocksRouter:
    """Test cases for /api/blocks endpoints."""

    async def test_list_blocks_empty(self, test_client):
        """Test listing blocks for an object with no blocks."""
        response = await test_client.get("/api/v1/blocks/object/test-object-1")
        assert response.status_code == 200
        data = response.json()
        assert "blocks" in data
        assert data["blocks"] == []

    async def test_create_block_success(self, test_client):
        """Test creating a new block."""
        block_data = {
            "object_id": "test-object-1",
            "content": "Test block content",
            "type": "paragraph",
        }
        response = await test_client.post("/api/v1/blocks", json=block_data)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["content"] == block_data["content"]
        assert data["object_id"] == block_data["object_id"]

    async def test_create_block_with_all_fields(self, test_client):
        """Test creating a block with all fields."""
        block_data = {
            "object_id": "test-object-1",
            "content": "Full block",
            "type": "heading",
            "level": 2,
            "order": 0,
            "properties": {"color": "red"},
        }
        response = await test_client.post("/api/v1/blocks", json=block_data)
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "heading"
        assert data["level"] == 2

    async def test_update_block_success(self, test_client):
        """Test updating a block."""
        # Create a block first
        create_resp = await test_client.post("/api/v1/blocks", json={
            "object_id": "test-object-1",
            "content": "Original content",
            "type": "paragraph",
        })
        assert create_resp.status_code == 200
        block_id = create_resp.json()["id"]

        update_data = {"content": "Updated content"}
        response = await test_client.put(f"/api/v1/blocks/{block_id}", json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Updated content"

    async def test_update_block_not_found(self, test_client):
        """Test updating a non-existent block."""
        response = await test_client.put("/api/v1/blocks/non-existent", json={"content": "test"})
        assert response.status_code == 404

    async def test_delete_block_success(self, test_client):
        """Test deleting a block."""
        # Create a block first
        create_resp = await test_client.post("/api/v1/blocks", json={
            "object_id": "test-object-1",
            "content": "To delete",
            "type": "paragraph",
        })
        assert create_resp.status_code == 200
        block_id = create_resp.json()["id"]

        response = await test_client.delete(f"/api/v1/blocks/{block_id}")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    async def test_delete_block_not_found(self, test_client):
        """Test deleting a non-existent block."""
        response = await test_client.delete("/api/v1/blocks/non-existent")
        assert response.status_code == 404

    async def test_create_checklist_block(self, test_client):
        """Test creating a checklist block."""
        block_data = {
            "object_id": "test-object-1",
            "content": "Checklist item",
            "type": "checklist",
            "properties": {"checked": False},
        }
        response = await test_client.post("/api/v1/blocks", json=block_data)
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "checklist"

    async def test_create_code_block(self, test_client):
        """Test creating a code block."""
        block_data = {
            "object_id": "test-object-1",
            "content": "print('hello')",
            "type": "code",
            "properties": {"language": "python"},
        }
        response = await test_client.post("/api/v1/blocks", json=block_data)
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "code"

    async def test_batch_update_blocks(self, test_client):
        """Test batch updating blocks."""
        # Create a block first
        create_resp = await test_client.post("/api/v1/blocks", json={
            "object_id": "test-object-1",
            "content": "Block",
            "type": "paragraph",
        })
        assert create_resp.status_code == 200
        block_id = create_resp.json()["id"]

        response = await test_client.post("/api/v1/blocks/batch-update", json={
            "blocks": [{"id": block_id, "order": 5}]
        })
        assert response.status_code == 200
        data = response.json()
        assert "count" in data

    async def test_list_blocks_for_object(self, test_client):
        """Test listing blocks after creating them."""
        # Create a block
        await test_client.post("/api/v1/blocks", json={
            "object_id": "test-obj-list",
            "content": "Block 1",
            "type": "paragraph",
        })

        response = await test_client.get("/api/v1/blocks/object/test-obj-list")
        assert response.status_code == 200
        data = response.json()
        assert "blocks" in data
        assert len(data["blocks"]) >= 1
