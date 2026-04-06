"""Blocks Router - CRUD operations for blocks."""
import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.constants import COLLECTION_BLOCKS
from app.database.qdrant_client import qdrant_manager, QdrantManager
from app.database.sqlite import sqlite_manager
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import read_rate_limit, write_rate_limit
from app.models.blocks import (
    BlockCreate, BlockListResponse, BlockUpdate,
    BatchBlockUpdateRequest, SyncBlocksRequest,
)
from app.services.embedding import embedding_service
from app.services.relations import relation_service
from app.services.websocket_manager import WebSocketEvents, websocket_manager
from app.utils.time import utc_now_iso

router = APIRouter()
logger = logging.getLogger(__name__)


def _point_vector(point) -> list[float] | None:
    """Normalize Qdrant point vectors for reuse in batch upserts."""
    vector = getattr(point, "vector", None)
    if isinstance(vector, dict):
        return next(iter(vector.values()), None)
    return vector


async def _rollback_sqlite(operation: str) -> None:
    """Best-effort SQLite rollback for partially applied multi-store operations."""
    connection = getattr(sqlite_manager, "connection", None)
    if connection is None:
        return
    try:
        await connection.rollback()
    except Exception as exc:
        logger.error("SQLite rollback failed during %s: %s", operation, exc)


async def _restore_blocks_snapshot(client, snapshot_points: list[dict], operation: str, delete_ids: list[str] | None = None) -> None:
    """Best-effort Qdrant rollback for block mutations."""
    try:
        if snapshot_points:
            await client.upsert(collection_name=COLLECTION_BLOCKS, points=snapshot_points)
        if delete_ids:
            await client.delete(collection_name=COLLECTION_BLOCKS, points_selector=delete_ids)
    except Exception as exc:
        logger.error("Qdrant rollback failed during %s: %s", operation, exc)


async def _get_blocks_for_object(object_id: str, limit: int = 100) -> list[dict]:
    limit = max(1, min(limit, 500))
    client = qdrant_manager.get_async_client()
    results = await client.scroll(
        collection_name=COLLECTION_BLOCKS,
        scroll_filter={"must": [{"key": "object_id", "match": {"value": object_id}}]},
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )

    blocks = []
    for point in results[0]:
        payload = dict(point.payload or {})
        payload["id"] = str(point.id)
        blocks.append(payload)

    blocks.sort(key=lambda item: (item.get("order", 0), item.get("created_at", "")))
    return blocks


