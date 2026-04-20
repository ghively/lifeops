"""Collaboration Router — REST + WebSocket endpoints for collaboration features."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect

from app.middleware.auth import authenticate_websocket, get_current_user
from app.middleware.rate_limit import read_rate_limit
from app.services.collaboration import (
    MSG_AWARENESS,
    MSG_CURSOR,
    MSG_ERROR,
    MSG_JOIN,
    MSG_LEAVE,
    MSG_OP,
    MSG_SNAPSHOT_REQ,
    CROperation,
    collaboration_manager,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# WebSocket endpoint for real-time collaboration
# ---------------------------------------------------------------------------


@router.websocket("/ws/{object_id}")
async def collaboration_ws(websocket: WebSocket, object_id: str):
    """WebSocket endpoint for collaborative editing of a document.

    Protocol (all JSON):
      Client -> Server:
        { type: "collab.join",   data: { user_id, display_name } }
        { type: "collab.op",     data: { op_id, block_id, type, path, offset, content, length } }
        { type: "collab.cursor", data: { cursor?, selection? } }
        { type: "collab.awareness", data: { ... } }
        { type: "collab.snapshot_req", data: {} }
        { type: "collab.leave",  data: {} }

      Server -> Client:
        { type: "collab.welcome",  data: { object_id, user_id, color, users[], pending_ops[] } }
        { type: "collab.user_joined", data: { user_id, display_name, color } }
        { type: "collab.user_left",   data: { user_id } }
        { type: "collab.op_broadcast", data: { op_id, block_id, type, path, offset, content, length, lamport_ts, user_id } }
        { type: "collab.cursor_broadcast", data: { user_id, cursor?, selection? } }
        { type: "collab.awareness_broadcast", data: { user_id, state } }
        { type: "collab.ack", data: { op_id, lamport_ts } }
        { type: "collab.snapshot", data: { ... } }
        { type: "collab.error", data: { message } }
    """
    try:
        authenticated_user = await authenticate_websocket(websocket)
    except HTTPException:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    user_id: str | None = None
    default_display_name = (
        authenticated_user.get("display_name")
        or authenticated_user.get("username")
        or authenticated_user.get("email")
        or "Anonymous"
    )

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": MSG_ERROR, "data": {"message": "Invalid JSON"}})
                continue

            msg_type = msg.get("type", "")
            data = msg.get("data", {})

            # --- JOIN ---
            if msg_type == MSG_JOIN:
                user_id = authenticated_user["id"]
                display_name = data.get("display_name") or default_display_name
                await collaboration_manager.join_room(object_id, user_id, display_name, websocket)

            # --- LEAVE ---
            elif msg_type == MSG_LEAVE:
                if user_id:
                    await collaboration_manager.leave_room(object_id, user_id)
                    user_id = None
                break  # Close connection

            # --- OPERATION ---
            elif msg_type == MSG_OP:
                if not user_id:
                    await websocket.send_json({"type": MSG_ERROR, "data": {"message": "Not joined"}})
                    continue
                room = collaboration_manager.get_room(object_id)
                if not room:
                    await websocket.send_json({"type": MSG_ERROR, "data": {"message": "Room not found"}})
                    continue
                op = CROperation(
                    op_id=data.get("op_id", ""),
                    object_id=object_id,
                    block_id=data.get("block_id", ""),
                    type=data.get("type", "replace"),
                    path=data.get("path", []),
                    offset=data.get("offset", 0),
                    content=data.get("content", ""),
                    length=data.get("length", 0),
                    user_id=user_id,
                )
                await room.handle_operation(op)

            # --- CURSOR ---
            elif msg_type == MSG_CURSOR:
                if not user_id:
                    continue
                room = collaboration_manager.get_room(object_id)
                if not room:
                    continue
                await room.handle_cursor(
                    user_id,
                    data.get("cursor"),
                    data.get("selection"),
                )

            # --- AWARENESS ---
            elif msg_type == MSG_AWARENESS:
                if not user_id:
                    continue
                room = collaboration_manager.get_room(object_id)
                if not room:
                    continue
                await room.handle_awareness(user_id, data)

            # --- SNAPSHOT REQUEST ---
            elif msg_type == MSG_SNAPSHOT_REQ:
                room = collaboration_manager.get_room(object_id)
                if room:
                    await websocket.send_json(
                        {
                            "type": "collab.snapshot",
                            "data": room.get_snapshot(),
                        }
                    )

            else:
                await websocket.send_json({"type": MSG_ERROR, "data": {"message": f"Unknown message type: {msg_type}"}})

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.error("Collaboration WS error for room %s", object_id, exc_info=True)
    finally:
        if user_id:
            await collaboration_manager.leave_room(object_id, user_id)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@router.get("/{object_id}/presence")
@read_rate_limit
async def get_presence(object_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Get current users editing a document."""
    users = collaboration_manager.get_presence(object_id)
    return {"object_id": object_id, "users": users, "count": len(users)}


@router.get("/{object_id}/snapshot")
@read_rate_limit
async def get_snapshot(object_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Get collaboration room snapshot."""
    room = collaboration_manager.get_room(object_id)
    if not room:
        raise HTTPException(status_code=404, detail="No active collaboration session for this document")
    return room.get_snapshot()


@router.get("/stats/rooms")
@read_rate_limit
async def get_stats(request: Request, current_user: dict = Depends(get_current_user)):
    """Get collaboration stats across all rooms."""
    rooms = collaboration_manager.rooms
    return {
        "active_rooms": len(rooms),
        "total_users": sum(r.user_count for r in rooms.values()),
        "rooms": [
            {
                "object_id": oid,
                "user_count": r.user_count,
                "last_activity": r.last_activity,
            }
            for oid, r in rooms.items()
        ],
    }
