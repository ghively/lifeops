"""
Tests for the files router.
"""

import pytest

import app.routers.files as files_router_module


# Patch path validation to allow test paths
def _permissive_validate(path: str) -> str:
    return path


files_router_module.validate_file_path = _permissive_validate


@pytest.mark.asyncio
class TestFilesRouter:
    """Test cases for /api/files endpoints."""

    async def test_list_files_empty(self, test_client):
        """Test listing files when none exist."""
        response = await test_client.get("/api/v1/files")
        assert response.status_code == 200
        data = response.json()
        assert "files" in data
        assert data["files"] == []

    async def test_list_files_with_data(self, test_client):
        """Test listing files after indexing."""
        # Index a file via content endpoint
        await test_client.post(
            "/api/v1/files/test-file-1/content",
            json={
                "path": "/test/document.md",
                "content": "Test file content",
                "content_type": "text/markdown",
            },
        )

        response = await test_client.get("/api/v1/files")
        assert response.status_code == 200
        data = response.json()
        assert "files" in data
        assert len(data["files"]) >= 1

    async def test_get_file_success(self, test_client):
        """Test getting a file by ID."""
        # Index a file first
        await test_client.post(
            "/api/v1/files/test-file-2/content",
            json={
                "path": "/test/readme.md",
                "content": "Readme content",
            },
        )

        response = await test_client.get("/api/v1/files/test-file-2")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "test-file-2"

    async def test_get_file_not_found(self, test_client):
        """Test getting a non-existent file."""
        response = await test_client.get("/api/v1/files/non-existent")
        assert response.status_code == 404

    async def test_reindex_file_success(self, test_client):
        """Test reindexing a file."""
        # Index a file first
        await test_client.post(
            "/api/v1/files/test-file-3/content",
            json={
                "path": "/tmp/test-reindex.md",
                "content": "Reindex content",
            },
        )

        response = await test_client.post("/api/v1/files/test-file-3/reindex")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    async def test_reindex_file_not_found(self, test_client):
        """Test reindexing a non-existent file."""
        response = await test_client.post("/api/v1/files/non-existent/reindex")
        assert response.status_code == 404

    async def test_file_notification(self, test_client):
        """Test file change notification."""
        data = {
            "event_type": "created",
            "path": "/test/new-file.md",
        }
        response = await test_client.post("/api/v1/files/notify", json=data)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    async def test_file_notification_missing_fields(self, test_client):
        """Test file notification with missing fields."""
        response = await test_client.post("/api/v1/files/notify", json={})
        assert response.status_code in [400, 422]

    async def test_index_file_content(self, test_client):
        """Test indexing file content."""
        response = await test_client.post(
            "/api/v1/files/test-file-4/content",
            json={
                "path": "/test/index-me.md",
                "content": "Content to index",
                "content_type": "text/markdown",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["file_id"] == "test-file-4"

    async def test_index_file_content_missing_path(self, test_client):
        """Test indexing file content without path."""
        response = await test_client.post(
            "/api/v1/files/test-file-5/content",
            json={
                "content": "No path",
            },
        )
        assert response.status_code in [400, 422]

    async def test_file_delete_notification(self, test_client):
        """Test file delete notification."""
        response = await test_client.post(
            "/api/v1/files/notify",
            json={
                "event_type": "deleted",
                "path": "/test/deleted-file.md",
            },
        )
        assert response.status_code == 200

    async def test_file_move_notification(self, test_client):
        """Test file move notification."""
        response = await test_client.post(
            "/api/v1/files/notify",
            json={
                "event_type": "moved",
                "path": "/test/old-path.md",
                "dest_path": "/test/new-path.md",
            },
        )
        assert response.status_code == 200
