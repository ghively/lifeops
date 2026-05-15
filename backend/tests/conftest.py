"""
Shared pytest fixtures for Knowledge OS backend tests.
"""

import os

# Must be set before any app.* imports so AuthService's startup guard passes.
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-ci-only")

import asyncio
import sys
from contextlib import ExitStack
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from qdrant_client import models as qdrant_models

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def mock_qdrant_client():
    """Mock Qdrant client with realistic collection and point operations."""
    mock_client = MagicMock()

    # Storage for mock data
    mock_storage = {
        "collections": {
            "objects": {},
            "blocks": {},
            "relations": {},
            "files": {},
            "images": {},
            "code": {},
            "agent_memories": {},
            "chat_logs": {},
        },
        "points": {},
    }

    # Mock collection operations
    def mock_create_collection(collection_name, vectors_config, **kwargs):
        mock_storage["collections"][collection_name] = {}

    def mock_get_collection(collection_name):
        if collection_name in mock_storage["collections"]:
            return MagicMock(result=MagicMock(status="green"))
        raise Exception("Collection not found")

    def mock_delete_collection(collection_name):
        if collection_name in mock_storage["collections"]:
            del mock_storage["collections"][collection_name]

    def mock_create_payload_index(collection_name, payload_schema_path, **kwargs):
        return None

    # Mock point operations
    def mock_upsert(collection_name, points):
        if collection_name not in mock_storage["collections"]:
            return
        for point in points:
            if isinstance(point, qdrant_models.PointStruct):
                mock_storage["points"][point.id] = point
            elif isinstance(point, dict):
                mock_storage["points"][point["id"]] = point

    def mock_search(collection_name, query_vector, limit=10, **kwargs):
        points = list(mock_storage["points"].values())
        # Return first N points as mock results
        results = []
        for i, point in enumerate(points[:limit]):
            if isinstance(point, qdrant_models.PointStruct):
                results.append(
                    qdrant_models.ScoredPoint(
                        id=point.id,
                        score=0.9 - (i * 0.1),
                        payload=point.payload,
                        version=0,
                    )
                )
        return results

    def mock_recommend(collection_name, positive, limit=10, **kwargs):
        return mock_search(collection_name, [], limit)

    def mock_delete(collection_name, points_selector, **kwargs):
        if hasattr(points_selector, "points"):
            for point_id in points_selector.points:
                mock_storage["points"].pop(point_id, None)
        elif hasattr(points_selector, "ids"):
            for point_id in points_selector.ids:
                mock_storage["points"].pop(point_id, None)

    def mock_retrieve(collection_name, ids, **kwargs):
        results = []
        for point_id in ids:
            if point_id in mock_storage["points"]:
                point = mock_storage["points"][point_id]
                if isinstance(point, qdrant_models.PointStruct):
                    results.append(
                        qdrant_models.Record(
                            id=point.id,
                            payload=point.payload,
                        )
                    )
        return results

    def mock_count(collection_name, **kwargs):
        count = len([p for p in mock_storage["points"].values() if isinstance(p, qdrant_models.PointStruct)])
        return MagicMock(count=count)

    def mock_scroll(collection_name, limit=10, **kwargs):
        points = list(mock_storage["points"].values())[:limit]
        records = []
        for point in points:
            if isinstance(point, qdrant_models.PointStruct):
                records.append(qdrant_models.Record(id=point.id, payload=point.payload, vector=point.vector))
        return records, None

    # Assign mock methods
    mock_client.create_collection = mock_create_collection
    mock_client.get_collection = mock_get_collection
    mock_client.delete_collection = mock_delete_collection
    mock_client.create_payload_index = mock_create_payload_index
    mock_client.upsert = mock_upsert
    mock_client.search = mock_search
    mock_client.recommend = mock_recommend
    mock_client.delete = mock_delete
    mock_client.retrieve = mock_retrieve
    mock_client.count = mock_count
    mock_client.scroll = mock_scroll

    # Store reference for test access
    mock_client._storage = mock_storage

    return mock_client


