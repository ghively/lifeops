"""Objects Router - CRUD operations for objects."""
import logging
import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.constants import COLLECTION_BLOCKS, COLLECTION_OBJECTS
from app.database.qdrant_client import qdrant_manager, QdrantManager
from app.database.sqlite import sqlite_manager
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import read_rate_limit, write_rate_limit
from app.models.objects import ObjectCreate, ObjectListResponse, ObjectUpdate
from app.services.embedding import embedding_service
from app.services.relations import relation_service
from app.services.websocket_manager import WebSocketEvents, websocket_manager
from app.utils.sanitize import sanitize_content
from app.utils.time import utc_now_iso

router = APIRouter()
logger = logging.getLogger(__name__)
TAG_PATTERN = re.compile(r"#([a-zA-Z0-9_-]+)")
MENTION_PATTERN = re.compile(r"@([a-zA-Z0-9_-]+)")


def _point_vector(point) -> list[float] | None:
    vector = getattr(point, "vector", None)
    if isinstance(vector, dict):
        return next(iter(vector.values()), None)
    return vector


async def _rollback_sqlite(operation: str) -> None:
    connection = getattr(sqlite_manager, "connection", None)
    if connection is None:
        return
    try:
        await connection.rollback()
    except Exception as exc:
        logger.error("SQLite rollback failed during %s: %s", operation, exc)


async def _restore_qdrant_snapshot(client, collection_name: str, snapshot_points: list[dict], operation: str, delete_ids: list[str] | None = None) -> None:
    try:
        if snapshot_points:
            await client.upsert(collection_name=collection_name, points=snapshot_points)
        if delete_ids:
            await client.delete(collection_name=collection_name, points_selector=delete_ids)
    except Exception as exc:
        logger.error("Qdrant rollback failed during %s for %s: %s", operation, collection_name, exc)


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


def _unique_preserving_order(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _parse_tags_from_content(content: str) -> list[str]:
    return _unique_preserving_order(TAG_PATTERN.findall(content or ""))


async def _parse_mentions_from_content(client, content: str) -> list[str]:
    requested_mentions = _unique_preserving_order(MENTION_PATTERN.findall(content or ""))
    if not requested_mentions:
        return []

    agent_records, _ = await client.scroll(
        collection_name=COLLECTION_OBJECTS,
        scroll_filter={"must": [{"key": "type", "match": {"value": "agent"}}]},
        limit=100,
        with_payload=True,
        with_vectors=False,
    )
    agent_names = {
        payload_name.lower()
        for point in agent_records
        for payload_name in [
            (point.payload or {}).get("properties", {}).get("agent_name") or (point.payload or {}).get("title")
        ]
        if payload_name
    }
    # Deduplicate by lowercase to avoid storing @Sampler and @sampler separately
    seen = set()
    result = []
    for mention in requested_mentions:
        lower = mention.lower()
        if lower in agent_names and lower not in seen:
            seen.add(lower)
            result.append(mention)
    return result


async def _enrich_properties_from_content(client, object_id: str, payload: dict) -> dict:
    properties = dict(payload.get("properties") or {})
    content = payload.get("content") or payload.get("title", "")

    parsed_tags = _parse_tags_from_content(content)
    if parsed_tags:
        properties["tags"] = _unique_preserving_order([*(properties.get("tags") or []), *parsed_tags])

    parsed_mentions = await _parse_mentions_from_content(client, content)
    if parsed_mentions:
        properties["mentions"] = _unique_preserving_order([*(properties.get("mentions") or []), *parsed_mentions])

    payload["properties"] = properties
    await client.set_payload(collection_name=COLLECTION_OBJECTS, payload=payload, points=[object_id])
    return payload


async def _delete_blocks_for_object(client, object_id: str) -> None:
    next_offset = None
    while True:
        blocks, next_offset = await client.scroll(
            collection_name=COLLECTION_BLOCKS,
            scroll_filter={"must": [{"key": "object_id", "match": {"value": object_id}}]},
            offset=next_offset,
            limit=100,
            with_payload=True,
            with_vectors=False,
        )
        for block in blocks:
            await relation_service.remove_block_references(str(block.id))
            await client.delete(collection_name=COLLECTION_BLOCKS, points_selector=[str(block.id)])
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
        collection_name=COLLECTION_OBJECTS,
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
        total=await _count_collection(client, COLLECTION_OBJECTS, query_filter),
        next_offset=str(next_offset) if next_offset is not None else None,
    )


