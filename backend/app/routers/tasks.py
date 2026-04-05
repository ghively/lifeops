"""Tasks Router - Task management and assignment."""
import asyncio
import logging
import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.config import settings


class AssignTaskRequest(BaseModel):
    agent_name: str
    priority: str = "medium"
    include_context: bool = True
    additional_context: List[str] = Field(default_factory=list)


class UpdateTaskStatusRequest(BaseModel):
    status: str
    current_action: Optional[str] = None
    notes: Optional[str] = None
    agent_name: Optional[str] = None
from app.database.qdrant_client import qdrant_manager, QdrantManager
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import read_rate_limit, write_rate_limit
from app.models.tasks import TaskListResponse
from app.services.context_builder import context_builder
from app.services.embedding import embedding_service
from app.services.openclaw import openclaw_service
from app.services.websocket_manager import WebSocketEvents, websocket_manager
from app.utils.time import utc_now_iso

router = APIRouter()
logger = logging.getLogger(__name__)

VALID_STATUSES = ["todo", "in-progress", "blocked", "review", "done"]
VALID_PRIORITIES = ["low", "medium", "high", "urgent"]
HEARTBEAT_PATH = settings.heartbeat_path


def _task_counts(tasks: list, key: str):
    counts = {}
    for task in tasks:
        value = task.get("properties", {}).get(key)
        counts[value] = counts.get(value, 0) + 1
    return counts


def _write_to_heartbeat_sync(task_id: str, agent_name: str, task: dict, context: dict):
    """Synchronous file I/O for heartbeat — call via asyncio.to_thread()."""
    os.makedirs(os.path.dirname(HEARTBEAT_PATH), exist_ok=True)
    lines = [
        f"## {utc_now_iso()} | @{agent_name} | task:{task_id}",
        "",
        f"Title: {task.get('title', '')}",
        f"Priority: {task.get('properties', {}).get('priority', 'low')}",
        "",
        "Task:",
        task.get("content") or task.get("title", ""),
        "",
        "Context pointers:",
    ]

    pointers = context.get("qdrant_pointers", {})
    for key, value in pointers.items():
        if isinstance(value, list):
            for item in value:
                lines.append(f"- {key}: {item}")
        elif value:
            lines.append(f"- {key}: {value}")

    lines.extend(["", "---", ""])
    with open(HEARTBEAT_PATH, "a", encoding="utf-8") as heartbeat_file:
        heartbeat_file.write("\n".join(lines))


@router.get("")
@read_rate_limit
async def list_tasks(
    request: Request,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assigned_to: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    current_user: dict = Depends(get_current_user),
):
    """List tasks with filters and counts."""
    client = qdrant_manager.get_async_client()
    query_filter = {"must": [{"key": "type", "match": {"value": "task"}}]}
    if status:
        query_filter["must"].append({"key": "properties.status", "match": {"value": status}})
    if priority:
        query_filter["must"].append({"key": "properties.priority", "match": {"value": priority}})
    if assigned_to:
        query_filter["must"].append({"key": "properties.assigned_to", "match": {"value": assigned_to}})

    results = await client.scroll(
        collection_name="objects",
        scroll_filter=query_filter,
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )

    tasks = []
    for point in results[0]:
        payload = dict(point.payload or {})
        payload["id"] = str(point.id)
        tasks.append(payload)

    tasks.sort(
        key=lambda task: (
            {"urgent": 0, "high": 1, "medium": 2, "low": 3}.get(task.get("properties", {}).get("priority"), 9),
            task.get("properties", {}).get("updated_at", ""),
        )
    )

    return {
        "tasks": tasks,
        "by_status": _task_counts(tasks, "status"),
        "by_priority": _task_counts(tasks, "priority"),
    }


