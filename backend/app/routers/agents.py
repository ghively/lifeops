"""Agents Router - Agent management and chat."""
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.database.qdrant_client import qdrant_manager
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import read_rate_limit, write_rate_limit
from app.database.sqlite import sqlite_manager
from app.services.embedding import embedding_service
from app.services.openclaw import openclaw_service
from app.services.websocket_manager import WebSocketEvents, websocket_manager
from app.utils.time import utc_now_iso

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    content: str
    session_id: Optional[str] = "main"
    related_task: Optional[str] = None


DEFAULT_AGENTS = [
    {"name": "researcher", "description": "Research and information gathering agent", "capabilities": ["search", "summarize", "analyze"]},
    {"name": "writer", "description": "Writing and editing agent", "capabilities": ["write", "edit", "format"]},
]


async def _ensure_agent_objects():
    client = qdrant_manager.get_async_client()
    existing = await client.scroll(
        collection_name="objects",
        scroll_filter={"must": [{"key": "type", "match": {"value": "agent"}}]},
        limit=100,
        with_payload=True,
        with_vectors=False,
    )
    names = {point.payload.get("properties", {}).get("agent_name") or point.payload.get("title") for point in existing[0]}
    for agent in DEFAULT_AGENTS:
        if agent["name"] in names:
            continue
        agent_id = str(uuid.uuid4())
        embedding = await embedding_service.embed_text(agent["description"])
        await client.upsert(
            collection_name="objects",
            points=[{
                "id": agent_id,
                "vector": embedding.tolist(),
                "payload": {
                    "id": agent_id,
                    "type": "agent",
                    "title": agent["name"],
                    "icon": "🤖",
                    "content": agent["description"],
                    "layout": "profile",
                    "properties": {
                        "agent_name": agent["name"],
                        "capabilities": agent["capabilities"],
                        "agent_status": "idle",
                        "last_seen": utc_now_iso(),
                    },
                },
            }],
        )


async def _list_agents() -> list[dict]:
    await _ensure_agent_objects()
    client = qdrant_manager.get_async_client()
    results = await client.scroll(
        collection_name="objects",
        scroll_filter={"must": [{"key": "type", "match": {"value": "agent"}}]},
        limit=100,
        with_payload=True,
        with_vectors=False,
    )
    agents = []
    for point in results[0]:
        payload = dict(point.payload or {})
        properties = payload.get("properties", {})
        status = await openclaw_service.get_agent_status(properties.get("agent_name", payload.get("title", "")))
        agent = {
            "id": str(point.id),
            "name": properties.get("agent_name") or payload.get("title"),
            "description": payload.get("content"),
            "status": status.get("status", properties.get("agent_status", "offline")),
            "capabilities": properties.get("capabilities", []),
            "current_action": status.get("current_action"),
            "last_seen": status.get("last_seen") or properties.get("last_seen"),
        }
        agents.append(agent)
    agents.sort(key=lambda item: item["name"])
    return agents


@router.get("")
@read_rate_limit
async def list_agents(request: Request, current_user: dict = Depends(get_current_user)):
    """List agents with current status."""
    return {"agents": await _list_agents()}


@router.get("/{name}")
@read_rate_limit
async def get_agent(name: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Get agent details."""
    agents = await _list_agents()
    agent = next((item for item in agents if item["name"] == name), None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/{name}/chat")
@write_rate_limit
async def chat_with_agent(name: str, request: Request, data: ChatRequest = Body(...), current_user: dict = Depends(get_current_user)):
    """Send a message to an agent and store chat logs."""
    client = qdrant_manager.get_async_client()
    content = data.content.strip()
    session_id = data.session_id or "main"
    related_task = data.related_task
    if not content:
        raise HTTPException(status_code=400, detail="content is required")

    user_message_id = str(uuid.uuid4())
    user_embedding = await embedding_service.embed_text(content)
    await client.upsert(
        collection_name="chat_logs",
        points=[{
            "id": user_message_id,
            "vector": user_embedding.tolist(),
            "payload": {
                "id": user_message_id,
                "session_id": session_id,
                "agent_name": name,
                "message_type": "user",
                "content": content,
                "timestamp": utc_now_iso(),
                "related_task": related_task,
                "metadata": {},
            },
        }],
    )

    response = await openclaw_service.send_message(name, content, session_id=session_id)
    agent_content = response.get("content") or response.get("message") or ""
    agent_message_id = str(uuid.uuid4())
    agent_embedding = await embedding_service.embed_text(agent_content)
    await client.upsert(
        collection_name="chat_logs",
        points=[{
            "id": agent_message_id,
            "vector": agent_embedding.tolist(),
            "payload": {
                "id": agent_message_id,
                "session_id": session_id,
                "agent_name": name,
                "message_type": "agent",
                "content": agent_content,
                "timestamp": utc_now_iso(),
                "related_task": related_task,
                "metadata": response.get("metadata", {}),
            },
        }],
    )

    await sqlite_manager.execute(
        """
        INSERT INTO agent_sessions (id, agent_name, task_id, status, messages_count)
        VALUES (?, ?, ?, ?, 2)
        ON CONFLICT(id) DO UPDATE SET
            status = excluded.status,
            messages_count = agent_sessions.messages_count + 2
        """,
        (session_id, name, related_task, "active"),
    )

    await websocket_manager.broadcast(WebSocketEvents.chat_message(name, agent_content, session_id))
    return {
        "message_id": user_message_id,
        "response_id": agent_message_id,
        "session_id": session_id,
        "response": response,
    }


@router.get("/{name}/chat")
@read_rate_limit
async def get_chat_history(
    name: str,
    request: Request,
    session_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """Get chat history with an agent."""
    client = qdrant_manager.get_async_client()
    query_filter = {"must": [{"key": "agent_name", "match": {"value": name}}]}
    if session_id:
        query_filter["must"].append({"key": "session_id", "match": {"value": session_id}})

    results = await client.scroll(
        collection_name="chat_logs",
        scroll_filter=query_filter,
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )
    messages = []
    for point in results[0]:
        payload = dict(point.payload or {})
        payload["id"] = str(point.id)
        payload["role"] = payload.get("message_type", "agent")
        messages.append(payload)
    messages.sort(key=lambda item: item.get("timestamp", ""))
    return {"messages": messages}


@router.get("/{name}/tasks")
@read_rate_limit
async def get_agent_tasks(
    name: str,
    request: Request,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Get tasks assigned to an agent."""
    client = qdrant_manager.get_async_client()
    query_filter = {
        "must": [
            {"key": "type", "match": {"value": "task"}},
            {"key": "properties.assigned_to", "match": {"value": name}},
        ]
    }
    if status:
        query_filter["must"].append({"key": "properties.status", "match": {"value": status}})
    results = await client.scroll(
        collection_name="objects",
        scroll_filter=query_filter,
        limit=100,
        with_payload=True,
        with_vectors=False,
    )
    tasks = []
    for point in results[0]:
        payload = dict(point.payload or {})
        payload["id"] = str(point.id)
        tasks.append(payload)
    return {"tasks": tasks}
