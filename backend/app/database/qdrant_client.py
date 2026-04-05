"""Qdrant Database Manager"""
import logging

from qdrant_client import QdrantClient, AsyncQdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PayloadSchemaType
)
from typing import Optional, Dict, Any

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


class QdrantManager:
    """Manages Qdrant connection and collections"""
    
    def __init__(self):
        self.client: Optional[QdrantClient] = None
        self.async_client: Optional[AsyncQdrantClient] = None
    
    async def initialize(self):
        """Initialize Qdrant connection and create collections"""
        # Sync client for initialization
        self.client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            api_key=settings.qdrant_api_key or None,
            prefer_grpc=False
        )
        
        # Async client for async operations
        self.async_client = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            api_key=settings.qdrant_api_key or None,
            prefer_grpc=False
        )
        
        # Create collections if they don't exist
        for collection_name, config in COLLECTIONS.items():
            await self._ensure_collection(collection_name, config)
        
        logger.info(f"Qdrant initialized with {len(COLLECTIONS)} collections")
    
    async def _ensure_collection(self, name: str, config: Dict[str, Any]):
        """Ensure a collection exists"""
        try:
            # Check if collection exists
            collections = self.client.get_collections().collections
            exists = any(c.name == name for c in collections)
            
            if not exists:
                logger.info(f"Creating collection: {name}")
                
                # Create collection
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(
                        size=config["vector_size"],
                        distance=config["distance"]
                    ),
                    on_disk_payload=config.get("on_disk_payload", False)
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
                self.client.create_payload_index(
                    collection_name=name,
                    field_name=field_name,
                    field_schema=field_schema,
                    wait=True,
                )
            except Exception as exc:
                logger.warning("Payload index skipped for %s.%s: %s", name, field_name, exc)
    
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
