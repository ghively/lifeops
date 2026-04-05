"""Blocks Router - CRUD operations for blocks."""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.database.qdrant_client import qdrant_manager
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import read_rate_limit, write_rate_limit
from app.models.blocks import BlockCreate, BlockListResponse, BlockUpdate
from app.services.embedding import embedding_service
from app.services.relations import relation_service
from app.services.websocket_manager import WebSocketEvents, websocket_manager
from app.utils.time import utc_now_iso

router = APIRouter()
logger = logging.getLogger(__name__)


async def _get_blocks_for_object(object_id: str, limit: int) -> list[dict]:
    client = qdrant_manager.get_async_client()
    results = await client.scroll(
        collection_name="blocks",
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
    limit: int = Query(1000, ge=1, le=5000),
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

    existing_blocks = await _get_blocks_for_object(block.object_id, 5000)
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
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }

    await client.upsert(
        collection_name="blocks",
        points=[{"id": block_id, "vector": embedding.tolist(), "payload": payload}],
    )
    await relation_service.sync_block_references(block_id, block.object_id, block.content)
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
    existing = await client.retrieve(
        collection_name="blocks",
        ids=[block_id],
        with_payload=True,
        with_vectors=False,
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

    if content_changed:
        embedding = await embedding_service.embed_text(payload["content"])
        await client.upsert(
            collection_name="blocks",
            points=[{"id": block_id, "vector": embedding.tolist(), "payload": payload}],
        )
        await relation_service.sync_block_references(block_id, payload["object_id"], payload["content"])
    else:
        await client.set_payload(collection_name="blocks", payload=payload, points=[block_id])

    await websocket_manager.broadcast(WebSocketEvents.block_updated(block_id, payload["object_id"]))
    return payload


@router.post("/batch-update")
@write_rate_limit
async def batch_update_blocks(data: dict, request: Request, current_user: dict = Depends(get_current_user)):
    """Batch update block order and nesting."""
    client = qdrant_manager.get_async_client()
    updated = 0

    for block_data in data.get("blocks", []):
        block_id = block_data.get("id")
        if not block_id:
            continue
        existing = await client.retrieve(
            collection_name="blocks",
            ids=[block_id],
            with_payload=True,
            with_vectors=False,
        )
        if not existing:
            continue
        payload = dict(existing[0].payload or {})
        if "order" in block_data:
            payload["order"] = block_data["order"]
        if "parent_id" in block_data:
            payload["parent_id"] = block_data["parent_id"]
        if "level" in block_data:
            payload["level"] = block_data["level"]
        payload["updated_at"] = utc_now_iso()
        await client.set_payload(collection_name="blocks", payload=payload, points=[block_id])
        updated += 1

    return {"message": f"Updated {updated} blocks", "count": updated}


@router.put("/object/{object_id}/sync")
@write_rate_limit
async def sync_blocks_for_object(
    object_id: str,
    data: dict,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Replace an object's block set in a single request."""
    client = qdrant_manager.get_async_client()
    incoming_blocks = data.get("blocks", [])

    existing = await client.scroll(
        collection_name="blocks",
        scroll_filter={"must": [{"key": "object_id", "match": {"value": object_id}}]},
        limit=5000,
        with_payload=True,
        with_vectors=False,
    )
    existing_map = {str(point.id): dict(point.payload or {}) for point in existing[0]}
    incoming_ids = {block["id"] for block in incoming_blocks if block.get("id")}

    for block_id, payload in existing_map.items():
        if block_id not in incoming_ids:
            await relation_service.remove_block_references(block_id)
            await client.delete(collection_name="blocks", points_selector=[block_id])

    for order, block in enumerate(incoming_blocks):
        block_id = block.get("id") or str(uuid.uuid4())
        existing_payload = existing_map.get(block_id)
        payload = {
            "id": block_id,
            "object_id": object_id,
            "type": block.get("type", "paragraph"),
            "content": block.get("content", ""),
            "level": block.get("level", 0),
            "order": order,
            "properties": block.get("properties", {}),
            "parent_id": block.get("parent_id"),
            "references": existing_payload.get("references", []) if existing_payload else [],
            "referenced_by": existing_payload.get("referenced_by", []) if existing_payload else [],
            "created_at": existing_payload.get("created_at", utc_now_iso()) if existing_payload else utc_now_iso(),
            "updated_at": utc_now_iso(),
        }
        embedding = await embedding_service.embed_text(payload["content"])
        await client.upsert(
            collection_name="blocks",
            points=[{"id": block_id, "vector": embedding.tolist(), "payload": payload}],
        )
        await relation_service.sync_block_references(block_id, object_id, payload["content"])

    await websocket_manager.broadcast(WebSocketEvents.object_updated(object_id, ["blocks"]))
    return {"message": "Blocks synced", "count": len(incoming_blocks)}


@router.delete("/{block_id}")
@write_rate_limit
async def delete_block(block_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Delete a block."""
    client = qdrant_manager.get_async_client()
    existing = await client.retrieve(
        collection_name="blocks",
        ids=[block_id],
        with_payload=True,
        with_vectors=False,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Block not found")

    payload = dict(existing[0].payload or {})
    await relation_service.remove_block_references(block_id)
    await client.delete(collection_name="blocks", points_selector=[block_id])
    await websocket_manager.broadcast(WebSocketEvents.block_deleted(block_id, payload.get("object_id")))
    return {"message": "Block deleted", "id": block_id}
