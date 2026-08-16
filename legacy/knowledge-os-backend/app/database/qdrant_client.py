"""Qdrant Database Manager"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

from app.config import settings

logger = logging.getLogger(__name__)


# Collection configurations
COLLECTIONS = {
    "objects": {
        "vector_size": 384,
        "distance": Distance.COSINE,
        "on_disk_payload": False,
    },
    "blocks": {
        "vector_size": 384,
        "distance": Distance.COSINE,
        "on_disk_payload": False,
    },
    "relations": {
        "vector_size": 384,
        "distance": Distance.COSINE,
        "on_disk_payload": False,
    },
    "files": {
        "vector_size": 384,
        "distance": Distance.COSINE,
        "on_disk_payload": True,
    },
    "images": {
        "vector_size": 512,
        "distance": Distance.COSINE,
        "on_disk_payload": True,
    },
    "code": {
        "vector_size": 384,
        "distance": Distance.COSINE,
        "on_disk_payload": True,
    },
    "agent_memories": {
        "vector_size": 384,
        "distance": Distance.COSINE,
        "on_disk_payload": False,
    },
    "chat_logs": {
        "vector_size": 384,
        "distance": Distance.COSINE,
        "on_disk_payload": False,
    },
}


class CircuitBreaker:
    """Circuit breaker for Qdrant operations (H22).

    States:
      CLOSED  — normal operation
      OPEN    — all calls short-circuit immediately
      HALF-OPEN — allows a single probe to test recovery
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max: int = 1,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._state = "CLOSED"  # CLOSED | OPEN | HALF-OPEN
        self._half_open_successes = 0

    @property
    def state(self) -> str:
        if self._state == "OPEN":
            if self._last_failure_time and (time.monotonic() - self._last_failure_time >= self.recovery_timeout):
                self._state = "HALF-OPEN"
                self._half_open_successes = 0
                logger.info("Circuit breaker entering HALF-OPEN state")
        return self._state

    def record_success(self) -> None:
        self._failure_count = 0
        if self._state == "HALF-OPEN":
            self._half_open_successes += 1
            if self._half_open_successes >= self.half_open_max:
                self._state = "CLOSED"
                logger.info("Circuit breaker recovered to CLOSED state")

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = "OPEN"
            logger.warning("Circuit breaker opened after %d consecutive failures", self._failure_count)

    @property
    def is_open(self) -> bool:
        return self.state == "OPEN"


