"""Knowledge domain rules (BUILD_SPEC sections 18, 36)."""

from __future__ import annotations

import pytest

from lifeops.domain.knowledge import (
    Knowledge,
    KnowledgeDraft,
    create_knowledge,
    entity_to_knowledge,
    knowledge_to_entity,
)
from lifeops.domain.world import WorldEntityType
from lifeops.errors import ValidationError

NOW = "2026-08-18T12:00:00Z"


class TestCreation:
    def test_creating_knowledge_stamps_provenance(self) -> None:
        knowledge = create_knowledge(
            KnowledgeDraft(
                title="Water heater warranty",
                category="warranty",
                content="10-year tank warranty, registered 2024-03-01.",
            ),
            now=NOW,
            client_id="hermes-personal",
        )
        assert knowledge.title == "Water heater warranty"
        assert knowledge.category == "warranty"
        assert knowledge.created_by_client == "hermes-personal"
        assert knowledge.created_at == NOW

    def test_title_and_content_are_stripped(self) -> None:
        knowledge = create_knowledge(
            KnowledgeDraft(title="  Trash day  ", content=" Tuesdays and Fridays "),
            now=NOW,
            client_id="console",
        )
        assert knowledge.title == "Trash day"
        assert knowledge.content == "Tuesdays and Fridays"


class TestWorldProjection:
    def test_knowledge_round_trips_through_world_entity_facts(self) -> None:
        knowledge = Knowledge(
            id="knowledge_01",
            title="Sump pump checklist",
            category="checklist",
            content="1. Test the float switch.\n2. Clear the discharge line.",
            source_document_id="document_9",
            created_at=NOW,
            updated_at=NOW,
            created_by_client="console",
        )
        entity = knowledge_to_entity(knowledge)
        assert entity.entity_type is WorldEntityType.KNOWLEDGE
        assert entity.display_name == knowledge.title
        assert all(isinstance(v, str) for v in entity.facts.values())

        restored = entity_to_knowledge(entity)
        assert restored.category == "checklist"
        assert restored.content == knowledge.content
        assert restored.source_document_id == "document_9"

    def test_a_missing_source_document_id_round_trips_as_none(self) -> None:
        knowledge = create_knowledge(
            KnowledgeDraft(title="Trash day", content="Tuesdays and Fridays"),
            now=NOW,
            client_id="console",
        )
        restored = entity_to_knowledge(knowledge_to_entity(knowledge))
        assert restored.source_document_id is None

    def test_a_non_knowledge_entity_is_rejected(self) -> None:
        knowledge = create_knowledge(
            KnowledgeDraft(title="Trash day"), now=NOW, client_id="console"
        )
        entity = knowledge_to_entity(knowledge)
        entity.entity_type = WorldEntityType.DOCUMENT
        with pytest.raises(ValidationError):
            entity_to_knowledge(entity)