@router.get("/{object_id}")
@read_rate_limit
async def get_object(object_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Get a single object by ID."""
    client = qdrant_manager.get_async_client()
    results = await QdrantManager.safe_retrieve(client, 
        collection_name=COLLECTION_OBJECTS,
        ids=[object_id],
        with_payload=True,
        with_vectors=False,
    )
    if not results:
        raise HTTPException(status_code=404, detail="Object not found")

    payload = dict(results[0].payload or {})
    payload["id"] = str(results[0].id)
    return payload


@router.post("", status_code=201)
@write_rate_limit
async def create_object(obj: ObjectCreate, request: Request, current_user: dict = Depends(get_current_user)):
    """Create a new object."""
    client = qdrant_manager.get_async_client()
    object_id = str(uuid.uuid4())
    content = sanitize_content(obj.content or obj.title)
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

    try:
        await client.upsert(
            collection_name=COLLECTION_OBJECTS,
            points=[{"id": object_id, "vector": embedding.tolist(), "payload": payload}],
        )
        payload = await _enrich_properties_from_content(client, object_id, payload)
        await relation_service.sync_object_links(object_id, obj.title, content)
    except Exception as exc:
        logger.error("Failed to create object %s: %s", object_id, exc)
        await _rollback_sqlite("create_object")
        await _restore_qdrant_snapshot(client, COLLECTION_OBJECTS, [], "create_object", delete_ids=[object_id])
        raise

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
    existing = await QdrantManager.safe_retrieve(client, 
        collection_name=COLLECTION_OBJECTS,
        ids=[object_id],
        with_payload=True,
        with_vectors=True,
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
        payload["content"] = sanitize_content(update.content)
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

    original_point = {
        "id": object_id,
        "vector": _point_vector(existing[0]),
        "payload": dict(existing[0].payload or {}),
    }

    try:
        if "title" in changes or "content" in changes:
            embedding = await embedding_service.embed_text(payload.get("content") or payload.get("title", ""))
            await client.upsert(
                collection_name=COLLECTION_OBJECTS,
                points=[{"id": object_id, "vector": embedding.tolist(), "payload": payload}],
            )
        else:
            await client.set_payload(collection_name=COLLECTION_OBJECTS, payload=payload, points=[object_id])

        payload = await _enrich_properties_from_content(client, object_id, payload)
        await relation_service.sync_object_links(object_id, payload.get("title", ""), payload.get("content", ""))
    except Exception as exc:
        logger.error("Failed to update object %s: %s", object_id, exc)
        await _rollback_sqlite("update_object")
        await _restore_qdrant_snapshot(client, COLLECTION_OBJECTS, [original_point], "update_object")
        raise

    await websocket_manager.broadcast(WebSocketEvents.object_updated(object_id, changes))
    return payload


@router.delete("/{object_id}")
@write_rate_limit
async def delete_object(object_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Delete an object and cleanup related blocks and relations."""
    client = qdrant_manager.get_async_client()
    existing = await QdrantManager.safe_retrieve(client, 
        collection_name=COLLECTION_OBJECTS,
        ids=[object_id],
        with_payload=True,
        with_vectors=True,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Object not found")

    block_points, _ = await client.scroll(
        collection_name=COLLECTION_BLOCKS,
        scroll_filter={"must": [{"key": "object_id", "match": {"value": object_id}}]},
        limit=5000,
        with_payload=True,
        with_vectors=True,
    )
    object_snapshot = [
        {
            "id": object_id,
            "vector": _point_vector(existing[0]),
            "payload": dict(existing[0].payload or {}),
        }
    ]
    block_snapshot = [
        {
            "id": str(point.id),
            "vector": _point_vector(point),
            "payload": dict(point.payload or {}),
        }
        for point in block_points
    ]
    block_ids = [str(point.id) for point in block_points]

    try:
        for block_id in block_ids:
            await relation_service.remove_block_references(block_id)

        if block_ids:
            await client.delete(collection_name=COLLECTION_BLOCKS, points_selector=block_ids)

        await relation_service.remove_relations_for_entity(object_id)
        await client.delete(collection_name=COLLECTION_OBJECTS, points_selector=[object_id])
    except Exception as exc:
        logger.error("Failed to delete object %s: %s", object_id, exc)
        await _rollback_sqlite("delete_object")
        await _restore_qdrant_snapshot(client, COLLECTION_BLOCKS, block_snapshot, "delete_object")
        await _restore_qdrant_snapshot(client, COLLECTION_OBJECTS, object_snapshot, "delete_object")
        raise

    await websocket_manager.broadcast(WebSocketEvents.object_deleted(object_id))
    return {"message": "Object deleted", "id": object_id}


@router.get("/{object_id}/relations")
@read_rate_limit
async def get_object_relations(object_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Get relations for an object."""
    return {"relations": await relation_service.list_relations_for_object(object_id)}