@router.get("/object/{object_id}", response_model=BlockListResponse)
@read_rate_limit
async def get_blocks_for_object(
    object_id: str,
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    """Get all blocks for an object."""
    return BlockListResponse(blocks=await _get_blocks_for_object(object_id, limit))


@router.post("")
@write_rate_limit
async def create_block(block: BlockCreate, request: Request, current_user: dict = Depends(get_current_user)):
    """Create a new block."""
    client = qdrant_manager.get_async_client()
    block_id = block.id or str(uuid.uuid4())
    embedding = await embedding_service.embed_text(block.content)

    existing_blocks = await _get_blocks_for_object(block.object_id, 500)
    now = utc_now_iso()
    payload = {
        "id": block_id,
        "object_id": block.object_id,
        "type": block.type,
        "content": block.content,
        "level": block.level,
        "order": block.order if block.order is not None else len(existing_blocks),
        "properties": (block.properties.model_dump(exclude_none=True) if block.properties else {}),
        "parent_id": block.parent_id,
        "references": [],
        "referenced_by": [],
        "created_at": now,
        "updated_at": now,
    }

    try:
        await client.upsert(
            collection_name=COLLECTION_BLOCKS,
            points=[{"id": block_id, "vector": embedding.tolist(), "payload": payload}],
        )
        await relation_service.sync_block_references(block_id, block.object_id, block.content)
    except Exception as exc:
        logger.error("Failed to create block %s: %s", block_id, exc)
        await _rollback_sqlite("create_block")
        await _restore_blocks_snapshot(client, [], "create_block", delete_ids=[block_id])
        raise

    await websocket_manager.broadcast(WebSocketEvents.block_created(block_id, block.object_id))
    return payload


@router.put("/{block_id}")
@write_rate_limit
async def update_block(
    block_id: str,
    update: BlockUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Update a block."""
    client = qdrant_manager.get_async_client()
    existing = await QdrantManager.safe_retrieve(client, 
        collection_name=COLLECTION_BLOCKS,
        ids=[block_id],
        with_payload=True,
        with_vectors=True,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Block not found")

    payload = dict(existing[0].payload or {})
    content_changed = False
    if update.content is not None:
        payload["content"] = update.content
        content_changed = True
    if update.type is not None:
        payload["type"] = update.type
    if update.level is not None:
        payload["level"] = update.level
    if update.properties is not None:
        payload["properties"] = update.properties.model_dump(exclude_none=True)
    if update.order is not None:
        payload["order"] = update.order
    if "parent_id" in update.model_fields_set:
        payload["parent_id"] = update.parent_id
    payload["updated_at"] = utc_now_iso()

    original_point = {
        "id": block_id,
        "vector": _point_vector(existing[0]),
        "payload": dict(existing[0].payload or {}),
    }

    try:
        if content_changed:
            embedding = await embedding_service.embed_text(payload["content"])
            await client.upsert(
                collection_name=COLLECTION_BLOCKS,
                points=[{"id": block_id, "vector": embedding.tolist(), "payload": payload}],
            )
            await relation_service.sync_block_references(block_id, payload["object_id"], payload["content"])
        else:
            await client.set_payload(collection_name=COLLECTION_BLOCKS, payload=payload, points=[block_id])
    except Exception as exc:
        logger.error("Failed to update block %s: %s", block_id, exc)
        await _rollback_sqlite("update_block")
        await _restore_blocks_snapshot(client, [original_point], "update_block")
        raise

    await websocket_manager.broadcast(WebSocketEvents.block_updated(block_id, payload["object_id"]))
    return payload


@router.post("/batch-update")
@write_rate_limit
async def batch_update_blocks(data: BatchBlockUpdateRequest, request: Request, current_user: dict = Depends(get_current_user)):
    """Batch update block order and nesting."""
    client = qdrant_manager.get_async_client()
    requested_updates = [block_data for block_data in data.blocks if block_data.id]
    if not requested_updates:
        return {"message": "Updated 0 blocks", "count": 0}

    existing_points = await QdrantManager.safe_retrieve(client, 
        collection_name=COLLECTION_BLOCKS,
        ids=[block_data.id for block_data in requested_updates],
        with_payload=True,
        with_vectors=True,
    )
    existing_map = {str(point.id): point for point in existing_points}

    points = []
    for block_data in requested_updates:
        block_id = block_data.id
        existing = existing_map.get(block_id)
        if existing is None:
            continue
        payload = dict(existing.payload or {})
        if block_data.order is not None:
            payload["order"] = block_data.order
        if block_data.parent_id is not None:
            payload["parent_id"] = block_data.parent_id
        if block_data.level is not None:
            payload["level"] = block_data.level
        payload["updated_at"] = utc_now_iso()
        points.append({"id": block_id, "vector": _point_vector(existing), "payload": payload})

    if points:
        await client.upsert(collection_name=COLLECTION_BLOCKS, points=points)

    updated = len(points)
    return {"message": f"Updated {updated} blocks", "count": updated}


@router.put("/object/{object_id}/sync")
@write_rate_limit
async def sync_blocks_for_object(
    object_id: str,
    data: SyncBlocksRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Replace an object's block set in a single request."""
    client = qdrant_manager.get_async_client()
    incoming_blocks = data.blocks

    existing, _ = await client.scroll(
        collection_name=COLLECTION_BLOCKS,
        scroll_filter={"must": [{"key": "object_id", "match": {"value": object_id}}]},
        limit=5000,
        with_payload=True,
        with_vectors=True,
    )
    existing_map = {str(point.id): point for point in existing}
    snapshot_points = [
        {
            "id": str(point.id),
            "vector": _point_vector(point),
            "payload": dict(point.payload or {}),
        }
        for point in existing
    ]
    incoming_ids = {block.id for block in incoming_blocks if block.id}
    deleted_ids = [block_id for block_id in existing_map if block_id not in incoming_ids]

    upsert_payloads = []
    for order, block in enumerate(incoming_blocks):
        block_id = block.id or str(uuid.uuid4())
        existing_point = existing_map.get(block_id)
        existing_payload = dict(existing_point.payload or {}) if existing_point else {}
        created_at = existing_payload.get("created_at") if existing_payload else None
        upsert_payloads.append(
            {
                "id": block_id,
                "object_id": object_id,
                "type": block.type,
                "content": block.content,
                "level": block.level,
                "order": order,
                "properties": block.properties if block.properties is not None else {},
                "parent_id": block.parent_id,
                "references": existing_payload.get("references", []),
                "referenced_by": existing_payload.get("referenced_by", []),
                "created_at": created_at or utc_now_iso(),
                "updated_at": utc_now_iso(),
            }
        )

    created_ids = [payload["id"] for payload in upsert_payloads if payload["id"] not in existing_map]
    try:
        for block_id in deleted_ids:
            await relation_service.remove_block_references(block_id)

        if deleted_ids:
            await client.delete(collection_name=COLLECTION_BLOCKS, points_selector=deleted_ids)

        if upsert_payloads:
            embeddings = await asyncio.gather(
                *(embedding_service.embed_text(payload["content"]) for payload in upsert_payloads)
            )
            points = [
                {"id": payload["id"], "vector": embedding.tolist(), "payload": payload}
                for payload, embedding in zip(upsert_payloads, embeddings)
            ]
            await client.upsert(collection_name=COLLECTION_BLOCKS, points=points)

        for payload in upsert_payloads:
            await relation_service.sync_block_references(payload["id"], object_id, payload["content"])
    except Exception as exc:
        logger.error("Failed to sync blocks for object %s: %s", object_id, exc)
        await _rollback_sqlite("sync_blocks_for_object")
        await _restore_blocks_snapshot(client, snapshot_points, "sync_blocks_for_object", delete_ids=created_ids)
        raise

    await websocket_manager.broadcast(WebSocketEvents.object_updated(object_id, ["blocks"]))
    return {"message": "Blocks synced", "count": len(incoming_blocks)}


@router.delete("/{block_id}")
@write_rate_limit
async def delete_block(block_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Delete a block."""
    client = qdrant_manager.get_async_client()
    existing = await QdrantManager.safe_retrieve(client, 
        collection_name=COLLECTION_BLOCKS,
        ids=[block_id],
        with_payload=True,
        with_vectors=False,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Block not found")

    payload = dict(existing[0].payload or {})
    try:
        await relation_service.remove_block_references(block_id)
        await client.delete(collection_name=COLLECTION_BLOCKS, points_selector=[block_id])
    except Exception as exc:
        logger.error("Failed to delete block %s: %s", block_id, exc)
        await _rollback_sqlite("delete_block")
        raise

    await websocket_manager.broadcast(WebSocketEvents.block_deleted(block_id, payload.get("object_id")))
    return {"message": "Block deleted", "id": block_id}
