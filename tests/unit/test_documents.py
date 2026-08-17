"""Document domain rules (BUILD_SPEC sections 36, 64, 96)."""

from __future__ import annotations

import pytest

from lifeops.domain.documents import (
    Document,
    DocumentDraft,
    create_document,
    document_to_entity,
    entity_to_document,
    validate_source,
)
from lifeops.domain.world import WorldEntityType
from lifeops.errors import ValidationError

NOW = "2026-08-17T12:00:00Z"


class TestSourceValidation:
    @pytest.mark.parametrize("source", ["email", "calendar", "manual"])
    def test_known_sources_are_accepted(self, source: str) -> None:
        assert validate_source(source) == source

    def test_an_unknown_source_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_source("dropbox")

    def test_source_is_normalised(self) -> None:
        assert validate_source(" Email ") == "email"


class TestCreation:
    def test_creating_a_document_stamps_provenance(self) -> None:
        document = create_document(
            DocumentDraft(
                title="ABC Electric quote",
                source="email",
                source_ref="msg-123",
                summary="Quote for panel upgrade: $2,400",
            ),
            now=NOW,
            client_id="hermes-personal",
        )
        assert document.title == "ABC Electric quote"
        assert document.source == "email"
        assert document.created_by_client == "hermes-personal"
        assert document.created_at == NOW


class TestWorldProjection:
    def test_a_document_round_trips_through_world_entity_facts(self) -> None:
        document = Document(
            id="document_01",
            title="Furnace warranty",
            source="email",
            source_ref="msg-9",
            mime_type="application/pdf",
            summary="5-year parts warranty",
            created_at=NOW,
            updated_at=NOW,
            created_by_client="hermes-personal",
        )
        entity = document_to_entity(document)
        assert entity.entity_type is WorldEntityType.DOCUMENT
        assert entity.display_name == document.title
        assert all(isinstance(v, str) for v in entity.facts.values())

        restored = entity_to_document(entity)
        assert restored.source == "email"
        assert restored.source_ref == "msg-9"
        assert restored.summary == document.summary