class QdrantManager:
    """Manages Qdrant connection and collections"""

    # Reconnection settings (H20)
    _MAX_RETRIES = 5
    _BASE_DELAY = 1.0  # seconds

    def __init__(self):
        self.client: Optional[QdrantClient] = None
        self.async_client: Optional[AsyncQdrantClient] = None
        self._circuit_breaker = CircuitBreaker()
        # Cache of actual vector sizes fetched from Qdrant (H21)
        self._vector_sizes: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # H20: reconnection helper with exponential backoff
    # ------------------------------------------------------------------
    def _reconnect_sync(self) -> bool:
        """Attempt to re-establish the sync Qdrant connection. Returns True on success."""
        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                if self.client:
                    self.client.close()
                self.client = QdrantClient(
                    host=settings.qdrant_host,
                    port=settings.qdrant_port,
                    api_key=settings.qdrant_api_key or None,
                    prefer_grpc=False,
                    timeout=30.0,
                )
                # Verify connection
                self.client.get_collections()
                logger.info("Qdrant sync client reconnected (attempt %d)", attempt)
                self._circuit_breaker.record_success()
                return True
            except Exception as exc:
                delay = self._BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "Qdrant reconnect attempt %d/%d failed: %s — retrying in %.1fs",
                    attempt,
                    self._MAX_RETRIES,
                    exc,
                    delay,
                )
                time.sleep(delay)
        self._circuit_breaker.record_failure()
        return False

    async def _reconnect_async(self) -> bool:
        """Attempt to re-establish the async Qdrant connection. Returns True on success."""
        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                if self.async_client:
                    await self.async_client.close()
                self.async_client = AsyncQdrantClient(
                    host=settings.qdrant_host,
                    port=settings.qdrant_port,
                    api_key=settings.qdrant_api_key or None,
                    prefer_grpc=False,
                    timeout=30.0,
                )
                await self.async_client.get_collections()
                logger.info("Qdrant async client reconnected (attempt %d)", attempt)
                self._circuit_breaker.record_success()
                return True
            except Exception as exc:
                delay = self._BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "Qdrant async reconnect attempt %d/%d failed: %s — retrying in %.1fs",
                    attempt,
                    self._MAX_RETRIES,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
        self._circuit_breaker.record_failure()
        return False

    async def initialize(self):
        """Initialize Qdrant connection and create collections"""
        try:
            self.client = QdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
                api_key=settings.qdrant_api_key or None,
                prefer_grpc=False,
                timeout=30.0,
            )
            self.async_client = AsyncQdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
                api_key=settings.qdrant_api_key or None,
                prefer_grpc=False,
                timeout=30.0,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to connect to Qdrant at {settings.qdrant_host}:{settings.qdrant_port}. "
                f"Ensure Qdrant is running. Error: {exc}"
            ) from exc

        for collection_name, config in COLLECTIONS.items():
            await self._ensure_collection(collection_name, config)

        logger.info(f"Qdrant initialized with {len(COLLECTIONS)} collections")

    # ------------------------------------------------------------------
    # H19: wrap all sync-client calls in asyncio.to_thread()
    # ------------------------------------------------------------------
    async def _ensure_collection(self, name: str, config: Dict[str, Any]):
        """Ensure a collection exists"""
        try:
            collections = await asyncio.to_thread(lambda: self.client.get_collections().collections)
            exists = any(c.name == name for c in collections)

            if not exists:
                logger.info(f"Creating collection: {name}")
                await asyncio.to_thread(
                    self.client.create_collection,
                    collection_name=name,
                    vectors_config=VectorParams(
                        size=config["vector_size"],
                        distance=config["distance"],
                    ),
                    on_disk_payload=config.get("on_disk_payload", False),
                )
                logger.info(f"Created collection: {name}")

            await self._ensure_payload_indexes(name)
        except Exception as e:
            logger.error(f"Error ensuring collection {name}: {e}")
            raise

    async def _ensure_payload_indexes(self, name: str):
        """Ensure required payload indexes exist for a collection."""
        index_map = {
            "objects": {
                "type": PayloadSchemaType.KEYWORD,
                "title": PayloadSchemaType.TEXT,
                "properties.tags": PayloadSchemaType.KEYWORD,
                "properties.mentions": PayloadSchemaType.KEYWORD,
                "properties.status": PayloadSchemaType.KEYWORD,
                "properties.priority": PayloadSchemaType.KEYWORD,
                "properties.assigned_to": PayloadSchemaType.KEYWORD,
                "properties.agent_name": PayloadSchemaType.KEYWORD,
                "properties.agent_status": PayloadSchemaType.KEYWORD,
            },
            "blocks": {
                "object_id": PayloadSchemaType.KEYWORD,
                "type": PayloadSchemaType.KEYWORD,
                "parent_id": PayloadSchemaType.KEYWORD,
                "references": PayloadSchemaType.KEYWORD,
                "referenced_by": PayloadSchemaType.KEYWORD,
                "content": PayloadSchemaType.TEXT,
            },
            "relations": {
                "source_id": PayloadSchemaType.KEYWORD,
                "target_id": PayloadSchemaType.KEYWORD,
                "relation_type": PayloadSchemaType.KEYWORD,
                "source_type": PayloadSchemaType.KEYWORD,
                "target_type": PayloadSchemaType.KEYWORD,
                "context": PayloadSchemaType.TEXT,
            },
            "files": {
                "object_id": PayloadSchemaType.KEYWORD,
                "path": PayloadSchemaType.KEYWORD,
                "filename": PayloadSchemaType.KEYWORD,
                "extension": PayloadSchemaType.KEYWORD,
                "mime_type": PayloadSchemaType.KEYWORD,
                "index_status": PayloadSchemaType.KEYWORD,
                "content_text": PayloadSchemaType.TEXT,
            },
            "images": {
                "object_id": PayloadSchemaType.KEYWORD,
                "path": PayloadSchemaType.KEYWORD,
                "filename": PayloadSchemaType.KEYWORD,
                "tags": PayloadSchemaType.KEYWORD,
            },
            "code": {
                "file_id": PayloadSchemaType.KEYWORD,
                "object_id": PayloadSchemaType.KEYWORD,
                "file_path": PayloadSchemaType.KEYWORD,
                "language": PayloadSchemaType.KEYWORD,
                "type": PayloadSchemaType.KEYWORD,
                "name": PayloadSchemaType.KEYWORD,
                "content": PayloadSchemaType.TEXT,
            },
            "agent_memories": {
                "agent_name": PayloadSchemaType.KEYWORD,
                "memory_type": PayloadSchemaType.KEYWORD,
                "related_objects": PayloadSchemaType.KEYWORD,
                "related_tasks": PayloadSchemaType.KEYWORD,
                "content": PayloadSchemaType.TEXT,
            },
            "chat_logs": {
                "session_id": PayloadSchemaType.KEYWORD,
                "agent_name": PayloadSchemaType.KEYWORD,
                "message_type": PayloadSchemaType.KEYWORD,
                "related_task": PayloadSchemaType.KEYWORD,
                "content": PayloadSchemaType.TEXT,
            },
        }

        for field_name, field_schema in index_map.get(name, {}).items():
            try:
                await asyncio.to_thread(
                    self.client.create_payload_index,
                    collection_name=name,
                    field_name=field_name,
                    field_schema=field_schema,
                    wait=True,
                )
            except Exception as exc:
                logger.warning("Payload index skipped for %s.%s: %s", name, field_name, exc)

    # ------------------------------------------------------------------
    # H21: runtime vector dimension validation
    # ------------------------------------------------------------------
    def _get_collection_vector_size(self, collection_name: str) -> Optional[int]:
        """Fetch and cache the actual vector size of a collection from Qdrant."""
        if collection_name in self._vector_sizes:
            return self._vector_sizes[collection_name]
        try:
            info = self.client.get_collection(collection_name)
            # config.params.vectors may be a dict or VectorParams
            vectors_config = info.config.params.vectors
            if isinstance(vectors_config, dict):
                size = vectors_config.get("size")
            elif vectors_config is not None:
                size = getattr(vectors_config, "size", None)
            else:
                size = None
            if size is not None:
                self._vector_sizes[collection_name] = size
            return size
        except Exception as exc:
            logger.warning("Could not fetch vector size for %s: %s", collection_name, exc)
            return None

    def validate_vector(self, collection_name: str, vector: List[float], context: str = "") -> bool:
        """Validate that a vector's dimensions match the collection's config (H21).

        Returns True if valid or if validation cannot be performed (graceful).
        Logs a warning and returns False on mismatch.
        """
        expected = self._get_collection_vector_size(collection_name)
        if expected is None:
            return True  # can't validate — don't block
        actual = len(vector)
        if actual != expected:
            logger.warning(
                "Vector dimension mismatch for %s%s: expected %d, got %d",
                collection_name,
                f" ({context})" if context else "",
                expected,
                actual,
            )
            return False
        return True

    # ------------------------------------------------------------------
    # H22: circuit-breaker-aware wrappers for common operations
    # ------------------------------------------------------------------
    async def upsert(
        self,
        collection_name: str,
        points: list,
    ) -> bool:
        """Upsert points with circuit breaker protection (H22)."""
        if self._circuit_breaker.is_open:
            logger.warning("Circuit breaker OPEN — skipping upsert to %s", collection_name)
            return False
        try:
            if self.async_client:
                await self.async_client.upsert(collection_name=collection_name, points=points)
            else:
                await asyncio.to_thread(self.client.upsert, collection_name=collection_name, points=points)
            self._circuit_breaker.record_success()
            return True
        except Exception as exc:
            logger.error("Upsert to %s failed: %s", collection_name, exc)
            self._circuit_breaker.record_failure()
            # Attempt reconnect (H20)
            await self._reconnect_async()
            return False

    async def search(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int = 10,
        **kwargs,
    ) -> list:
        """Search with circuit breaker protection (H22)."""
        if self._circuit_breaker.is_open:
            logger.warning("Circuit breaker OPEN — skipping search on %s", collection_name)
            return []
        # H21: validate vector dimensions
        if not self.validate_vector(collection_name, query_vector, context="search"):
            return []
        try:
            if self.async_client:
                return await self.async_client.search(
                    collection_name=collection_name,
                    query_vector=query_vector,
                    limit=limit,
                    **kwargs,
                )
            else:
                return await asyncio.to_thread(
                    self.client.search,
                    collection_name=collection_name,
                    query_vector=query_vector,
                    limit=limit,
                    **kwargs,
                )
        except Exception as exc:
            logger.error("Search on %s failed: %s", collection_name, exc)
            self._circuit_breaker.record_failure()
            await self._reconnect_async()
            return []

    async def close(self):
        """Close connections"""
        if self.client:
            self.client.close()
        if self.async_client:
            await self.async_client.close()
        logger.info("Qdrant connections closed")

    # Convenience methods
    def get_client(self) -> QdrantClient:
        """Get sync client"""
        return self.client

    def get_async_client(self) -> AsyncQdrantClient:
        """Get async client"""
        return self.async_client

    @staticmethod
    async def safe_retrieve(client, *, collection_name: str, ids: list, **kwargs):
        """Retrieve points, returning empty list for invalid IDs instead of raising.

        Qdrant rejects non-UUID/non-integer IDs with a 400 error.
        This wrapper catches that and returns an empty list, so callers
        can treat "invalid ID" the same as "not found" (404).
        """
        try:
            return await client.retrieve(
                collection_name=collection_name,
                ids=ids,
                **kwargs,
            )
        except Exception as exc:
            error_str = str(exc).lower()
            if "not a valid point id" in error_str or "bad request" in error_str:
                logger.debug("safe_retrieve: invalid ID(s) %s in %s: %s", ids, collection_name, exc)
                return []
            raise


# Global instance
qdrant_manager = QdrantManager()
