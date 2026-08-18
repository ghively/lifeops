"""Knowledge domain model (BUILD_SPEC sections 18, 36).

Section 18 wants "human/reference knowledge kept distinct from personal
memory": insurance policies, school handbooks, contracts, warranties,
quotes, household notes, checklists, user-written procedures. That is
self-contained reference text, which is what separates it from the other
two content-shaped entities already in the world graph:

  * ``Memory`` (domain/memory.py) is a fact LifeOps *observed* about the
    user's life, temporal and provenance-tracked (section 42-47).
  * ``Document`` (domain/documents.py) is a *pointer* to something ingested
    from email or the calendar — LifeOps stores a reference and a summary,
    never the content itself.

Knowledge is neither: it is the content, authored by the user or distilled
from a Document, with no temporal supersession chain (like Document, and
unlike Preference/Memory) because a knowledge article is edited in place,
not restated. Section 18 also says "initial extraction should remain
simple" and warns against a heavyweight document-processing stack — so this
is a facts-bag entity like Document, not a chunked/embedded store.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from lifeops.domain.world import WorldEntity, WorldEntityType
from lifeops.errors import ValidationError
from lifeops.ids import new_knowledge_id


class Knowledge(BaseModel):
    """One piece of reference content (section 36)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    #: Free text, not a closed taxonomy — section 18's examples (insurance,
    #: warranty, checklist, procedure...) are illustrative, not exhaustive.
    category: str = ""
    #: The reference text itself: a checklist, a procedure, household notes.
    #: Bounded, not chunked — section 18 defers real extraction until a real
    #: document needs it.
    content: str = ""
    #: An optional pointer back to the Document this was distilled from.
    source_document_id: str | None = None

    created_at: str
    updated_at: str
    created_by_client: str | None = None

    @staticmethod
    def make_id() -> str:
        return new_knowledge_id()


class KnowledgeDraft(BaseModel):
    """Input shape for recording a piece of knowledge."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    category: str = Field(default="", max_length=100)
    content: str = Field(default="", max_length=8000)
    source_document_id: str | None = None


def create_knowledge(draft: KnowledgeDraft, *, now: str, client_id: str) -> Knowledge:
    return Knowledge(
        id=Knowledge.make_id(),
        title=draft.title.strip(),
        category=draft.category.strip(),
        content=draft.content.strip(),
        source_document_id=draft.source_document_id,
        created_at=now,
        updated_at=now,
        created_by_client=client_id,
    )


def knowledge_to_entity(knowledge: Knowledge) -> WorldEntity:
    return WorldEntity(
        id=knowledge.id,
        entity_type=WorldEntityType.KNOWLEDGE,
        display_name=knowledge.title,
        facts={
            "category": knowledge.category,
            "content": knowledge.content,
            "source_document_id": knowledge.source_document_id or "",
        },
        created_at=knowledge.created_at,
        updated_at=knowledge.updated_at,
        created_by_client=knowledge.created_by_client,
    )


def entity_to_knowledge(entity: WorldEntity) -> Knowledge:
    if entity.entity_type is not WorldEntityType.KNOWLEDGE:
        raise ValidationError(f"{entity.id} is not knowledge", entity_id=entity.id)
    facts = entity.facts
    return Knowledge(
        id=entity.id,
        title=entity.display_name,
        category=facts.get("category", ""),
        content=facts.get("content", ""),
        source_document_id=facts.get("source_document_id") or None,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        created_by_client=entity.created_by_client,
    )
