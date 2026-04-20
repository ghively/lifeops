"""
Tests for the search router.
"""

import pytest


@pytest.mark.asyncio
class TestSearchRouter:
    """Test cases for /api/search endpoints."""

    async def test_search_empty_query(self, test_client):
        """Test search with empty query returns 400."""
        response = await test_client.get("/api/v1/search", params={"q": ""})
        assert response.status_code == 400

    async def test_search_with_query(self, test_client):
        """Test search with a query string."""
        response = await test_client.get("/api/v1/search", params={"q": "test"})
        assert response.status_code == 200
        data = response.json()
        assert "results" in data

    async def test_search_with_type_filter(self, test_client):
        """Test search with collection filter."""
        response = await test_client.get("/api/v1/search", params={"q": "test", "collection": "objects"})
        assert response.status_code == 200
        data = response.json()
        assert "results" in data

    async def test_search_with_limit(self, test_client):
        """Test search with custom limit."""
        response = await test_client.get("/api/v1/search", params={"q": "test", "limit": 5})
        assert response.status_code == 200

    async def test_search_exact_mode(self, test_client):
        """Test exact search mode."""
        # Create an object with known content
        await test_client.post(
            "/api/v1/objects",
            json={
                "title": "Searchable Note",
                "content": "This is a test note about python programming",
                "type": "note",
            },
        )

        response = await test_client.get("/api/v1/search", params={"q": "python", "exact": True})
        assert response.status_code == 200
        data = response.json()
        assert "results" in data

    async def test_search_no_results(self, test_client):
        """Test search that returns no results."""
        response = await test_client.get("/api/v1/search", params={"q": "zzznonexistentxyz123"})
        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []

    async def test_find_similar_success(self, test_client):
        """Test finding similar objects."""
        # Create an object first
        create_resp = await test_client.post(
            "/api/v1/objects",
            json={
                "title": "Test Object",
                "content": "Test content for similarity",
                "type": "note",
            },
        )
        assert create_resp.status_code == 201
        obj_id = create_resp.json()["id"]

        response = await test_client.get(f"/api/v1/search/similar/{obj_id}")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data

    async def test_find_similar_not_found(self, test_client):
        """Test finding similar for non-existent object."""
        response = await test_client.get("/api/v1/search/similar/non-existent")
        assert response.status_code == 404

    async def test_search_special_characters(self, test_client):
        """Test search with special characters."""
        response = await test_client.get("/api/v1/search", params={"q": "test & <special>"})
        assert response.status_code == 200

    async def test_search_unicode(self, test_client):
        """Test search with unicode characters."""
        response = await test_client.get("/api/v1/search", params={"q": "日本語テスト"})
        assert response.status_code == 200
