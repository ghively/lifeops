"""
Tests for the settings router.
"""

import pytest

from app.routers.settings import (
    MAX_PREFERENCE_VALUE_BYTES,
    MAX_PREFERENCES_PER_USER,
)


@pytest.mark.asyncio
class TestSettingsRouter:
    """Test cases for /api/settings endpoints."""

    async def test_get_settings(self, test_client, mock_sqlite_manager):
        """Test getting application settings."""
        response = await test_client.get("/api/v1/settings")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    async def test_update_settings(self, test_client, mock_sqlite_manager):
        """Test updating application settings."""
        update_data = {
            "backup_snapshots": True,
            "backup_markdown": True,
            "embedding_model": "all-MiniLM-L6-v2",
        }

        response = await test_client.put("/api/v1/settings", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    async def test_update_settings_partial(self, test_client, mock_sqlite_manager):
        """Test partial settings update."""
        update_data = {
            "backup_snapshots": False,
        }

        response = await test_client.put("/api/v1/settings", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data.get("backup_snapshots") == False

    async def test_get_watched_folders_empty(self, test_client, mock_sqlite_manager):
        """Test getting watched folders when none exist."""
        response = await test_client.get("/api/v1/settings/watched-folders")

        assert response.status_code == 200
        data = response.json()
        assert "folders" in data
        assert data["folders"] == []

    async def test_add_watched_folder(self, test_client, mock_sqlite_manager):
        """Test adding a watched folder."""
        folder_data = {
            "path": "/path/to/watch",
            "recursive": True,
            "include_patterns": ["*.txt", "*.md"],
            "exclude_patterns": ["*.tmp", "*.bak"],
        }

        response = await test_client.post("/api/v1/settings/watched-folders", json=folder_data)

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["path"] == folder_data["path"]

    async def test_add_watched_folder_missing_path(self, test_client):
        """Test adding watched folder without path."""
        folder_data = {
            "recursive": True,
        }

        response = await test_client.post("/api/v1/settings/watched-folders", json=folder_data)

        assert response.status_code == 400

    async def test_remove_watched_folder(self, test_client, mock_sqlite_manager):
        """Test removing a watched folder."""
        response = await test_client.delete("/api/v1/settings/watched-folders/folder-id-1")

        assert response.status_code in [200, 404]

    async def test_trigger_backup_snapshot(self, test_client):
        """Test triggering snapshot backup."""
        backup_data = {
            "type": "snapshot",
        }

        response = await test_client.post("/api/v1/settings/backup", json=backup_data)

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    async def test_trigger_backup_markdown(self, test_client):
        """Test triggering markdown export backup."""
        backup_data = {
            "type": "markdown",
        }

        response = await test_client.post("/api/v1/settings/backup", json=backup_data)

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    async def test_trigger_backup_git(self, test_client):
        """Test triggering git sync backup."""
        backup_data = {
            "type": "git",
        }

        response = await test_client.post("/api/v1/settings/backup", json=backup_data)

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    async def test_trigger_backup_invalid_type(self, test_client):
        """Test triggering backup with invalid type."""
        backup_data = {
            "type": "invalid_type",
        }

        response = await test_client.post("/api/v1/settings/backup", json=backup_data)

        assert response.status_code == 400


@pytest.mark.asyncio
class TestSettingsService:
    """Test cases for settings management."""

    async def test_setting_persistence(self, mock_sqlite_manager):
        """Test that settings persist across restarts."""
        # Set a value
        await mock_sqlite_manager.upsert_setting("test_key", "test_value")
        # Retrieve it
        value = await mock_sqlite_manager.get_setting("test_key")
        assert value == "test_value"

    async def test_setting_defaults(self, mock_sqlite_manager):
        """Test getting default values for unset settings."""
        value = await mock_sqlite_manager.get_setting("nonexistent_key", default="default")
        assert value == "default"

    async def test_setting_overwrite(self, mock_sqlite_manager):
        """Test overwriting existing settings."""
        await mock_sqlite_manager.upsert_setting("key", "value1")
        await mock_sqlite_manager.upsert_setting("key", "value2")
        value = await mock_sqlite_manager.get_setting("key")
        assert value == "value2"


@pytest.mark.asyncio
class TestUserPreferences:
    """Per-user arbitrary key/value preference bag (issue cluster #156-#170)."""

    async def test_get_returns_empty_bag_initially(self, test_client, mock_sqlite_manager):
        response = await test_client.get("/api/v1/settings/preferences")
        assert response.status_code == 200
        assert response.json() == {}

    async def test_put_then_get_roundtrips_arbitrary_keys(self, test_client, mock_sqlite_manager):
        body = {
            "theme": "dark",
            "sidebar_width": 280,
            "experimental_flags": {"agents_v2": True},
            "recent_agents": ["alpha", "beta"],
        }
        put = await test_client.put("/api/v1/settings/preferences", json=body)
        assert put.status_code == 200
        assert put.json() == body

        get = await test_client.get("/api/v1/settings/preferences")
        assert get.status_code == 200
        assert get.json() == body

    async def test_put_merges_into_existing_bag(self, test_client, mock_sqlite_manager):
        await test_client.put("/api/v1/settings/preferences", json={"theme": "dark"})
        await test_client.put("/api/v1/settings/preferences", json={"locale": "en-US"})

        get = await test_client.get("/api/v1/settings/preferences")
        assert get.json() == {"theme": "dark", "locale": "en-US"}

    async def test_put_overwrites_existing_key(self, test_client, mock_sqlite_manager):
        await test_client.put("/api/v1/settings/preferences", json={"theme": "dark"})
        await test_client.put("/api/v1/settings/preferences", json={"theme": "light"})

        get = await test_client.get("/api/v1/settings/preferences")
        assert get.json() == {"theme": "light"}

    async def test_delete_removes_one_key(self, test_client, mock_sqlite_manager):
        await test_client.put(
            "/api/v1/settings/preferences", json={"theme": "dark", "locale": "en-US"}
        )
        delete = await test_client.delete("/api/v1/settings/preferences/theme")
        assert delete.status_code == 200
        assert delete.json() == {"message": "Preference removed", "key": "theme"}

        get = await test_client.get("/api/v1/settings/preferences")
        assert get.json() == {"locale": "en-US"}

    async def test_delete_unknown_key_returns_404(self, test_client, mock_sqlite_manager):
        response = await test_client.delete("/api/v1/settings/preferences/nope")
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "bad_key",
        ["", "has spaces", "has/slash", "ümlaut", "x" * 65],
    )
    async def test_put_rejects_invalid_keys(self, test_client, mock_sqlite_manager, bad_key):
        response = await test_client.put(
            "/api/v1/settings/preferences", json={bad_key: "value"}
        )
        assert response.status_code == 400

    async def test_put_rejects_oversized_value(self, test_client, mock_sqlite_manager):
        oversized = "x" * (MAX_PREFERENCE_VALUE_BYTES + 1)
        response = await test_client.put(
            "/api/v1/settings/preferences", json={"big": oversized}
        )
        assert response.status_code == 400

    async def test_put_rejects_when_cap_exceeded(self, test_client, mock_sqlite_manager):
        baseline = {f"k{i}": i for i in range(MAX_PREFERENCES_PER_USER)}
        baseline_response = await test_client.put(
            "/api/v1/settings/preferences", json=baseline
        )
        assert baseline_response.status_code == 200

        overflow = await test_client.put(
            "/api/v1/settings/preferences", json={"one_too_many": True}
        )
        assert overflow.status_code == 400


@pytest.mark.asyncio
class TestUserPreferencesStorage:
    """Direct SQLiteManager helpers — verify mock matches the contract the
    router relies on."""

    async def test_per_user_isolation(self, mock_sqlite_manager):
        await mock_sqlite_manager.upsert_user_preferences("user-a", {"theme": "dark"})
        await mock_sqlite_manager.upsert_user_preferences("user-b", {"theme": "light"})

        assert await mock_sqlite_manager.list_user_preferences("user-a") == {"theme": "dark"}
        assert await mock_sqlite_manager.list_user_preferences("user-b") == {"theme": "light"}

    async def test_delete_returns_false_when_missing(self, mock_sqlite_manager):
        removed = await mock_sqlite_manager.delete_user_preference("user-a", "missing")
        assert removed is False


@pytest.mark.asyncio
class TestBackupService:
    """Test cases for backup service."""

    async def test_backup_service_exists(self):
        """Test that backup service exists."""
        from app.services.backup import backup_service

        assert hasattr(backup_service, "run_backup")
        assert callable(backup_service.run_backup)
