"""Objects Router - CRUD operations for objects."""
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.database.qdrant_client import qdrant_manager
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import read_rate_limit, write_rate_limit
from app.models.objects import ObjectCreate, ObjectListResponse, ObjectUpdate
from app.services.embedding import embedding_service
from app.services.relations import relation_service
from app.services.websocket_manager import WebSocketEvents, websocket_manager
from app.utils.time import utc_now_iso

router = APIRouter()
logger = logging.getLogger(__name__)


def _merge_properties(existing: dict, incoming: Optional[dict]) -> dict:
    merged = dict(existing or {})
    if incoming:
        for key, value in incoming.items():
            merged[key] = value
    merged["updated_at"] = utc_now_iso()
    merged.setdefault("created_at", utc_now_iso())
    return merged


def _normalize_scroll_offset(offset: Optional[str]) -> Optional[str]:
    if offset in {None, "", "0"}:
        return None
    return offset


async def _count_collection(client, collection_name: str, scroll_filter: Optional[dict]) -> int:
    count = await client.count(
        collection_name=collection_name,
        count_filter=scroll_filter,
        exact=True,
    )
    return int(count.count)


async def _delete_blocks_for_object(client, object_id: str) -> None:
    next_offset = None
    while True:
        blocks, next_offset = await client.scroll(
            collection_name="blocks",
            scroll_filter={"must": [{"key": "object_id", "match": {"value": object_id}}]},
            offset=next_offset,
            limit=100,
            with_payload=True,
            with_vectors=False,
        )
        for block in blocks:
            await relation_service.remove_block_references(str(block.id))
            await client.delete(collection_name="blocks", points_selector=[str(block.id)])
        if next_offset is None:
            break


@router.get("", response_model=ObjectListResponse)
@read_rate_limit
async def list_objects(
    request: Request,
    type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=1000),
    offset: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """List objects with optional filtering."""
    client = qdrant_manager.get_async_client()
    query_filter = {"must": [{"key": "type", "match": {"value": type}}]} if type else None

    points, next_offset = await client.scroll(
        collection_name="objects",
        scroll_filter=query_filter,
        offset=_normalize_scroll_offset(offset),
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )

    objects = []
    for point in points:
        payload = dict(point.payload or {})
        payload["id"] = str(point.id)
        objects.append(payload)

    return ObjectListResponse(
        objects=objects,
        total=await _count_collection(client, "objects", query_filter),
        next_offset=str(next_offset) if next_offset is not None else None,
    )


@router.get("/{object_id}")
@read_rate_limit
async def get_object(object_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Get a single object by ID."""
    client = qdrant_manager.get_async_client()
    results = await client.retrieve(
        collection_name="objects",
        ids=[object_id],
        with_payload=True,
        with_vectors=False,
    )
    if not results:
        raise HTTPException(status_code=404, detail="Object not found")

    payload = dict(results[0].payload or {})
    payload["id"] = str(results[0].id)
    return payload


@router.post("")
@write_rate_limit
async def create_object(obj: ObjectCreate, request: Request, current_user: dict = Depends(get_current_user)):
    """Create a new object."""
    client = qdrant_manager.get_async_client()
    object_id = str(uuid.uuid4())
    content = obj.content or obj.title
    embedding = await embedding_service.embed_text(content)

    properties = _merge_properties({}, obj.properties.model_dump(exclude_none=True) if obj.properties else {})
    payload = {
        "id": object_id,
        "type": obj.type,
        "title": obj.title,
        "icon": obj.icon,
        "content": content,
        "properties": properties,
        "layout": obj.layout or "default",
    }

    await client.upsert(
        collection_name="objects",
        points=[{"id": object_id, "vector": embedding.tolist(), "payload": payload}],
    )
    await relation_service.sync_object_links(object_id, obj.title, content)
    await websocket_manager.broadcast(WebSocketEvents.object_created(object_id, obj.type, obj.title))
    return payload


@router.put("/{object_id}")
@write_rate_limit
async def update_object(
    object_id: str,
    update: ObjectUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Partial update for an object."""
    client = qdrant_manager.get_async_client()
    existing = await client.retrieve(
        collection_name="objects",
        ids=[object_id],
        with_payload=True,
        with_vectors=False,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Object not found")

    payload = dict(existing[0].payload or {})
    changes = []

    if update.title is not None:
        payload["title"] = update.title
        changes.append("title")
    if update.icon is not None:
        payload["icon"] = update.icon
        changes.append("icon")
    if update.content is not None:
        payload["content"] = update.content
        changes.append("content")
    if update.layout is not None:
        payload["layout"] = update.layout
        changes.append("layout")
    if update.properties is not None:
        payload["properties"] = _merge_properties(
            payload.get("properties", {}),
            update.properties.model_dump(exclude_none=True),
        )
        changes.append("properties")
    else:
        payload["properties"] = _merge_properties(payload.get("properties", {}), None)

    if not changes:
        return payload

    if "title" in changes or "content" in changes:
        embedding = await embedding_service.embed_text(payload.get("content") or payload.get("title", ""))
        await client.upsert(
            collection_name="objects",
            points=[{"id": object_id, "vector": embedding.tolist(), "payload": payload}],
        )
    else:
        await client.set_payload(collection_name="objects", payload=payload, points=[object_id])

    await relation_service.sync_object_links(object_id, payload.get("title", ""), payload.get("content", ""))
    await websocket_manager.broadcast(WebSocketEvents.object_updated(object_id, changes))
    return payload


@router.delete("/{object_id}")
@write_rate_limit
async def delete_object(object_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Delete an object and cleanup related blocks and relations."""
    client = qdrant_manager.get_async_client()
    existing = await client.retrieve(
        collection_name="objects",
        ids=[object_id],
        with_payload=False,
        with_vectors=False,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Object not found")

    await _delete_blocks_for_object(client, object_id)

    await relation_service.remove_relations_for_entity(object_id)
    await client.delete(collection_name="objects", points_selector=[object_id])
    await websocket_manager.broadcast(WebSocketEvents.object_deleted(object_id))
    return {"message": "Object deleted", "id": object_id}


@router.get("/{object_id}/relations")
@read_rate_limit
async def get_object_relations(object_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Get relations for an object."""
    return {"relations": await relation_service.list_relations_for_object(object_id)}
