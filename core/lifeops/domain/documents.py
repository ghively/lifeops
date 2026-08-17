"""Document domain model (BUILD_SPEC sections 36, 64, 96).

Section 64 gives email two capabilities this module exists to satisfy:
"associate message with task/provider/entity" and "ingest relevant
observations". A Document is the durable record of the first — a reference to
something an email or calendar read produced (an attachment, a confirmation,
the body of a message worth keeping) that a task, provider, or other entity can
point at. Associating it with a task or entity is an ordinary ``LINK``
(``REFERENCES``/``ABOUT``, section 39's existing vocabulary), not a new
relationship type — section 39 warns against inventing more than the spec
already lists.

Unlike ``Appointment``, a Document has no lifecycle: it is created once and
read thereafter, so it goes through the same lightweight facts-bag shape as
Household/Provider/Asset rather than earning its own status machine.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from lifeops.domain.world import WorldEntity, WorldEntityType
from lifeops.errors import ValidationError
from lifeops.ids import new_document_id


class Document(BaseModel):
    """A reference to content ingested from email, the calendar, or elsewhere
    (section 36). LifeOps stores the reference and a summary, never the raw
    content — this is a pointer, not a file store."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    #: Where this came from: "email", "calendar", or "manual".
    source: str
    #: The source system's own identifier — a message id, an event id —
    #: so a document can be traced back to what produced it.
    source_ref: str = ""
    mime_type: str = ""
    summary: str = ""

    created_at: str
    updated_at: str
    created_by_client: str | None = None

    @staticmethod
    def make_id() -> str:
        return new_document_id()


_KNOWN_SOURCES = frozenset({"email", "calendar", "manual"})


class DocumentDraft(BaseModel):
    """Input shape for recording a document reference."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    source: str = Field(min_length=1, max_length=50)
    source_ref: str = Field(default="", max_length=500)
    mime_type: str = Field(default="", max_length=200)
    summary: str = Field(default="", max_length=4000)


def validate_source(source: str) -> str:
    cleaned = source.strip().lower()
    if cleaned not in _KNOWN_SOURCES:
        raise ValidationError(
            f"unknown document source: {source!r}",
            field="source",
            allowed=sorted(_KNOWN_SOURCES),
        )
    return cleaned


def create_document(draft: DocumentDraft, *, now: str, client_id: str) -> Document:
    return Document(
        id=Document.make_id(),
        title=draft.title.strip(),
        source=validate_source(draft.source),
        source_ref=draft.source_ref.strip(),
        mime_type=draft.mime_type.strip(),
        summary=draft.summary.strip(),
        created_at=now,
        updated_at=now,
        created_by_client=client_id,
    )


def document_to_entity(document: Document) -> WorldEntity:
    return WorldEntity(
        id=document.id,
        entity_type=WorldEntityType.DOCUMENT,
        display_name=document.title,
        facts={
            "source": document.source,
            "source_ref": document.source_ref,
            "mime_type": document.mime_type,
            "summary": document.summary,
        },
        created_at=document.created_at,
        updated_at=document.updated_at,
        created_by_client=document.created_by_client,
    )


def entity_to_document(entity: WorldEntity) -> Document:
    if entity.entity_type is not WorldEntityType.DOCUMENT:
        raise ValidationError(f"{entity.id} is not a document", entity_id=entity.id)
    facts = entity.facts
    return Document(
        id=entity.id,
        title=entity.display_name,
        source=facts.get("source", "manual"),
        source_ref=facts.get("source_ref", ""),
        mime_type=facts.get("mime_type", ""),
        summary=facts.get("summary", ""),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        created_by_client=entity.created_by_client,
    )