@pytest.fixture
def mock_async_qdrant_client():
    """Mock async Qdrant client."""
    from unittest.mock import MagicMock

    import numpy as np

    mock_client = AsyncMock()

    # Storage for mock data
    mock_storage = {
        "collections": {
            "objects": {},
            "blocks": {},
            "relations": {},
            "files": {},
            "images": {},
            "code": {},
            "agent_memories": {},
            "chat_logs": {},
        },
        "points": {},
        "counters": {
            coll: 0 for coll in ["objects", "blocks", "relations", "files", "images", "code", "agent_memories", "chat_logs"]
        },
    }

    # Mock point operations
    async def mock_upsert(collection_name, points):
        for point in points:
            if isinstance(point, qdrant_models.PointStruct):
                mock_storage["points"][point.id] = point
                mock_storage["counters"][collection_name] = mock_storage["counters"].get(collection_name, 0) + 1
            elif isinstance(point, dict):
                # Convert dict to PointStruct for storage
                vector = point.get("vector", [0.1] * 384)
                if vector is None:
                    vector = []
                mock_point = qdrant_models.PointStruct(
                    id=point["id"],
                    vector=vector,
                    payload=point.get("payload", {}),
                )
                mock_storage["points"][point["id"]] = mock_point
                mock_storage["counters"][collection_name] = mock_storage["counters"].get(collection_name, 0) + 1

    async def mock_search(collection_name, query_vector, limit=10, **kwargs):
        points = list(mock_storage["points"].values())
        results = []
        for i, point in enumerate(points[:limit]):
            if isinstance(point, qdrant_models.PointStruct):
                results.append(
                    qdrant_models.ScoredPoint(
                        id=point.id,
                        score=0.9 - (i * 0.1),
                        payload=point.payload,
                        version=0,
                    )
                )
        return results

    async def mock_recommend(collection_name, positive, limit=10, **kwargs):
        return await mock_search(collection_name, [], limit)

    async def mock_delete(collection_name, points_selector, **kwargs):
        # Handle both list of IDs and points_selector objects
        if isinstance(points_selector, list):
            for point_id in points_selector:
                if point_id in mock_storage["points"]:
                    del mock_storage["points"][point_id]
                    mock_storage["counters"][collection_name] = max(0, mock_storage["counters"].get(collection_name, 0) - 1)
        elif hasattr(points_selector, "points"):
            for point_id in points_selector.points:
                if point_id in mock_storage["points"]:
                    del mock_storage["points"][point_id]
                    mock_storage["counters"][collection_name] = max(0, mock_storage["counters"].get(collection_name, 0) - 1)
        elif hasattr(points_selector, "ids"):
            for point_id in points_selector.ids:
                if point_id in mock_storage["points"]:
                    del mock_storage["points"][point_id]
                    mock_storage["counters"][collection_name] = max(0, mock_storage["counters"].get(collection_name, 0) - 1)

    async def mock_retrieve(collection_name, ids, **kwargs):
        results = []
        for point_id in ids:
            if point_id in mock_storage["points"]:
                point = mock_storage["points"][point_id]
                if isinstance(point, qdrant_models.PointStruct):
                    results.append(
                        qdrant_models.Record(
                            id=point.id,
                            payload=point.payload,
                        )
                    )
        return results

    async def mock_count(collection_name, **kwargs):
        count = mock_storage["counters"].get(collection_name, 0)
        count_result = MagicMock()
        count_result.count = count
        return count_result

    async def mock_scroll(collection_name, limit=10, scroll_filter=None, with_payload=True, with_vectors=False, **kwargs):
        # limit may come as a FastAPI Query object or other non-int type
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 10
        points = list(mock_storage["points"].values())[:limit]
        records = []
        for point in points:
            if isinstance(point, qdrant_models.PointStruct):
                records.append(qdrant_models.Record(id=point.id, payload=point.payload, vector=point.vector))
        return records, None

    async def mock_set_payload(collection_name, payload, points):
        """Mock set_payload operation."""
        for point_id in points if isinstance(points, list) else [points]:
            if point_id in mock_storage["points"]:
                point = mock_storage["points"][point_id]
                if isinstance(point, qdrant_models.PointStruct):
                    # Merge payload
                    existing_payload = dict(point.payload or {})
                    existing_payload.update(payload)
                    point.payload = existing_payload

    mock_client.upsert = mock_upsert
    mock_client.search = mock_search
    mock_client.recommend = mock_recommend
    mock_client.delete = mock_delete
    mock_client.retrieve = mock_retrieve
    mock_client.count = mock_count
    mock_client.scroll = mock_scroll
    mock_client.set_payload = mock_set_payload
    mock_client._storage = mock_storage

    return mock_client