@router.get("/{task_id}")
@read_rate_limit
async def get_task(task_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Get a single task."""
    client = qdrant_manager.get_async_client()
    result = await QdrantManager.safe_retrieve(client, 
        collection_name="objects",
        ids=[task_id],
        with_payload=True,
        with_vectors=False,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    payload = dict(result[0].payload or {})
    payload["id"] = str(result[0].id)
    return payload


@router.post("/{task_id}/assign")
@write_rate_limit
async def assign_task(
    task_id: str,
    data: AssignTaskRequest = Body(...),
    request: Request = None,
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user),
):
    """Assign a task to an agent with context."""
    client = qdrant_manager.get_async_client()
    agent_name = data.agent_name
    priority = data.priority
    include_context = data.include_context
    additional_context = data.additional_context
    if priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"Invalid priority: {priority}")

    task_result = await QdrantManager.safe_retrieve(client, 
        collection_name="objects",
        ids=[task_id],
        with_payload=True,
        with_vectors=False,
    )
    if not task_result:
        raise HTTPException(status_code=404, detail="Task not found")

    task = dict(task_result[0].payload or {})
    context = await context_builder.build_task_context(task_id, additional_context) if include_context else {}

    properties = dict(task.get("properties", {}))
    properties["assigned_to"] = agent_name
    properties["priority"] = priority
    properties["assigned_at"] = utc_now_iso()
    properties["current_action"] = "queued"
    properties["context_included"] = additional_context

    route = "heartbeat" if priority == "low" else "direct"
    if route == "direct":
        response = await openclaw_service.assign_task(
            agent_name=agent_name,
            task_id=task_id,
            task_content=task.get("content") or task.get("title", ""),
            context=context,
        )
        properties["status"] = "in-progress"
    else:
        await asyncio.to_thread(_write_to_heartbeat_sync, task_id, agent_name, task, context)
        memory_id = str(uuid.uuid4())
        heartbeat_content = f"{task.get('title', '')}\n\n{task.get('content', '')}"
        embedding = await embedding_service.embed_text(heartbeat_content)
        await client.upsert(
            collection_name="agent_memories",
            points=[{
                "id": memory_id,
                "vector": embedding.tolist(),
                "payload": {
                    "id": memory_id,
                    "agent_name": agent_name,
                    "memory_type": "action",
                    "content": heartbeat_content,
                    "importance": 5,
                    "related_objects": additional_context,
                    "related_tasks": [task_id],
                    "session_id": f"heartbeat:{task_id}",
                    "timestamp": utc_now_iso(),
                },
            }],
        )
        response = {
            "status": "queued",
            "memory_id": memory_id,
            "heartbeat_path": HEARTBEAT_PATH,
            "message": "Task queued in HEARTBEAT.md",
        }
        properties["status"] = "todo"

    task["properties"] = properties
    await client.set_payload(collection_name="objects", payload=task, points=[task_id])
    await websocket_manager.broadcast(WebSocketEvents.task_assigned(task_id, agent_name, priority, route))
    await websocket_manager.broadcast(
        WebSocketEvents.agent_current_action(agent_name, properties.get("current_action", "queued"), task_id)
    )

    return {
        "message": "Task assigned",
        "task_id": task_id,
        "agent_name": agent_name,
        "assignment_type": route,
        "context": context,
        "response": response,
    }


@router.post("/{task_id}/status")
@write_rate_limit
async def update_task_status(
    task_id: str,
    data: UpdateTaskStatusRequest = Body(...),
    request: Request = None,
    current_user: dict = Depends(get_current_user),
):
    """Update task status, current action, and notes."""
    client = qdrant_manager.get_async_client()
    status = data.status
    current_action = data.current_action
    notes = data.notes
    agent_name = data.agent_name

    if status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {VALID_STATUSES}")

    task_result = await QdrantManager.safe_retrieve(client, 
        collection_name="objects",
        ids=[task_id],
        with_payload=True,
        with_vectors=False,
    )
    if not task_result:
        raise HTTPException(status_code=404, detail="Task not found")

    task = dict(task_result[0].payload or {})
    properties = dict(task.get("properties", {}))
    properties["status"] = status
    if current_action is not None:
        properties["current_action"] = current_action
    if notes is not None:
        properties["notes"] = notes
    if status == "done":
        properties["completed_at"] = utc_now_iso()
    properties["updated_at"] = utc_now_iso()
    task["properties"] = properties
    await client.set_payload(collection_name="objects", payload=task, points=[task_id])

    await websocket_manager.broadcast(WebSocketEvents.task_status_changed(task_id, status, agent_name))
    if current_action is not None and agent_name:
        await websocket_manager.broadcast(WebSocketEvents.agent_current_action(agent_name, current_action, task_id))
        await websocket_manager.broadcast(WebSocketEvents.task_progress_update(task_id, current_action, agent_name))
    if status == "done":
        await websocket_manager.broadcast(WebSocketEvents.task_completed(task_id, agent_name))

    return {"message": "Status updated", "task_id": task_id, "status": status}


@router.get("/{task_id}/context")
@read_rate_limit
async def get_task_context(task_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Get the full context package for a task."""
    return {"context": await context_builder.build_task_context(task_id=task_id)}
