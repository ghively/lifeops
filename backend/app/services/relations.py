"""Relation and reference synchronization helpers."""
import re
import uuid
from typing import List

from app.database.qdrant_client import qdrant_manager, QdrantManager
from app.services.embedding import embedding_service
from app.utils.time import utc_now_iso

BLOCK_REFERENCE_PATTERN = re.compile(r"\(\(([a-zA-Z0-9-]+)\)\)")
WIKI_LINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")


class RelationService:
    """Synchronizes block references and wiki-link relations."""

    async def list_relations_for_object(self, object_id: str):
        client = qdrant_manager.get_async_client()
        results = await client.scroll(
            collection_name="relations",
            scroll_filter={
                "should": [
                    {"key": "source_id", "match": {"value": object_id}},
                    {"key": "target_id", "match": {"value": object_id}},
                ]
            },
            limit=500,
            with_payload=True,
            with_vectors=False,
        )
        relations = []
        for point in results[0]:
            payload = dict(point.payload or {})
            payload["id"] = str(point.id)
            relations.append(payload)
        relations.sort(key=lambda item: item.get("created_at", ""))
        return relations

    async def delete_relation(self, relation_id: str):
        client = qdrant_manager.get_async_client()
        await client.delete(collection_name="relations", points_selector=[relation_id])

    async def remove_relations_for_entity(self, entity_id: str):
        relations = await self.list_relations_for_object(entity_id)
        for relation in relations:
            await self.delete_relation(relation["id"])

    async def create_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        source_type: str = "object",
        target_type: str = "object",
        context: str = "",
    ):
        client = qdrant_manager.get_async_client()
        await self._assert_entity_exists(source_type, source_id)
        await self._assert_entity_exists(target_type, target_id)
        relation_id = str(uuid.uuid4())
        try:
            embedding = await embedding_service.embed_text(context or relation_type)
        except Exception:
            embedding = await embedding_service.embed_text(relation_type)
        payload = {
            "id": relation_id,
            "source_id": source_id,
            "source_type": source_type,
            "target_id": target_id,
            "target_type": target_type,
            "relation_type": relation_type,
            "context": context,
            "created_at": utc_now_iso(),
        }
        await client.upsert(
            collection_name="relations",
            points=[{"id": relation_id, "vector": embedding.tolist(), "payload": payload}],
        )
        return payload

    async def sync_object_links(self, object_id: str, title: str = "", content: str = ""):
        client = qdrant_manager.get_async_client()
        existing = await self.list_relations_for_object(object_id)
        for relation in existing:
            if relation.get("source_id") == object_id and relation.get("relation_type") in {"links_to", "mentions"}:
                await self.delete_relation(relation["id"])

        seen_titles = set(self.extract_wiki_links(title + "\n" + content))
        for linked_title in seen_titles:
            target = await client.scroll(
                collection_name="objects",
                scroll_filter={"must": [{"key": "title", "match": {"value": linked_title}}]},
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
            if not target[0]:
                continue
            target_id = str(target[0][0].id)
            await self.create_relation(
                source_id=object_id,
                target_id=target_id,
                relation_type="links_to",
                context=linked_title,
            )

    async def sync_block_references(self, block_id: str, object_id: str, content: str):
        client = qdrant_manager.get_async_client()
        existing = await QdrantManager.safe_retrieve(client, 
            collection_name="blocks",
            ids=[block_id],
            with_payload=True,
            with_vectors=False,
        )
        if not existing:
            return [], []

        payload = dict(existing[0].payload or {})
        old_references = set(payload.get("references", []))
        new_references = set(self.extract_block_references(content))

        payload["references"] = sorted(new_references)
        payload["updated_at"] = utc_now_iso()
        await client.set_payload(collection_name="blocks", payload=payload, points=[block_id])

        for removed_id in old_references - new_references:
            await self._remove_back_reference(removed_id, block_id)

        for reference_id in new_references - old_references:
            # Only attempt back-reference for valid UUIDs — raw names like
            # ((target-block)) are stored as references but can't be looked up
            # in Qdrant until the referenced block actually exists.
            try:
                uuid.UUID(reference_id)
                await self._add_back_reference(reference_id, block_id)
                await self.create_relation(
                    source_id=block_id,
                    source_type="block",
                    target_id=reference_id,
                    target_type="block",
                    relation_type="references",
                    context=content[:500],
                )
            except (ValueError, AttributeError):
                pass

        relations = await self.list_relations_for_object(block_id)
        for relation in relations:
            if relation.get("source_id") == block_id and relation.get("relation_type") == "references":
                if relation.get("target_id") not in new_references:
                    await self.delete_relation(relation["id"])

        await self.sync_object_links(object_id=object_id, content=content)
        return sorted(new_references), list(old_references - new_references)

    async def remove_block_references(self, block_id: str):
        client = qdrant_manager.get_async_client()
        existing = await QdrantManager.safe_retrieve(client, 
            collection_name="blocks",
            ids=[block_id],
            with_payload=True,
            with_vectors=False,
        )
        if existing:
            for reference_id in existing[0].payload.get("references", []):
                try:
                    uuid.UUID(reference_id)
                    await self._remove_back_reference(reference_id, block_id)
                except (ValueError, AttributeError):
                    pass
        await self.remove_relations_for_entity(block_id)

    async def _add_back_reference(self, referenced_block_id: str, block_id: str):
        client = qdrant_manager.get_async_client()
        result = await QdrantManager.safe_retrieve(client, 
            collection_name="blocks",
            ids=[referenced_block_id],
            with_payload=True,
            with_vectors=False,
        )
        if not result:
            return
        payload = dict(result[0].payload or {})
        referenced_by = set(payload.get("referenced_by", []))
        referenced_by.add(block_id)
        payload["referenced_by"] = sorted(referenced_by)
        payload["updated_at"] = utc_now_iso()
        await client.set_payload(collection_name="blocks", payload=payload, points=[referenced_block_id])

    async def _remove_back_reference(self, referenced_block_id: str, block_id: str):
        client = qdrant_manager.get_async_client()
        result = await QdrantManager.safe_retrieve(client, 
            collection_name="blocks",
            ids=[referenced_block_id],
            with_payload=True,
            with_vectors=False,
        )
        if not result:
            return
        payload = dict(result[0].payload or {})
        referenced_by = set(payload.get("referenced_by", []))
        if block_id in referenced_by:
            referenced_by.remove(block_id)
            payload["referenced_by"] = sorted(referenced_by)
            payload["updated_at"] = utc_now_iso()
            await client.set_payload(collection_name="blocks", payload=payload, points=[referenced_block_id])

    @staticmethod
    def extract_block_references(content: str) -> List[str]:
        return BLOCK_REFERENCE_PATTERN.findall(content or "")

    @staticmethod
    def extract_wiki_links(content: str) -> List[str]:
        return [title.strip() for title in WIKI_LINK_PATTERN.findall(content or "") if title.strip()]

    async def _assert_entity_exists(self, entity_type: str, entity_id: str):
        collection = "objects" if entity_type == "object" else "blocks"
        client = qdrant_manager.get_async_client()
        result = await QdrantManager.safe_retrieve(client, 
            collection_name=collection,
            ids=[entity_id],
            with_payload=False,
            with_vectors=False,
        )
        if not result:
            raise ValueError(f"{entity_type} target not found: {entity_id}")


relation_service = RelationService()
