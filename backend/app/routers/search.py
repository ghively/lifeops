"""Search Router - Semantic and exact search."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.database.qdrant_client import qdrant_manager
from app.middleware.auth import get_optional_user
from app.middleware.rate_limit import read_rate_limit
from app.services.embedding import embedding_service

router = APIRouter()
logger = logging.getLogger(__name__)

# Search uses optional authentication so public/shared knowledge bases can be
# searched without requiring a logged-in user. When a user is present, this can
# later be extended to include user-specific search behavior and results.
SEARCH_COLLECTIONS = ["objects", "blocks", "relations", "files", "images", "code", "agent_memories", "chat_logs"]
TEXT_FIELDS = ["title", "content", "context", "content_text", "content_preview", "description", "name"]


def _match_exact(payload: dict, query: str) -> bool:
    lowered = query.lower()
    for field in TEXT_FIELDS:
        value = payload.get(field)
        if isinstance(value, str) and lowered in value.lower():
            return True
    return False


@router.get("")
@read_rate_limit
async def search(
    request: Request,
    q: str,
    exact: bool = False,
    collection: Optional[str] = None,
    limit: int = Query(10, ge=1, le=100),
    current_user: dict | None = Depends(get_optional_user),
):
    """Search across configured collections."""
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    client = qdrant_manager.get_async_client()
    collections = [collection] if collection else SEARCH_COLLECTIONS
    results = []

    query_embedding = None if exact else await embedding_service.embed_text(q)
    for coll in collections:
        try:
            if exact:
                scroll = await client.scroll(
                    collection_name=coll,
                    limit=max(limit * 5, 50),
                    with_payload=True,
                    with_vectors=False,
                )
                for point in scroll[0]:
                    payload = dict(point.payload or {})
                    if _match_exact(payload, q):
                        payload["id"] = str(point.id)
                        payload["score"] = 1.0
                        payload["collection"] = coll
                        results.append(payload)
            else:
                search_results = await client.search(
                    collection_name=coll,
                    query_vector=query_embedding.tolist(),
                    limit=limit,
                    with_payload=True,
                    with_vectors=False,
                )
                for point in search_results:
                    payload = dict(point.payload or {})
                    payload["id"] = str(point.id)
                    payload["score"] = point.score
                    payload["collection"] = coll
                    results.append(payload)
        except Exception as exc:
            logger.warning("Search skipped for %s: %s", coll, exc)

    results.sort(key=lambda item: item.get("score", 0), reverse=True)
    return {"results": results[:limit]}


@router.get("/similar/{object_id}")
@read_rate_limit
async def find_similar(
    object_id: str,
    request: Request,
    collection: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50),
    current_user: dict | None = Depends(get_optional_user),
):
    """Find similar entries for a given object."""
    client = qdrant_manager.get_async_client()
    source_collection = collection or "objects"
    source = await client.retrieve(
        collection_name=source_collection,
        ids=[object_id],
        with_payload=True,
        with_vectors=True,
    )
    if not source:
        raise HTTPException(status_code=404, detail="Object not found")

    source_vector = source[0].vector
    search_results = await client.search(
        collection_name=source_collection,
        query_vector=source_vector,
        limit=limit + 1,
        with_payload=True,
        with_vectors=False,
    )

    similar = []
    for point in search_results:
        if str(point.id) == object_id:
            continue
        payload = dict(point.payload or {})
        payload["id"] = str(point.id)
        payload["score"] = point.score
        payload["collection"] = source_collection
        similar.append(payload)
    return {"results": similar[:limit]}
