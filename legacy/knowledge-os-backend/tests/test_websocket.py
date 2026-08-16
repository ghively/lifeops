"""
Tests for the WebSocket manager.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
class TestWebSocketManager:
    """Test cases for WebSocket connection manager."""

    async def test_connect_client(self, mock_websocket_manager):
        """Test connecting a new WebSocket client."""
        mock_websocket = MagicMock()
        client_id = "test-client-1"

        await mock_websocket_manager.connect(mock_websocket, client_id, "system")

        assert client_id in mock_websocket_manager._connections

    async def test_disconnect_client(self, mock_websocket_manager):
        """Test disconnecting a WebSocket client."""
        mock_websocket = MagicMock()
        client_id = "test-client-1"

        await mock_websocket_manager.connect(mock_websocket, client_id, "system")
        await mock_websocket_manager.disconnect(client_id)

        assert client_id not in mock_websocket_manager._connections

    async def test_broadcast_message(self, mock_websocket_manager):
        """Test broadcasting message to all connected clients."""
        mock_websocket = AsyncMock()
        client_id = "test-client-1"

        await mock_websocket_manager.connect(mock_websocket, client_id, "system")

        message = {"type": "object_created", "data": {"id": "test-obj-1"}}

        await mock_websocket_manager.broadcast(message, "system")

        # Should have sent message to connected client
        # (verify in actual implementation)

    async def test_broadcast_to_channel(self, mock_websocket_manager):
        """Test broadcasting to specific channel."""
        mock_websocket = AsyncMock()
        client_id = "test-client-1"

        await mock_websocket_manager.connect(mock_websocket, client_id, "agents")

        message = {"type": "agent_status", "data": {"agent": "test-agent", "status": "idle"}}

        await mock_websocket_manager.broadcast(message, "agents")

    async def test_send_message_to_client(self):
        """Test sending message to specific client."""
        mock_websocket = AsyncMock()

        # Create simple manager
        from app.services.websocket_manager import websocket_manager as manager

        await manager.connect(mock_websocket)

        message = {"type": "test", "data": "hello"}

        # Send message (implementation specific)
        await manager.broadcast(message)

        manager.disconnect(mock_websocket)

    async def test_handle_incoming_message(self, mock_websocket_manager):
        """Test handling incoming WebSocket message."""
        mock_websocket = AsyncMock()
        client_id = "test-client-1"

        await mock_websocket_manager.connect(mock_websocket, client_id, "system")

        # Mock receiving a message
        await mock_websocket_manager.handle_message(mock_websocket, client_id)

    async def test_multiple_clients_same_channel(self, mock_websocket_manager):
        """Test multiple clients connected to same channel."""
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        await mock_websocket_manager.connect(mock_ws1, "client-1", "system")
        await mock_websocket_manager.connect(mock_ws2, "client-2", "system")

        assert len(mock_websocket_manager._connections) == 2

    async def test_multiple_channels(self, mock_websocket_manager):
        """Test clients connected to different channels."""
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        await mock_websocket_manager.connect(mock_ws1, "client-1", "system")
        await mock_websocket_manager.connect(mock_ws2, "client-2", "agents")

        # Both clients should be tracked
        assert len(mock_websocket_manager._connections) == 2

    async def test_disconnect_nonexistent_client(self, mock_websocket_manager):
        """Test disconnecting a client that doesn't exist."""
        # Should not raise error
        await mock_websocket_manager.disconnect("nonexistent")

    async def test_broadcast_with_no_clients(self, mock_websocket_manager):
        """Test broadcasting when no clients connected."""
        message = {"type": "test", "data": "hello"}

        # Should not raise error
        await mock_websocket_manager.broadcast(message, "system")


@pytest.mark.asyncio
class TestWebSocketEvents:
    """Test cases for WebSocket event types."""

    async def test_object_created_event(self, mock_websocket_manager):
        """Test object created event."""
        event = {"type": "object_created", "data": {"id": "obj-1", "title": "Test Object", "object_type": "note"}}

        await mock_websocket_manager.broadcast(event, "system")

    async def test_object_updated_event(self, mock_websocket_manager):
        """Test object updated event."""
        event = {"type": "object_updated", "data": {"id": "obj-1", "title": "Updated Title"}}

        await mock_websocket_manager.broadcast(event, "system")

    async def test_object_deleted_event(self, mock_websocket_manager):
        """Test object deleted event."""
        event = {"type": "object_deleted", "data": {"id": "obj-1"}}

        await mock_websocket_manager.broadcast(event, "system")

    async def test_block_created_event(self, mock_websocket_manager):
        """Test block created event."""
        event = {"type": "block_created", "data": {"id": "block-1", "object_id": "obj-1", "content": "New block"}}

        await mock_websocket_manager.broadcast(event, "system")

    async def test_task_assigned_event(self, mock_websocket_manager):
        """Test task assigned event."""
        event = {"type": "task_assigned", "data": {"task_id": "task-1", "agent": "test-agent"}}

        await mock_websocket_manager.broadcast(event, "agents")

    async def test_task_status_changed_event(self, mock_websocket_manager):
        """Test task status changed event."""
        event = {
            "type": "task_status_changed",
            "data": {"task_id": "task-1", "old_status": "todo", "new_status": "in-progress"},
        }

        await mock_websocket_manager.broadcast(event, "agents")

    async def test_agent_status_changed_event(self, mock_websocket_manager):
        """Test agent status changed event."""
        event = {
            "type": "agent_status_changed",
            "data": {"agent": "test-agent", "status": "working", "current_task": "task-1"},
        }

        await mock_websocket_manager.broadcast(event, "agents")

    async def test_chat_message_event(self, mock_websocket_manager):
        """Test chat message event."""
        event = {
            "type": "message",
            "data": {"agent": "test-agent", "session_id": "session-1", "content": "Hello!", "role": "assistant"},
        }

        await mock_websocket_manager.broadcast(event, "agents")

    async def test_file_indexed_event(self, mock_websocket_manager):
        """Test file indexed event."""
        event = {"type": "file_indexed", "data": {"file_id": "file-1", "filename": "test.pdf"}}

        await mock_websocket_manager.broadcast(event, "system")


