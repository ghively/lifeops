"""Access-control helpers.

Single-tenant by default — every user that holds a valid JWT sees the
whole knowledge base. This module narrows that for the channels and
resources where ownership IS recorded (objects with a `created_by`
field, per-user notification channels, etc.) so an authenticated user
cannot eavesdrop on another user's private surfaces over WebSockets.

See issue #176.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.constants import COLLECTION_OBJECTS
from app.database.qdrant_client import QdrantManager, qdrant_manager

logger = logging.getLogger(__name__)


def _object_creator(payload: dict[str, Any] | None) -> Optional[str]:
    if not payload:
        return None
    creator = payload.get("created_by")
    if creator:
        return str(creator)
    properties = payload.get("properties") or {}
    if isinstance(properties, dict):
        nested = properties.get("created_by")
        if nested:
            return str(nested)
    return None


async def user_can_access_object(user_id: str, object_id: str) -> bool:
    """Return True if *user_id* may read events for *object_id*.

    Rule: if the stored object carries a `created_by`, only that user
    qualifies. Objects that pre-date ownership tracking (`created_by`
    missing) remain accessible to any authenticated user — the project
    is still single-tenant in spirit (see ROADMAP v0.4 for true
    multi-tenant isolation).

    A missing object short-circuits to False: there is nothing to
    authorize against, and granting access would let a caller probe
    for object IDs.
    """
    if not user_id or not object_id:
        return False
    try:
        client = qdrant_manager.get_async_client()
        results = await QdrantManager.safe_retrieve(
            client,
            collection_name=COLLECTION_OBJECTS,
            ids=[object_id],
            with_payload=True,
            with_vectors=False,
        )
    except Exception:
        logger.exception("Object access check failed for object_id=%s", object_id)
        return False
    if not results:
        return False
    creator = _object_creator(dict(results[0].payload or {}))
    if creator is None:
        return True
    return creator == user_id
