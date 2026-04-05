"""Context Builder Service - Builds context packages for agent tasks."""
import logging
from typing import Dict, List, Optional

from app.database.qdrant_client import qdrant_manager
from app.database.sqlite import sqlite_manager
from app.services.embedding import embedding_service

logger = logging.getLogger(__name__)


class ContextBuilder:
    """Builds context for task assignment."""

    @staticmethod
    def _estimate_token_count(value) -> int:
        return max(1, len(str(value)) // 4) if value else 0

    def _context_token_count(self, context: Dict) -> int:
        return self._estimate_token_count(context)

    def _truncate_to_token_limit(self, context: Dict) -> Dict:
        max_tokens = int(context.get("max_context_tokens") or 4000)
        token_count_estimate = self._context_token_count(context)
        if token_count_estimate <= max_tokens:
            context["token_count_estimate"] = token_count_estimate
            return context

        truncation_fields = [
            ("linked_objects", "linked_object_ids", "objects"),
            ("related_files", "related_file_ids", "files"),
            ("relevant_memories", "agent_memory_ids", "agent_memories"),
            ("recent_chat", "recent_chat_ids", "chat_logs"),
        ]

        for field_name, pointer_name, collection_name in truncation_fields:
            while context.get(field_name) and token_count_estimate > max_tokens:
                removed_item = context[field_name].pop()
                removed_id = removed_item.get("id")
                context["qdrant_pointers"][pointer_name] = [item["id"] for item in context.get(field_name, [])]
                context["qdrant_pointer_entries"] = [
                    entry
                    for entry in context.get("qdrant_pointer_entries", [])
                    if not (entry.get("collection") == collection_name and entry.get("id") == removed_id)
                ]
                token_count_estimate = self._context_token_count(context)
            if token_count_estimate <= max_tokens:
                break

        if token_count_estimate > max_tokens:
            logger.warning(
                "Context for task %s still exceeds token limit after truncation: estimated=%s max=%s",
                context.get("task_id"),
                token_count_estimate,
                max_tokens,
            )
        else:
            logger.warning(
                "Context for task %s truncated to fit token limit: estimated=%s max=%s",
                context.get("task_id"),
                token_count_estimate,
                max_tokens,
            )

        context["token_count_estimate"] = token_count_estimate
        return context

    async def build_task_context(
        self,
        task_id: str,
        additional_objects: Optional[List[str]] = None,
    ) -> Dict:
        client = qdrant_manager.get_async_client()
        settings = await sqlite_manager.get_setting("max_context_tokens", 4000)
        context = {
            "task_id": task_id,
            "task_title": None,
            "task_content": None,
            "priority": None,
            "task": None,
            "parent_object": None,
            "linked_objects": [],
            "related_files": [],
            "relevant_memories": [],
            "agent_memories": [],
            "recent_chat": [],
            "additional_context_objects": [],
            "qdrant_pointers": {},
            "qdrant_pointer_entries": [],
            "max_context_tokens": settings,
        }

        task_result = await client.retrieve(
            collection_name="objects",
            ids=[task_id],
            with_payload=True,
            with_vectors=False,
        )
        if not task_result:
            return context

        task_payload = dict(task_result[0].payload or {})
        task_payload["id"] = str(task_result[0].id)
        context["task"] = task_payload
        context["task_title"] = task_payload.get("title")
        context["task_content"] = task_payload.get("content")
        context["priority"] = task_payload.get("properties", {}).get("priority")
        context["qdrant_pointers"]["task_object_id"] = task_id
        context["qdrant_pointer_entries"].append({"collection": "objects", "id": task_id})

        properties = task_payload.get("properties", {})
        parent_id = properties.get("parent_id")
        linked_ids = list(dict.fromkeys(properties.get("linked_objects", []) + (additional_objects or [])))

        if parent_id:
            parent = await self._get_pointer("objects", parent_id)
            if parent:
                context["parent_object"] = parent
                context["qdrant_pointers"]["parent_object_id"] = parent["id"]
                context["qdrant_pointer_entries"].append({"collection": "objects", "id": parent["id"]})

        for object_id in linked_ids:
            linked = await self._get_pointer("objects", object_id)
            if linked:
                if object_id in (additional_objects or []):
                    context["additional_context_objects"].append(linked)
                else:
                    context["linked_objects"].append(linked)
                context["qdrant_pointer_entries"].append({"collection": "objects", "id": linked["id"]})
        context["qdrant_pointers"]["linked_object_ids"] = [item["id"] for item in context["linked_objects"]]
        context["qdrant_pointers"]["additional_context_object_ids"] = [
            item["id"] for item in context["additional_context_objects"]
        ]

        query_text = task_payload.get("content") or task_payload.get("title", "")
        if query_text:
            query_embedding = await embedding_service.embed_text(query_text)
            file_results = await client.search(
                collection_name="files",
                query_vector=query_embedding.tolist(),
                limit=5,
                with_payload=True,
                with_vectors=False,
            )
            for point in file_results:
                payload = dict(point.payload or {})
                payload["id"] = str(point.id)
                payload["score"] = point.score
                context["related_files"].append(payload)
                context["qdrant_pointer_entries"].append({"collection": "files", "id": payload["id"]})
        context["qdrant_pointers"]["related_file_ids"] = [item["id"] for item in context["related_files"]]

        assigned_to = properties.get("assigned_to")
        if assigned_to:
            memories = await client.scroll(
                collection_name="agent_memories",
                scroll_filter={"must": [{"key": "agent_name", "match": {"value": assigned_to}}]},
                limit=10,
                with_payload=True,
                with_vectors=False,
            )
            for point in memories[0]:
                payload = dict(point.payload or {})
                payload["id"] = str(point.id)
                context["relevant_memories"].append(payload)
                context["agent_memories"].append(payload)
                context["qdrant_pointer_entries"].append({"collection": "agent_memories", "id": payload["id"]})

            chat = await client.scroll(
                collection_name="chat_logs",
                scroll_filter={"must": [{"key": "agent_name", "match": {"value": assigned_to}}]},
                limit=10,
                with_payload=True,
                with_vectors=False,
            )
            recent = []
            for point in chat[0]:
                payload = dict(point.payload or {})
                payload["id"] = str(point.id)
                recent.append(payload)
                context["qdrant_pointer_entries"].append({"collection": "chat_logs", "id": payload["id"]})
            context["recent_chat"] = sorted(recent, key=lambda item: item.get("timestamp", ""))[-10:]
            context["qdrant_pointers"]["agent_memory_ids"] = [item["id"] for item in context["relevant_memories"]]
            context["qdrant_pointers"]["recent_chat_ids"] = [item["id"] for item in context["recent_chat"]]

        return self._truncate_to_token_limit(context)

    async def _get_pointer(self, collection: str, object_id: str):
        client = qdrant_manager.get_async_client()
        result = await client.retrieve(
            collection_name=collection,
            ids=[object_id],
            with_payload=True,
            with_vectors=False,
        )
        if not result:
            return None
        payload = dict(result[0].payload or {})
        payload["id"] = str(result[0].id)
        return payload


context_builder = ContextBuilder()