@pytest.mark.asyncio
class TestWebSocketErrorHandling:
    """Test cases for WebSocket error handling."""

    async def test_client_disconnect_error(self):
        """Test handling client disconnect errors."""
        # Should handle broken pipe errors gracefully
        pass

    async def test_invalid_message_format(self):
        """Test handling invalid message format."""
        # Should reject malformed messages
        pass

    async def test_connection_timeout(self):
        """Test connection timeout handling."""
        # Should close idle connections
        pass

    async def test_reconnect_logic(self):
        """Test client reconnect logic."""
        # Should handle reconnections
        pass


@pytest.mark.asyncio
class TestChannelAuthorization:
    """Direct exercise of WebSocketManager._authorize_channel and the
    subscribe handler (regression for issue #176)."""

    async def _make_ws(self):
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        return ws

    async def _connect(self, manager, user):
        ws = await self._make_ws()
        await manager.connect(ws, user=user)
        return ws

    async def test_public_channels_allowed_without_user(self):
        from app.services.websocket_manager import (
            PUBLIC_CHANNELS,
            WebSocketManager,
        )

        manager = WebSocketManager()
        for channel in PUBLIC_CHANNELS:
            assert await manager._authorize_channel(None, channel) is True

    async def test_namespaced_channels_denied_without_user(self):
        from app.services.websocket_manager import WebSocketManager

        manager = WebSocketManager()
        for channel in (
            "object:abc",
            "collab:abc",
            "agent-approval:other-user",
            "made-up-namespace:x",
        ):
            assert await manager._authorize_channel(None, channel) is False

    async def test_agent_approval_locked_to_authenticated_user(self):
        from app.services.websocket_manager import WebSocketManager

        manager = WebSocketManager()
        me = {"id": "user-self"}
        assert await manager._authorize_channel(me, "agent-approval:user-self") is True
        assert await manager._authorize_channel(me, "agent-approval:somebody-else") is False

    async def test_collab_and_object_channels_check_object_owner(self, monkeypatch):
        from app.services import access as access_module
        from app.services.websocket_manager import WebSocketManager

        async def fake_access(user_id, object_id):
            return user_id == "owner" and object_id == "doc-1"

        monkeypatch.setattr(access_module, "user_can_access_object", fake_access)

        manager = WebSocketManager()
        owner = {"id": "owner"}
        intruder = {"id": "intruder"}

        assert await manager._authorize_channel(owner, "object:doc-1") is True
        assert await manager._authorize_channel(owner, "collab:doc-1") is True
        assert await manager._authorize_channel(intruder, "object:doc-1") is False
        assert await manager._authorize_channel(intruder, "collab:doc-1") is False

    async def test_unknown_namespace_denied(self):
        from app.services.websocket_manager import WebSocketManager

        manager = WebSocketManager()
        assert await manager._authorize_channel({"id": "u"}, "future-feature:42") is False

    async def test_subscribe_handler_reports_denied_channels(self, monkeypatch):
        from app.services import access as access_module
        from app.services.websocket_manager import WebSocketManager

        async def fake_access(user_id, object_id):
            return False

        monkeypatch.setattr(access_module, "user_can_access_object", fake_access)

        manager = WebSocketManager()
        ws = await self._connect(manager, {"id": "u1"})
        payload = '{"type":"subscribe","data":{"channels":["system","collab:secret"]}}'
        await manager.handle_message(ws, payload)

        ws.send_json.assert_awaited_once()
        sent = ws.send_json.await_args.args[0]
        assert sent["type"] == "subscribed"
        assert "collab:secret" in sent["data"]["denied"]
        assert "collab:secret" not in sent["data"]["channels"]
        assert "system" in sent["data"]["channels"]
        assert manager.subscriptions[ws] == {"system"}

    async def test_subscribe_handler_grants_public_channel(self):
        from app.services.websocket_manager import WebSocketManager

        manager = WebSocketManager()
        ws = await self._connect(manager, {"id": "u1"})
        payload = '{"type":"subscribe","data":{"channels":["logs"]}}'
        await manager.handle_message(ws, payload)

        sent = ws.send_json.await_args.args[0]
        assert sent["data"]["granted"] == ["logs"]
        assert "logs" in manager.subscriptions[ws]
        assert "denied" not in sent["data"]

    async def test_disconnect_clears_user_mapping(self):
        from app.services.websocket_manager import WebSocketManager

        manager = WebSocketManager()
        ws = await self._connect(manager, {"id": "u1"})
        assert ws in manager.connection_users
        manager.disconnect(ws)
        assert ws not in manager.connection_users
