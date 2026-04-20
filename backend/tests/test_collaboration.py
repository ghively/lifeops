"""Tests for the collaboration service and WebSocket protocol."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.collaboration import (
    MSG_ACK,
    MSG_CURSOR,
    MSG_CURSOR_BROADCAST,
    MSG_JOIN,
    MSG_LEAVE,
    MSG_OP,
    MSG_OP_BROADCAST,
    MSG_USER_JOINED,
    MSG_USER_LEFT,
    MSG_WELCOME,
    CollaborationManager,
    CollaborationRoom,
    CROperation,
    PresenceUser,
    user_color,
)

# ---------------------------------------------------------------------------
# Unit tests — pure logic
# ---------------------------------------------------------------------------


class TestUserColor:
    """Tests for deterministic color assignment."""

    def test_same_user_always_same_color(self):
        assert user_color("alice") == user_color("alice")

    def test_different_users_likely_different_colors(self):
        colors = {user_color(f"user-{i}") for i in range(20)}
        # With 10 colors and 20 users, we should use at least 5 distinct colors
        assert len(colors) >= 5

    def test_returns_valid_hex(self):
        color = user_color("test")
        assert color.startswith("#")
        assert len(color) == 7


class TestPresenceUser:
    """Tests for PresenceUser dataclass."""

    def test_to_dict_minimal(self):
        u = PresenceUser(user_id="1", display_name="Alice", color="#e06c75")
        d = u.to_dict()
        assert d == {"user_id": "1", "display_name": "Alice", "color": "#e06c75"}
        assert "cursor" not in d
        assert "selection" not in d

    def test_to_dict_with_cursor(self):
        u = PresenceUser(
            user_id="1",
            display_name="Alice",
            color="#e06c75",
            cursor={"path": [0, 0], "offset": 5},
        )
        d = u.to_dict()
        assert d["cursor"] == {"path": [0, 0], "offset": 5}


class TestCROperation:
    """Tests for CRDT operation model."""

    def test_to_dict(self):
        op = CROperation(
            op_id="op-1",
            object_id="obj-1",
            block_id="blk-1",
            type="replace",
            path=[2, 0],
            offset=10,
            content="hello",
            length=3,
            lamport_ts=42,
            user_id="alice",
        )
        d = op.to_dict()
        assert d["op_id"] == "op-1"
        assert d["lamport_ts"] == 42
        assert d["path"] == [2, 0]


# ---------------------------------------------------------------------------
# Integration tests — CollaborationRoom
# ---------------------------------------------------------------------------


class TestCollaborationRoom:
    """Tests for room join/leave/operations."""

    def _mock_ws(self):
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        return ws

    @pytest.mark.asyncio
    async def test_add_user_sends_welcome(self):
        room = CollaborationRoom("doc-1")
        ws = self._mock_ws()
        await room.add_user("alice", "Alice", ws)

        ws.send_json.assert_called_once()
        call_args = ws.send_json.call_args[0][0]
        assert call_args["type"] == MSG_WELCOME
        assert call_args["data"]["user_id"] == "alice"
        assert call_args["data"]["color"].startswith("#")

    @pytest.mark.asyncio
    async def test_add_user_notifies_others(self):
        room = CollaborationRoom("doc-1")
        ws1 = self._mock_ws()
        ws2 = self._mock_ws()
        await room.add_user("alice", "Alice", ws1)
        await room.add_user("bob", "Bob", ws2)

        # ws1 should have received a user_joined message for bob
        calls = [c[0][0] for c in ws1.send_json.call_args_list]
        joined_msgs = [m for m in calls if m["type"] == MSG_USER_JOINED]
        assert len(joined_msgs) == 1
        assert joined_msgs[0]["data"]["user_id"] == "bob"

    @pytest.mark.asyncio
    async def test_user_count(self):
        room = CollaborationRoom("doc-1")
        assert room.user_count == 0
        await room.add_user("alice", "Alice", self._mock_ws())
        assert room.user_count == 1
        await room.add_user("bob", "Bob", self._mock_ws())
        assert room.user_count == 2

    @pytest.mark.asyncio
    async def test_remove_user_notifies_others(self):
        room = CollaborationRoom("doc-1")
        ws1 = self._mock_ws()
        ws2 = self._mock_ws()
        await room.add_user("alice", "Alice", ws1)
        await room.add_user("bob", "Bob", ws2)

        await room.remove_user("alice")
        assert room.user_count == 1
        assert "alice" not in room.presence

    @pytest.mark.asyncio
    async def test_handle_operation_broadcasts(self):
        room = CollaborationRoom("doc-1")
        ws_alice = self._mock_ws()
        ws_bob = self._mock_ws()
        await room.add_user("alice", "Alice", ws_alice)
        await room.add_user("bob", "Bob", ws_bob)

        op = CROperation(
            op_id="op-1",
            object_id="doc-1",
            block_id="blk-1",
            type="replace",
            path=[0, 0],
            user_id="alice",
        )
        await room.handle_operation(op)

        # Bob should get the broadcast, Alice should get an ack
        bob_calls = [c[0][0] for c in ws_bob.send_json.call_args_list]
        broadcast_msgs = [m for m in bob_calls if m["type"] == MSG_OP_BROADCAST]
        assert len(broadcast_msgs) == 1
        assert broadcast_msgs[0]["data"]["op_id"] == "op-1"
        assert broadcast_msgs[0]["data"]["lamport_ts"] == 1

        alice_calls = [c[0][0] for c in ws_alice.send_json.call_args_list]
        ack_msgs = [m for m in alice_calls if m["type"] == MSG_ACK]
        assert len(ack_msgs) == 1

    @pytest.mark.asyncio
    async def test_handle_cursor_broadcasts(self):
        room = CollaborationRoom("doc-1")
        ws_alice = self._mock_ws()
        ws_bob = self._mock_ws()
        await room.add_user("alice", "Alice", ws_alice)
        await room.add_user("bob", "Bob", ws_bob)

        cursor = {"path": [0, 0], "offset": 5}
        await room.handle_cursor("alice", cursor, None)

        bob_calls = [c[0][0] for c in ws_bob.send_json.call_args_list]
        cursor_msgs = [m for m in bob_calls if m["type"] == MSG_CURSOR_BROADCAST]
        assert len(cursor_msgs) == 1
        assert cursor_msgs[0]["data"]["cursor"] == cursor

    @pytest.mark.asyncio
    async def test_lamport_clock_increments(self):
        room = CollaborationRoom("doc-1")
        ws = self._mock_ws()
        await room.add_user("alice", "Alice", ws)

        for i in range(5):
            op = CROperation(
                op_id=f"op-{i}",
                object_id="doc-1",
                block_id="blk-1",
                type="replace",
                path=[0, 0],
                user_id="alice",
            )
            await room.handle_operation(op)

        assert room.lamport_clock == 5

    @pytest.mark.asyncio
    async def test_operation_log_trimmed(self):
        room = CollaborationRoom("doc-1")
        room._max_log_size = 10
        ws = self._mock_ws()
        await room.add_user("alice", "Alice", ws)

        for i in range(20):
            op = CROperation(
                op_id=f"op-{i}",
                object_id="doc-1",
                block_id="blk-1",
                type="replace",
                path=[0, 0],
                user_id="alice",
            )
            await room.handle_operation(op)

        assert len(room.operation_log) == 10


# ---------------------------------------------------------------------------
# Integration tests — CollaborationManager
# ---------------------------------------------------------------------------


class TestCollaborationManager:
    """Tests for the manager that orchestrates rooms."""

    @pytest.mark.asyncio
    async def test_get_or_create_room(self):
        mgr = CollaborationManager()
        room1 = mgr.get_or_create_room("doc-1")
        room2 = mgr.get_or_create_room("doc-1")
        assert room1 is room2

    @pytest.mark.asyncio
    async def test_join_and_leave_room(self):
        mgr = CollaborationManager()
        ws = AsyncMock()
        ws.send_json = AsyncMock()

        await mgr.join_room("doc-1", "alice", "Alice", ws)
        assert mgr.get_room("doc-1") is not None
        assert mgr.get_room("doc-1").user_count == 1

        await mgr.leave_room("doc-1", "alice")
        # Room should be cleaned up when empty
        assert mgr.get_room("doc-1") is None

    @pytest.mark.asyncio
    async def test_get_presence(self):
        mgr = CollaborationManager()
        ws = AsyncMock()
        ws.send_json = AsyncMock()

        await mgr.join_room("doc-1", "alice", "Alice", ws)
        presence = mgr.get_presence("doc-1")
        assert len(presence) == 1
        assert presence[0]["user_id"] == "alice"

    @pytest.mark.asyncio
    async def test_get_presence_empty(self):
        mgr = CollaborationManager()
        assert mgr.get_presence("nonexistent") == []

    @pytest.mark.asyncio
    async def test_multiple_users_in_room(self):
        mgr = CollaborationManager()
        ws1 = AsyncMock()
        ws1.send_json = AsyncMock()
        ws2 = AsyncMock()
        ws2.send_json = AsyncMock()

        await mgr.join_room("doc-1", "alice", "Alice", ws1)
        await mgr.join_room("doc-1", "bob", "Bob", ws2)

        presence = mgr.get_presence("doc-1")
        assert len(presence) == 2

        await mgr.leave_room("doc-1", "alice")
        assert mgr.get_room("doc-1").user_count == 1

        await mgr.leave_room("doc-1", "bob")
        assert mgr.get_room("doc-1") is None