@pytest.fixture
def mock_sqlite_manager():
    """Mock SQLite database manager."""
    from datetime import datetime

    mock_manager = MagicMock()

    # Mock storage
    storage = {
        "settings": {},
        "watched_folders": [],
        "file_sync_status": {},
        "backup_log": [],
        "agent_sessions": {},
        "mcp_server_configs": {},
        "agent_scheduled_tasks": {},
        "agent_webhooks": {},
        "users": {},
        "refresh_tokens": {},
        "password_reset_tokens": {},
    }

    async def mock_execute(query, params=None):
        normalized_query = " ".join(query.lower().split())
        params = params or ()

        if "insert into users" in normalized_query:
            # Auth service INSERT hardcodes is_active=1 and passes 7 params.
            # Some callers may pass 8 (explicit is_active) — accept both.
            if len(params) == 7:
                user_id, email, username, display_name, hashed_password, created_at, updated_at = params
                is_active = 1
            else:
                user_id, email, username, display_name, hashed_password, is_active, created_at, updated_at = params
            storage["users"][user_id] = {
                "id": user_id,
                "email": email,
                "username": username,
                "display_name": display_name,
                "hashed_password": hashed_password,
                "is_active": bool(is_active),
                "created_at": created_at,
                "updated_at": updated_at,
            }
            return MagicMock(lastrowid=1, rowcount=1)

        if "insert into refresh_tokens" in normalized_query:
            token_id, user_id, token_hash, expires_at, created_at = params
            storage["refresh_tokens"][token_id] = {
                "id": token_id,
                "user_id": user_id,
                "token_hash": token_hash,
                "expires_at": expires_at,
                "created_at": created_at,
            }
            return MagicMock(lastrowid=1, rowcount=1)

        if "delete from refresh_tokens where id = ?" in normalized_query:
            token_id = params[0]
            deleted = 1 if storage["refresh_tokens"].pop(token_id, None) else 0
            return MagicMock(lastrowid=1, rowcount=deleted)

        if "insert into password_reset_tokens" in normalized_query:
            token_id, user_id, token_hash, expires_at, created_at = params
            storage["password_reset_tokens"][token_id] = {
                "id": token_id,
                "user_id": user_id,
                "token_hash": token_hash,
                "expires_at": expires_at,
                "created_at": created_at,
                "used": 0,
            }
            return MagicMock(lastrowid=1, rowcount=1)

        if "update users set hashed_password = ?, updated_at = ? where id = ?" in normalized_query:
            hashed_password, updated_at, user_id = params
            user = storage["users"].get(user_id)
            if not user:
                return MagicMock(lastrowid=1, rowcount=0)
            user["hashed_password"] = hashed_password
            user["updated_at"] = updated_at
            return MagicMock(lastrowid=1, rowcount=1)

        if "update password_reset_tokens set used = 1 where id = ?" in normalized_query:
            token_id = params[0]
            token = storage["password_reset_tokens"].get(token_id)
            if not token:
                return MagicMock(lastrowid=1, rowcount=0)
            token["used"] = 1
            return MagicMock(lastrowid=1, rowcount=1)

        return MagicMock(lastrowid=1, rowcount=1)

    async def mock_executemany(query, params):
        return MagicMock(rowcount=len(params) if params else 0)

    async def mock_fetchone(query, params=None):
        normalized_query = " ".join(query.lower().split())
        params = params or ()

        if "from users where email = ? or username = ?" in normalized_query:
            email, username = params
            for user in storage["users"].values():
                if user["email"] == email or user["username"] == username:
                    return {
                        "id": user["id"],
                        "email": user["email"],
                        "username": user["username"],
                    }
            return None

        if "select * from users where email = ? and is_active = 1" in normalized_query:
            email = params[0]
            for user in storage["users"].values():
                if user["email"] == email and user["is_active"]:
                    return dict(user)
            return None

        if "from users where id = ?" in normalized_query:
            user_id = params[0]
            user = storage["users"].get(user_id)
            if not user:
                return None
            return {
                "id": user["id"],
                "email": user["email"],
                "username": user["username"],
                "display_name": user["display_name"],
                "is_active": user["is_active"],
                "created_at": user["created_at"],
                "updated_at": user["updated_at"],
            }

        if "select id from users where email = ? and is_active = 1" in normalized_query:
            email = params[0]
            for user in storage["users"].values():
                if user["email"] == email and user["is_active"]:
                    return {"id": user["id"]}
            return None

        return None

    async def mock_fetchall(query, params=None):
        normalized_query = " ".join(query.lower().split())
        params = params or ()

        if "select * from refresh_tokens" in normalized_query:
            user_id = params[0]
            expires_after = params[1] if len(params) > 1 else None
            rows = []
            for token in storage["refresh_tokens"].values():
                if token["user_id"] != user_id:
                    continue
                if expires_after is not None and token["expires_at"] <= expires_after:
                    continue
                rows.append(dict(token))
            rows.sort(key=lambda token: token["created_at"], reverse=True)
            return rows

        if "from password_reset_tokens prt join users u on u.id = prt.user_id" in normalized_query:
            not_expired_after = params[0] if params else datetime.utcnow()
            rows = []
            for token in storage["password_reset_tokens"].values():
                user = storage["users"].get(token["user_id"])
                if not user or token["used"] != 0 or token["expires_at"] <= not_expired_after:
                    continue
                rows.append({**dict(token), "user_id": user["id"], "email": user["email"]})
            return rows

        return []

    async def mock_upsert_setting(key, value):
        storage["settings"][key] = value

    async def mock_get_setting(key, default=None):
        return storage["settings"].get(key, default)

    async def mock_list_mcp_server_configs():
        return list(storage["mcp_server_configs"].values())

    async def mock_upsert_mcp_server_config(config):
        storage["mcp_server_configs"][config["name"]] = dict(config)

    async def mock_delete_mcp_server_config(name):
        storage["mcp_server_configs"].pop(name, None)

    async def mock_create_agent_scheduled_task(payload):
        storage["agent_scheduled_tasks"][payload["id"]] = dict(payload)

    async def mock_list_agent_scheduled_tasks(agent_id=None):
        rows = list(storage["agent_scheduled_tasks"].values())
        if agent_id:
            rows = [row for row in rows if row["agent_id"] == agent_id]
        return rows

    async def mock_get_agent_scheduled_task(task_id):
        return storage["agent_scheduled_tasks"].get(task_id)

    async def mock_update_agent_scheduled_task_run(task_id, *, last_run=None, next_run=None):
        if task_id in storage["agent_scheduled_tasks"]:
            storage["agent_scheduled_tasks"][task_id]["last_run"] = last_run
            storage["agent_scheduled_tasks"][task_id]["next_run"] = next_run

    async def mock_delete_agent_scheduled_task(task_id):
        storage["agent_scheduled_tasks"].pop(task_id, None)

    async def mock_create_agent_webhook(payload):
        storage["agent_webhooks"][payload["id"]] = dict(payload)

    async def mock_list_agent_webhooks(agent_id=None):
        rows = list(storage["agent_webhooks"].values())
        if agent_id:
            rows = [row for row in rows if row["agent_id"] == agent_id]
        return rows

    async def mock_get_agent_webhook(webhook_id):
        return storage["agent_webhooks"].get(webhook_id)

    async def mock_get_agent_webhook_by_path(url_path):
        for webhook in storage["agent_webhooks"].values():
            if webhook["url_path"] == url_path:
                return webhook
        return None

    async def mock_delete_agent_webhook(webhook_id):
        storage["agent_webhooks"].pop(webhook_id, None)

    mock_manager.execute = mock_execute
    mock_manager.executemany = mock_executemany
    mock_manager.fetchone = mock_fetchone
    mock_manager.fetchall = mock_fetchall
    mock_manager.upsert_setting = mock_upsert_setting
    mock_manager.get_setting = mock_get_setting
    mock_manager.list_mcp_server_configs = mock_list_mcp_server_configs
    mock_manager.upsert_mcp_server_config = mock_upsert_mcp_server_config
    mock_manager.delete_mcp_server_config = mock_delete_mcp_server_config
    mock_manager.create_agent_scheduled_task = mock_create_agent_scheduled_task
    mock_manager.list_agent_scheduled_tasks = mock_list_agent_scheduled_tasks
    mock_manager.get_agent_scheduled_task = mock_get_agent_scheduled_task
    mock_manager.update_agent_scheduled_task_run = mock_update_agent_scheduled_task_run
    mock_manager.delete_agent_scheduled_task = mock_delete_agent_scheduled_task
    mock_manager.create_agent_webhook = mock_create_agent_webhook
    mock_manager.list_agent_webhooks = mock_list_agent_webhooks
    mock_manager.get_agent_webhook = mock_get_agent_webhook
    mock_manager.get_agent_webhook_by_path = mock_get_agent_webhook_by_path
    mock_manager.delete_agent_webhook = mock_delete_agent_webhook
    mock_manager._storage = storage

    return mock_manager


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service with deterministic vectors."""
    from unittest.mock import AsyncMock

    import numpy as np

    mock_service = MagicMock()

    async def mock_embed_text(text):
        # Deterministic 384-dim vector based on text hash
        import hashlib

        hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16)
        vector = np.array([(hash_val + i) % 1000 / 1000 for i in range(384)], dtype=np.float32)
        # Normalize to unit length
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        return vector

    async def mock_embed_texts(texts):
        return [await mock_embed_text(text) for text in texts]

    async def mock_embed_image(image_path):
        # Deterministic 512-dim vector
        import hashlib

        hash_val = int(hashlib.md5(image_path.encode()).hexdigest(), 16)
        vector = np.array([(hash_val + i) % 1000 / 1000 for i in range(512)], dtype=np.float32)
        # Normalize to unit length
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        return vector

    mock_service.embed_text = mock_embed_text
    mock_service.embed_texts = mock_embed_texts
    mock_service.embed_image = mock_embed_image

    return mock_service


@pytest.fixture
def mock_websocket_manager():
    """Mock WebSocket manager."""
    mock_manager = MagicMock()

    mock_connections = {}

    async def mock_connect(websocket, client_id, channel="system"):
        mock_connections[client_id] = websocket

    async def mock_disconnect(client_id):
        mock_connections.pop(client_id, None)

    async def mock_broadcast(message, channel="system"):
        pass  # Mock broadcast

    async def mock_handle_message(websocket, client_id):
        pass  # Mock message handling

    mock_manager.connect = mock_connect
    mock_manager.disconnect = mock_disconnect
    mock_manager.broadcast = mock_broadcast
    mock_manager.handle_message = mock_handle_message
    mock_manager._connections = mock_connections

    return mock_manager


@pytest.fixture
def mock_openclaw_service():
    """Mock OpenClaw service."""
    mock_service = MagicMock()

    async def mock_send_message(agent_name, content, session_id=None):
        return {
            "response": "Mock response",
            "session_id": session_id or "test-session",
            "timestamp": "2024-01-01T00:00:00Z",
        }

    async def mock_assign_task(agent_name, task_id, context):
        return {"status": "assigned", "agent": agent_name, "task_id": task_id}

    async def mock_get_agent_status(agent_name):
        return {
            "name": agent_name,
            "status": "idle",
            "current_task": None,
            "last_seen": "2024-01-01T00:00:00Z",
        }

    mock_service.send_message = mock_send_message
    mock_service.assign_task = mock_assign_task
    mock_service.get_agent_status = mock_get_agent_status

    return mock_service


@pytest.fixture
async def test_client_with_store(mock_async_qdrant_client, mock_embedding_service, mock_sqlite_manager):
    """Create test HTTP client with mocked dependencies, exposing the mock store for pre-population."""
    from app.database.qdrant_client import qdrant_manager
    from app.database.sqlite import sqlite_manager
    from app.main import app
    from app.middleware.auth import get_current_user, get_optional_user
    from app.services.backup import backup_service
    from app.services.context_builder import context_builder
    from app.services.embedding import embedding_service as emb_svc
    from app.services.file_watcher import file_watcher_service
    from app.services.openclaw import openclaw_service

    with ExitStack() as stack:
        stack.enter_context(patch.object(qdrant_manager, "get_async_client", return_value=mock_async_qdrant_client))
        stack.enter_context(patch.object(qdrant_manager, "get_client", return_value=mock_async_qdrant_client))
        stack.enter_context(patch.object(qdrant_manager, "async_client", mock_async_qdrant_client))
        stack.enter_context(patch.object(emb_svc, "embed_text", mock_embedding_service.embed_text))
        stack.enter_context(patch.object(emb_svc, "embed_texts", mock_embedding_service.embed_texts))
        stack.enter_context(patch.object(emb_svc, "embed_image", mock_embedding_service.embed_image))
        stack.enter_context(patch.object(sqlite_manager, "get_setting", mock_sqlite_manager.get_setting))
        stack.enter_context(patch.object(sqlite_manager, "upsert_setting", mock_sqlite_manager.upsert_setting))
        stack.enter_context(
            patch.object(sqlite_manager, "list_mcp_server_configs", mock_sqlite_manager.list_mcp_server_configs)
        )
        stack.enter_context(
            patch.object(sqlite_manager, "upsert_mcp_server_config", mock_sqlite_manager.upsert_mcp_server_config)
        )
        stack.enter_context(
            patch.object(sqlite_manager, "delete_mcp_server_config", mock_sqlite_manager.delete_mcp_server_config)
        )
        stack.enter_context(patch.object(sqlite_manager, "fetchone", mock_sqlite_manager.fetchone))
        stack.enter_context(patch.object(sqlite_manager, "fetchall", mock_sqlite_manager.fetchall))
        stack.enter_context(patch.object(sqlite_manager, "execute", mock_sqlite_manager.execute))
        stack.enter_context(
            patch.object(sqlite_manager, "create_agent_scheduled_task", mock_sqlite_manager.create_agent_scheduled_task)
        )
        stack.enter_context(
            patch.object(sqlite_manager, "list_agent_scheduled_tasks", mock_sqlite_manager.list_agent_scheduled_tasks)
        )
        stack.enter_context(
            patch.object(sqlite_manager, "get_agent_scheduled_task", mock_sqlite_manager.get_agent_scheduled_task)
        )
        stack.enter_context(
            patch.object(
                sqlite_manager, "update_agent_scheduled_task_run", mock_sqlite_manager.update_agent_scheduled_task_run
            )
        )
        stack.enter_context(
            patch.object(sqlite_manager, "delete_agent_scheduled_task", mock_sqlite_manager.delete_agent_scheduled_task)
        )
        stack.enter_context(patch.object(sqlite_manager, "create_agent_webhook", mock_sqlite_manager.create_agent_webhook))
        stack.enter_context(patch.object(sqlite_manager, "list_agent_webhooks", mock_sqlite_manager.list_agent_webhooks))
        stack.enter_context(patch.object(sqlite_manager, "get_agent_webhook", mock_sqlite_manager.get_agent_webhook))
        stack.enter_context(
            patch.object(sqlite_manager, "get_agent_webhook_by_path", mock_sqlite_manager.get_agent_webhook_by_path)
        )
        stack.enter_context(patch.object(sqlite_manager, "delete_agent_webhook", mock_sqlite_manager.delete_agent_webhook))
        stack.enter_context(
            patch.object(
                openclaw_service, "send_message", AsyncMock(return_value={"content": "Mock response", "metadata": {}})
            )
        )
        stack.enter_context(patch.object(openclaw_service, "assign_task", AsyncMock(return_value={"status": "assigned"})))
        stack.enter_context(patch.object(openclaw_service, "get_agent_status", AsyncMock(return_value={"status": "idle"})))
        stack.enter_context(patch.object(context_builder, "build_task_context", AsyncMock(return_value={})))
        stack.enter_context(patch.object(file_watcher_service, "process_file", AsyncMock(return_value=None)))
        stack.enter_context(patch.object(file_watcher_service, "add_folder", AsyncMock(return_value=None)))
        stack.enter_context(patch.object(file_watcher_service, "remove_folder", AsyncMock(return_value=None)))
        stack.enter_context(patch.object(backup_service, "run_backup", AsyncMock(return_value=None)))

        from datetime import datetime

        async def fake_current_user():
            return {
                "id": "test-user-id",
                "email": "test@example.com",
                "username": "test-user",
                "display_name": "Test User",
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }

        limiter_enabled = getattr(app.state.limiter, "enabled", True)
        login_limiter_enabled = getattr(
            getattr(app.state, "login_limiter", None), "enabled", True
        )
        app.state.limiter.enabled = False
        if hasattr(app.state, "login_limiter"):
            app.state.login_limiter.enabled = False
        app.state.auth_enforcement_enabled = False
        app.dependency_overrides[get_current_user] = fake_current_user
        app.dependency_overrides[get_optional_user] = fake_current_user

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, mock_async_qdrant_client._storage
        app.state.limiter.enabled = limiter_enabled
        if hasattr(app.state, "login_limiter"):
            app.state.login_limiter.enabled = login_limiter_enabled
        app.state.auth_enforcement_enabled = True
        app.dependency_overrides.clear()


@pytest.fixture
async def test_client(mock_async_qdrant_client, mock_embedding_service, mock_sqlite_manager):
    """Create test HTTP client with mocked dependencies."""
    from app.database.qdrant_client import qdrant_manager
    from app.database.sqlite import sqlite_manager
    from app.main import app
    from app.middleware.auth import get_current_user, get_optional_user
    from app.services.backup import backup_service
    from app.services.context_builder import context_builder
    from app.services.embedding import embedding_service as emb_svc
    from app.services.file_watcher import file_watcher_service
    from app.services.openclaw import openclaw_service

    with ExitStack() as stack:
        stack.enter_context(patch.object(qdrant_manager, "get_async_client", return_value=mock_async_qdrant_client))
        stack.enter_context(patch.object(qdrant_manager, "get_client", return_value=mock_async_qdrant_client))
        stack.enter_context(patch.object(qdrant_manager, "async_client", mock_async_qdrant_client))
        stack.enter_context(patch.object(emb_svc, "embed_text", mock_embedding_service.embed_text))
        stack.enter_context(patch.object(emb_svc, "embed_texts", mock_embedding_service.embed_texts))
        stack.enter_context(patch.object(emb_svc, "embed_image", mock_embedding_service.embed_image))
        stack.enter_context(patch.object(sqlite_manager, "get_setting", mock_sqlite_manager.get_setting))
        stack.enter_context(patch.object(sqlite_manager, "upsert_setting", mock_sqlite_manager.upsert_setting))
        stack.enter_context(
            patch.object(sqlite_manager, "list_mcp_server_configs", mock_sqlite_manager.list_mcp_server_configs)
        )
        stack.enter_context(
            patch.object(sqlite_manager, "upsert_mcp_server_config", mock_sqlite_manager.upsert_mcp_server_config)
        )
        stack.enter_context(
            patch.object(sqlite_manager, "delete_mcp_server_config", mock_sqlite_manager.delete_mcp_server_config)
        )
        stack.enter_context(patch.object(sqlite_manager, "fetchone", mock_sqlite_manager.fetchone))
        stack.enter_context(patch.object(sqlite_manager, "fetchall", mock_sqlite_manager.fetchall))
        stack.enter_context(patch.object(sqlite_manager, "execute", mock_sqlite_manager.execute))
        stack.enter_context(
            patch.object(sqlite_manager, "create_agent_scheduled_task", mock_sqlite_manager.create_agent_scheduled_task)
        )
        stack.enter_context(
            patch.object(sqlite_manager, "list_agent_scheduled_tasks", mock_sqlite_manager.list_agent_scheduled_tasks)
        )
        stack.enter_context(
            patch.object(sqlite_manager, "get_agent_scheduled_task", mock_sqlite_manager.get_agent_scheduled_task)
        )
        stack.enter_context(
            patch.object(
                sqlite_manager, "update_agent_scheduled_task_run", mock_sqlite_manager.update_agent_scheduled_task_run
            )
        )
        stack.enter_context(
            patch.object(sqlite_manager, "delete_agent_scheduled_task", mock_sqlite_manager.delete_agent_scheduled_task)
        )
        stack.enter_context(patch.object(sqlite_manager, "create_agent_webhook", mock_sqlite_manager.create_agent_webhook))
        stack.enter_context(patch.object(sqlite_manager, "list_agent_webhooks", mock_sqlite_manager.list_agent_webhooks))
        stack.enter_context(patch.object(sqlite_manager, "get_agent_webhook", mock_sqlite_manager.get_agent_webhook))
        stack.enter_context(
            patch.object(sqlite_manager, "get_agent_webhook_by_path", mock_sqlite_manager.get_agent_webhook_by_path)
        )
        stack.enter_context(patch.object(sqlite_manager, "delete_agent_webhook", mock_sqlite_manager.delete_agent_webhook))
        stack.enter_context(
            patch.object(
                openclaw_service, "send_message", AsyncMock(return_value={"content": "Mock response", "metadata": {}})
            )
        )
        stack.enter_context(patch.object(openclaw_service, "assign_task", AsyncMock(return_value={"status": "assigned"})))
        stack.enter_context(patch.object(openclaw_service, "get_agent_status", AsyncMock(return_value={"status": "idle"})))
        stack.enter_context(patch.object(context_builder, "build_task_context", AsyncMock(return_value={})))
        stack.enter_context(patch.object(file_watcher_service, "process_file", AsyncMock(return_value=None)))
        stack.enter_context(patch.object(file_watcher_service, "add_folder", AsyncMock(return_value=None)))
        stack.enter_context(patch.object(file_watcher_service, "remove_folder", AsyncMock(return_value=None)))
        stack.enter_context(patch.object(backup_service, "run_backup", AsyncMock(return_value=None)))

        from datetime import datetime

        async def fake_current_user():
            return {
                "id": "test-user-id",
                "email": "test@example.com",
                "username": "test-user",
                "display_name": "Test User",
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }

        limiter_enabled = getattr(app.state.limiter, "enabled", True)
        login_limiter_enabled = getattr(
            getattr(app.state, "login_limiter", None), "enabled", True
        )
        app.state.limiter.enabled = False
        if hasattr(app.state, "login_limiter"):
            app.state.login_limiter.enabled = False
        app.state.auth_enforcement_enabled = False
        app.dependency_overrides[get_current_user] = fake_current_user
        app.dependency_overrides[get_optional_user] = fake_current_user

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
        app.state.limiter.enabled = limiter_enabled
        if hasattr(app.state, "login_limiter"):
            app.state.login_limiter.enabled = login_limiter_enabled
        app.state.auth_enforcement_enabled = True
        app.dependency_overrides.clear()


@pytest.fixture
async def authenticated_client(test_client):
    """Create a test client authenticated via register and login."""
    register_response = await test_client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "testpass123",
        },
    )
    assert register_response.status_code == 201, register_response.text

    login_response = await test_client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "testpass123",
        },
    )
    assert login_response.status_code == 200, login_response.text

    token = login_response.json()["access_token"]
    test_client.headers["Authorization"] = f"Bearer {token}"
    yield test_client
    test_client.headers.pop("Authorization", None)


@pytest.fixture
async def authenticated_client_with_store(test_client_with_store):
    """Create an authenticated client while keeping access to the backing store."""
    client, store = test_client_with_store

    register_response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "testpass123",
        },
    )
    assert register_response.status_code == 201, register_response.text

    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "testpass123",
        },
    )
    assert login_response.status_code == 200, login_response.text

    token = login_response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    yield client, store
    client.headers.pop("Authorization", None)


@pytest.fixture
def sample_object_data():
    """Sample object data for testing."""
    return {
        "id": "test-object-1",
        "payload": {
            "title": "Test Object",
            "content": "Test content",
            "object_type": "note",
            "tags": ["test", "sample"],
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        },
        "vector": [0.1] * 384,
    }


@pytest.fixture
def sample_block_data():
    """Sample block data for testing."""
    return {
        "id": "test-block-1",
        "payload": {
            "object_id": "test-object-1",
            "content": "Test block content",
            "block_type": "text",
            "order": 0,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        },
        "vector": [0.1] * 384,
    }


@pytest.fixture
def sample_task_data():
    """Sample task data for testing."""
    return {
        "id": "test-task-1",
        "payload": {
            "title": "Test Task",
            "description": "Test task description",
            "status": "todo",
            "priority": "medium",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        },
        "vector": [0.1] * 384,
    }


@pytest.fixture
def sample_relation_data():
    """Sample relation data for testing."""
    return {
        "id": "test-relation-1",
        "payload": {
            "source_type": "object",
            "source_id": "test-object-1",
            "target_type": "object",
            "target_id": "test-object-2",
            "relation_type": "references",
            "created_at": "2024-01-01T00:00:00Z",
        },
        "vector": [0.1] * 384,
    }
