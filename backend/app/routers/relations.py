"""Relations Router - CRUD operations for relations and backlinks."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.database.qdrant_client import qdrant_manager
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import read_rate_limit, write_rate_limit
from app.models.relations import RelationCreate, RelationListResponse, RelationUpdate
from app.services.relations import relation_service
from app.utils.time import utc_now_iso

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("")
@write_rate_limit
async def create_relation(relation: RelationCreate, request: Request, current_user: dict = Depends(get_current_user)):
    """Create a relation between objects or blocks."""
    try:
        return await relation_service.create_relation(
            source_id=relation.source_id,
            source_type=relation.source_type,
            target_id=relation.target_id,
            target_type=relation.target_type,
            relation_type=relation.relation_type,
            context=relation.context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/object/{object_id}", response_model=RelationListResponse)
@read_rate_limit
async def get_relations_for_object(
    object_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Get all relations where an entity is source or target."""
    relations = await relation_service.list_relations_for_object(object_id)
    return RelationListResponse(relations=relations)


@router.put("/{relation_id}")
@write_rate_limit
async def update_relation(
    relation_id: str,
    update: RelationUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Update relation metadata."""
    client = qdrant_manager.get_async_client()
    result = await client.retrieve(
        collection_name="relations",
        ids=[relation_id],
        with_payload=True,
        with_vectors=False,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Relation not found")

    payload = dict(result[0].payload or {})
    if update.relation_type is not None:
        payload["relation_type"] = update.relation_type
    if update.context is not None:
        payload["context"] = update.context
    payload["updated_at"] = utc_now_iso()

    await client.set_payload(collection_name="relations", payload=payload, points=[relation_id])
    return payload


@router.delete("/{relation_id}")
@write_rate_limit
async def delete_relation(relation_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Delete a relation."""
    await relation_service.delete_relation(relation_id)
    return {"message": "Relation deleted", "id": relation_id}
