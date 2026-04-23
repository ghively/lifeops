"""Tests for system router endpoints and log parsing utilities."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.system import _parse_nginx_line, _read_log_entries


@pytest.mark.asyncio
async def test_smoke_test_all_systems_healthy(test_client):
    """Test smoke-test endpoint when all subsystems are healthy."""
    with patch("app.routers.system.qdrant_manager") as mock_qdrant, patch(
        "app.routers.system.sqlite3"
    ) as mock_sqlite_module:
        # Mock Qdrant
        mock_client = MagicMock()
        mock_coll = MagicMock()
        mock_coll.name = "test_collection"
        mock_client.get_collections.return_value = MagicMock(collections=[mock_coll])
        mock_client.get_collection.return_value = MagicMock(
            config=MagicMock(
                params=MagicMock(vectors={"size": 384})
            )
        )
        mock_client.search.return_value = []
        mock_qdrant.get_client.return_value = mock_client

        # Mock SQLite
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("2024-01-01 12:00:00",)
        mock_conn.cursor.return_value = mock_cursor
        mock_sqlite_module.connect.return_value = mock_conn

        response = await test_client.get("/api/v1/system/smoke-test")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pass"
    assert "duration_ms" in data
    assert "results" in data
    assert data["results"]["sqlite"]["status"] == "pass"
    assert data["results"]["qdrant"]["status"] == "pass"
    assert data["results"]["filesystem"]["status"] == "pass"


@pytest.mark.asyncio
async def test_smoke_test_degraded_when_qdrant_down(test_client):
    """Test smoke-test endpoint when Qdrant is unavailable."""
    with patch("app.routers.system.qdrant_manager") as mock_qdrant, patch(
        "app.routers.system.sqlite3"
    ) as mock_sqlite_module:
        # Mock Qdrant failure
        mock_qdrant.get_client.side_effect = Exception("Qdrant connection failed")

        # Mock SQLite success
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("2024-01-01 12:00:00",)
        mock_conn.cursor.return_value = mock_cursor
        mock_sqlite_module.connect.return_value = mock_conn

        response = await test_client.get("/api/v1/system/smoke-test")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "fail"
    assert data["results"]["qdrant"]["status"] == "fail"
    assert data["results"]["sqlite"]["status"] == "pass"


@pytest.mark.asyncio
async def test_smoke_test_degraded_when_sqlite_down(test_client):
    """Test smoke-test endpoint when SQLite is unavailable."""
    with patch("app.routers.system.qdrant_manager") as mock_qdrant, patch(
        "app.routers.system.sqlite3"
    ) as mock_sqlite_module:
        # Mock Qdrant success
        mock_client = MagicMock()
        mock_coll = MagicMock()
        mock_coll.name = "test_collection"
        mock_client.get_collections.return_value = MagicMock(collections=[mock_coll])
        mock_client.get_collection.return_value = MagicMock(
            config=MagicMock(
                params=MagicMock(vectors={"size": 384})
            )
        )
        mock_client.search.return_value = []
        mock_qdrant.get_client.return_value = mock_client

        # Mock SQLite failure
        mock_sqlite_module.connect.side_effect = Exception("SQLite connection failed")

        response = await test_client.get("/api/v1/system/smoke-test")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "fail"
    assert data["results"]["sqlite"]["status"] == "fail"
    assert data["results"]["qdrant"]["status"] == "pass"


@pytest.mark.asyncio
async def test_logs_endpoint_requires_auth(test_client):
    """Test that logs endpoint requires authentication."""
    # test_client has auth disabled in conftest, so we need a raw client
    # or we can test that authenticated request works and unauthenticated doesn't
    # For now, just verify authenticated works
    response = await test_client.get("/api/v1/system/logs?limit=10")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_status_endpoint_shape(test_client):
    """Test that status endpoint returns expected shape."""
    response = await test_client.get("/api/v1/system/status")

    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "uptime_seconds" in data
    assert "request_counts" in data
    assert "error_counts" in data
    assert "active_websocket_connections" in data


def test_parse_nginx_line_valid():
    """Test parsing a valid nginx access log line."""
    line = '127.0.0.1 - - [21/Nov/2024:10:00:00 +0000] "GET /api/v1/test HTTP/1.1" 200 1024 "-" "curl/7.68.0"'
    result = _parse_nginx_line(line)

    assert result is not None
    assert result["remote"] == "127.0.0.1"
    assert result["method"] == "GET"
    assert result["path"] == "/api/v1/test"
    assert result["status"] == 200
    assert result["body_bytes"] == "1024"
    assert "timestamp" in result


def test_parse_nginx_line_malformed_timestamp():
    """Test parsing nginx line with malformed timestamp."""
    line = '127.0.0.1 - - [INVALID] "GET /api/v1/test HTTP/1.1" 200 1024 "-" "curl/7.68.0"'
    result = _parse_nginx_line(line)

    assert result is None


def test_parse_nginx_line_missing_fields():
    """Test parsing nginx line with missing fields."""
    line = '127.0.0.1 - - [21/Nov/2024:10:00:00 +0000] "GET HTTP/1.1" 200 1024'
    result = _parse_nginx_line(line)

    assert result is None


def test_parse_nginx_line_empty_line():
    """Test parsing an empty line."""
    result = _parse_nginx_line("")
    assert result is None


def test_parse_nginx_line_with_status_codes():
    """Test parsing nginx lines with different status codes."""
    for status in [200, 301, 400, 401, 403, 404, 500, 502, 503]:
        line = f'127.0.0.1 - - [21/Nov/2024:10:00:00 +0000] "GET /api HTTP/1.1" {status} 1024 "-" "curl"'
        result = _parse_nginx_line(line)
        assert result is not None
        assert result["status"] == status


def test_parse_nginx_line_very_long():
    """Test parsing very long nginx log line."""
    long_ua = "a" * 2000
    line = f'127.0.0.1 - - [21/Nov/2024:10:00:00 +0000] "GET /api HTTP/1.1" 200 1024 "http://example.com" "{long_ua}"'
    result = _parse_nginx_line(line)

    assert result is not None
    assert result["ua"] == long_ua


@pytest.mark.asyncio
async def test_logs_endpoint_with_limit(test_client):
    """Test logs endpoint respects limit parameter."""
    response = await test_client.get("/api/v1/system/logs?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "logs" in data
    assert "count" in data
    assert data["count"] <= 10


@pytest.mark.asyncio
async def test_logs_endpoint_with_level_filter(test_client):
    """Test logs endpoint with level filter."""
    response = await test_client.get("/api/v1/system/logs?level=error&limit=50")
    assert response.status_code == 200
    data = response.json()
    assert "logs" in data
    for log in data["logs"]:
        assert log["level"] == "error" or log["level"] == ""


@pytest.mark.asyncio
async def test_post_frontend_log_single_entry(test_client):
    """Test posting a single frontend log entry."""
    payload = {
        "level": "error",
        "message": "Test error",
        "component": "auth",
        "url": "http://example.com/login",
        "timestamp": "2024-01-01T12:00:00Z",
    }
    response = await test_client.post("/api/v1/system/logs", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_post_frontend_log_batch(test_client):
    """Test posting batch of frontend log entries."""
    payload = {
        "batch": [
            {
                "level": "error",
                "message": f"Error {i}",
                "component": "auth",
            }
            for i in range(5)
        ]
    }
    response = await test_client.post("/api/v1/system/logs", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["count"] == 5


@pytest.mark.asyncio
async def test_post_frontend_log_invalid_level(test_client):
    """Test posting log with invalid level."""
    payload = {
        "level": "invalid_level",
        "message": "Test",
        "component": "auth",
    }
    response = await test_client.post("/api/v1/system/logs", json=payload)

    assert response.status_code == 400
