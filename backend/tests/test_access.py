"""Tests for app.services.access.user_can_access_object (issue #176)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.access import user_can_access_object


def _record(payload):
    return SimpleNamespace(id="doc-1", payload=payload)


@pytest.mark.asyncio
async def test_creator_match_allows_access():
    fake = AsyncMock(return_value=[_record({"created_by": "alice"})])
    with patch("app.services.access.QdrantManager.safe_retrieve", fake), patch(
        "app.services.access.qdrant_manager.get_async_client",
        return_value=MagicMock(),
    ):
        assert await user_can_access_object("alice", "doc-1") is True


@pytest.mark.asyncio
async def test_other_user_denied():
    fake = AsyncMock(return_value=[_record({"created_by": "alice"})])
    with patch("app.services.access.QdrantManager.safe_retrieve", fake), patch(
        "app.services.access.qdrant_manager.get_async_client",
        return_value=MagicMock(),
    ):
        assert await user_can_access_object("mallory", "doc-1") is False


@pytest.mark.asyncio
async def test_created_by_nested_under_properties():
    fake = AsyncMock(return_value=[_record({"properties": {"created_by": "alice"}})])
    with patch("app.services.access.QdrantManager.safe_retrieve", fake), patch(
        "app.services.access.qdrant_manager.get_async_client",
        return_value=MagicMock(),
    ):
        assert await user_can_access_object("alice", "doc-1") is True
        assert await user_can_access_object("mallory", "doc-1") is False


@pytest.mark.asyncio
async def test_legacy_object_without_owner_is_accessible():
    fake = AsyncMock(return_value=[_record({"title": "legacy"})])
    with patch("app.services.access.QdrantManager.safe_retrieve", fake), patch(
        "app.services.access.qdrant_manager.get_async_client",
        return_value=MagicMock(),
    ):
        assert await user_can_access_object("anyone", "doc-1") is True


@pytest.mark.asyncio
async def test_missing_object_denied():
    fake = AsyncMock(return_value=[])
    with patch("app.services.access.QdrantManager.safe_retrieve", fake), patch(
        "app.services.access.qdrant_manager.get_async_client",
        return_value=MagicMock(),
    ):
        assert await user_can_access_object("alice", "doc-1") is False


@pytest.mark.asyncio
async def test_empty_inputs_denied():
    assert await user_can_access_object("", "doc-1") is False
    assert await user_can_access_object("alice", "") is False


@pytest.mark.asyncio
async def test_retrieve_error_denied():
    fake = AsyncMock(side_effect=RuntimeError("qdrant down"))
    with patch("app.services.access.QdrantManager.safe_retrieve", fake), patch(
        "app.services.access.qdrant_manager.get_async_client",
        return_value=MagicMock(),
    ):
        assert await user_can_access_object("alice", "doc-1") is False
