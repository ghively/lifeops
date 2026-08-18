"""World domain model — entities, relationships, and the graph read model
(BUILD_SPEC sections 36–40, 92).

Phase 3 adds Household, Provider, and Asset alongside the existing Person.
The three new types share one shape deliberately: ``id``, ``entity_type``,
``display_name``, a ``facts`` bag of current key facts, and timestamps. Splitting
them into three near-identical classes now would be modelling a difference that
no workflow has asked for yet (section 36: only add what a real workflow needs).

Two kinds of rules live here rather than in adapters:

  * Validation — display names, the facts bag, and relationship vocabulary are
    checked by pure functions so HTTP and MCP get identical behaviour.

  * Graph assembly — turning repository rows into the ``WorldGraph`` read model
    (dedup, dangling-edge drops, limit caps) is a domain transformation, not a
    Cypher concern.

Persons are part of the world graph but keep their own richer model in
``domain/people.py``; here they appear as graph projections (empty ``facts``).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from lifeops.domain.memory import MemoryRecord
from lifeops.domain.tasks import Task
from lifeops.errors import ValidationError
from lifeops.ids import (
    PREFIX_APPOINTMENT,
    PREFIX_ASSET,
    PREFIX_DOCUMENT,
    PREFIX_EVENT,
    PREFIX_HOUSEHOLD,
    PREFIX_KNOWLEDGE,
    PREFIX_PERSON,
    PREFIX_PREFERENCE,
    PREFIX_PROVIDER,
    PREFIX_SERVICE_REQUEST,
    PREFIX_SHOPPING_LIST,
    is_valid_id,
    new_ulid_id,
    slug_id,
)

#: Not centrally registered in lifeops.ids, the same way
#: domain/self_config.py's PREFIX_CHANGE_REQUEST is local to that module —
#: an EntityFact is never addressed on its own by a caller, only read back
#: as part of an entity's history, so it needs no place in the shared
#: prefix->type lookup ``is_world_entity_id`` uses.
PREFIX_ENTITY_FACT = "fact"


class WorldEntityType(StrEnum):
    """The section 36 entity types the world graph renders.

    Phase 3 scoped this to people, households, providers, and assets.
    ``PREFERENCE`` joins them because section 15's World screen draws one —
    ``Gene ─PREFERS→ "After 10 AM"`` — and the ``PREFERS`` edge is already
    written by the preference layer. Phase 7 adds ``APPOINTMENT``, ``EVENT``,
    and ``DOCUMENT`` (section 96): a booked-or-held calendar commitment, a
    read-only projection of what is on the calendar, and a reference to
    something ingested from email or the calendar (an attachment, a
    confirmation). Phase 8 (section 97) adds ``SERVICE_REQUEST``: the durable
    record of one provider workflow — research, contact, quote collection,
    approval-gated booking (section 67, section 101's electrician scenario).
    Phase 9 (section 98) adds ``SHOPPING_LIST``: a cart being assembled,
    checked out, and verified through the same outbox two actions drive
    (``build_grocery_cart``, ``submit_grocery_order``). ``KNOWLEDGE`` closes
    section 18's gap: reference content the user authored or a Document
    distilled — insurance policies, warranties, checklists, procedures —
    kept distinct from Memory (personal facts LifeOps observed about the
    user's life) and Document (a pointer to something ingested, not
    self-contained text). The remaining section 36 types are owned by phases
    that have not landed; each arrives with the phase that creates it.
    """

    PERSON = "person"
    HOUSEHOLD = "household"
    PROVIDER = "provider"
    ASSET = "asset"
    PREFERENCE = "preference"
    APPOINTMENT = "appointment"
    EVENT = "event"
    DOCUMENT = "document"
    SERVICE_REQUEST = "service_request"
    SHOPPING_LIST = "shopping_list"
    KNOWLEDGE = "knowledge"


#: The types ``create_entity`` accepts from a bare ``EntityDraft`` — the
#: generic Console/MCP "add an entity" path. Persons carry primary-user
#: semantics and preferences are temporal (section 40) — both have their own
#: operations, and creating one here would bypass the rules those operations
#: enforce. Appointments carry a booking state machine of their own (section
#: 63: a hold is not a booking) and events/documents are written by the
#: calendar and email flows that create them with the right provenance — so
#: none of the three Phase 7 types are generically creatable either.
CREATABLE_ENTITY_TYPES: frozenset[WorldEntityType] = frozenset(
    {
        WorldEntityType.HOUSEHOLD,
        WorldEntityType.PROVIDER,
        WorldEntityType.ASSET,
    }
)

#: Entity types the world repository will persist. Wider than
#: ``CREATABLE_ENTITY_TYPES``: the calendar and email flows build
#: ``WorldEntity`` objects directly (never through ``EntityDraft``, so the
#: generic creation path stays closed to them) and need a write path of their
#: own. This is that path's guard, kept in the domain layer so the NornicDB
#: and in-memory repositories enforce the identical rule.
#: ServiceRequest joins the same non-generic path (section 97): it is opened
#: by ``create_service_request``, which stamps the RESEARCHING status and
#: links it to a task, never through the bare ``EntityDraft`` creation path.
#: ShoppingList joins it too (section 98): it is opened by
#: ``create_shopping_list``, which stamps the DRAFT status, never through
#: ``EntityDraft``. Knowledge joins the same non-generic path: it is written
#: by ``record_knowledge``, the same pattern as Document, and for the same
#: reason — a facts bag with free-text content deserves its own draft
#: shape, not the generic entity path's bare key/value validation.
WORLD_MANAGED_ENTITY_TYPES: frozenset[WorldEntityType] = CREATABLE_ENTITY_TYPES | {
    WorldEntityType.APPOINTMENT,
    WorldEntityType.EVENT,
    WorldEntityType.DOCUMENT,
    WorldEntityType.SERVICE_REQUEST,
    WorldEntityType.SHOPPING_LIST,
    WorldEntityType.KNOWLEDGE,
}


class WorldRelationship(StrEnum):
    """The BUILD_SPEC section 39 relationship vocabulary, in the spec's order.

    All twenty are declared. Section 39 gives this list as the *initial*
    vocabulary and then warns "do not attempt to predefine every relationship
    in a human life" — that is a bound on inventing new types, not licence to
    implement fewer. Several of these are written by other aggregates today
    (``ASSIGNED_TO`` and ``ABOUT`` by tasks, ``PREFERS`` by preferences,
    ``SUPERSEDES`` by both temporal chains); declaring them here means the
    world graph reads one vocabulary rather than each layer keeping its own.
    """

    MEMBER_OF = "MEMBER_OF"
    RELATED_TO = "RELATED_TO"
    PREFERS = "PREFERS"
    OWNS = "OWNS"
    USES_PROVIDER = "USES_PROVIDER"
    ASSIGNED_TO = "ASSIGNED_TO"
    ABOUT = "ABOUT"
    WITH_PROVIDER = "WITH_PROVIDER"
    FOR_ASSET = "FOR_ASSET"
    WAITING_ON = "WAITING_ON"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"
    AUTHORIZES = "AUTHORIZES"
    CREATED_BY = "CREATED_BY"
    REQUESTED_BY = "REQUESTED_BY"
    EXECUTED_BY = "EXECUTED_BY"
    VERIFIED_BY = "VERIFIED_BY"
    DERIVED_FROM = "DERIVED_FROM"
    SUPERSEDES = "SUPERSEDES"
    RELATED_MEMORY = "RELATED_MEMORY"
    REFERENCES = "REFERENCES"


#: The whole section 39 vocabulary. Graph reads default to this, and edges
#: whose endpoints are not world entities are dropped during assembly — so an
#: ASSIGNED_TO edge to a Task neither appears as an arrow into nowhere nor has
#: to be excluded by name here.
WORLD_RELATIONSHIP_TYPES: tuple[WorldRelationship, ...] = tuple(WorldRelationship)

_PREFIX_FOR_TYPE: dict[WorldEntityType, str] = {
    WorldEntityType.PERSON: PREFIX_PERSON,
    WorldEntityType.HOUSEHOLD: PREFIX_HOUSEHOLD,
    WorldEntityType.PROVIDER: PREFIX_PROVIDER,
    WorldEntityType.ASSET: PREFIX_ASSET,
    WorldEntityType.PREFERENCE: PREFIX_PREFERENCE,
    WorldEntityType.APPOINTMENT: PREFIX_APPOINTMENT,
    WorldEntityType.EVENT: PREFIX_EVENT,
    WorldEntityType.DOCUMENT: PREFIX_DOCUMENT,
    WorldEntityType.SERVICE_REQUEST: PREFIX_SERVICE_REQUEST,
    WorldEntityType.SHOPPING_LIST: PREFIX_SHOPPING_LIST,
    WorldEntityType.KNOWLEDGE: PREFIX_KNOWLEDGE,
}

_TYPE_FOR_PREFIX: dict[str, WorldEntityType] = {
    prefix: entity_type for entity_type, prefix in _PREFIX_FOR_TYPE.items()
}

_MAX_FACTS = 50
_MAX_FACT_KEY = 100
_MAX_FACT_VALUE = 500


class WorldEntity(BaseModel):
    """One node in the user's world.

    ``facts`` is a flat bag of *current* key facts (``{"insurance":
    "Progressive", "mileage": "114203"}``) — the fast path every graph read,
    search, and the Entity Inspector's CURRENT section uses. It is not the
    only record: each fact's own version history lives in ``EntityFact``
    below, written alongside every change, the same "current state is a
    projection, history is the source of truth" split preferences already
    use.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    entity_type: WorldEntityType
    display_name: str
    facts: dict[str, str] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    created_by_client: str | None = None

    @staticmethod
    def make_id(entity_type: WorldEntityType, display_name: str) -> str:
        return slug_id(_PREFIX_FOR_TYPE[entity_type], display_name)


class EntityDraft(BaseModel):
    """Input shape for creating a Household, Provider, or Asset.

    Persons and preferences are excluded on purpose — see
    ``CREATABLE_ENTITY_TYPES``.
    """

    model_config = ConfigDict(extra="forbid")

    entity_type: WorldEntityType
    display_name: str = Field(min_length=1, max_length=200)
    facts: dict[str, str] = Field(default_factory=dict)

    @field_validator("entity_type")
    @classmethod
    def _is_creatable(cls, value: WorldEntityType) -> WorldEntityType:
        if value not in CREATABLE_ENTITY_TYPES:
            raise ValueError(
                f"{value} entities are not created here: persons go through the "
                "person surface and preferences through save_preference, which "
                "supersedes rather than overwrites"
            )
        return value


class EntityFact(BaseModel):
    """One version of one fact on a world entity (section 16's per-entity
    HISTORY: "Mileage 114,203" today, "Mileage 108,900" a version ago).

    Mirrors ``Preference``'s temporal shape exactly, scoped to
    ``(entity_id, key)`` instead of ``(subject_id, key)`` — a fact changing
    on the Land Rover is the same kind of event as a preference changing for
    a person, just attached to a different kind of subject.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    entity_id: str
    key: str
    value: str
    valid_from: str
    # None means "still true". Every current-state query filters on this.
    valid_to: str | None = None
    supersedes: str | None = None
    created_by_client: str | None = None

    @property
    def is_current(self) -> bool:
        return self.valid_to is None

    @staticmethod
    def make_id() -> str:
        return new_ulid_id(PREFIX_ENTITY_FACT)


class WorldNode(BaseModel):
    """One node of the graph read model the World screen renders (section 15)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    entity_type: WorldEntityType
    label: str
    # World entities have no lifecycle state yet; the field exists so the
    # Console contract is stable when one arrives.
    status: str = "active"


class WorldEdge(BaseModel):
    """A directed relationship between two world entities."""

    model_config = ConfigDict(extra="forbid")

    source: str
    target: str
    type: WorldRelationship


class WorldGraph(BaseModel):
    """The read model behind the World screen (sections 15 and 92)."""

    model_config = ConfigDict(extra="forbid")

    nodes: list[WorldNode] = Field(default_factory=list)
    edges: list[WorldEdge] = Field(default_factory=list)


class EntityDetail(BaseModel):
    """The entity inspector aggregate (section 16).

    Provenance is carried on the records themselves — ``created_by_client`` and
    timestamps on the entity, ``source_type`` / ``confidence`` on memories —
    rather than duplicated into a parallel structure.

    ``relationships`` holds raw ``(source, target, type)`` edges; ``neighbors``
    carries the same endpoints as labelled nodes. Section 16 requires the panel
    to show *named* relations, and an id alone cannot render one — so the read
    model resolves the labels rather than leaving each adapter to invent its
    own lookup.
    """

    model_config = ConfigDict(extra="forbid")

    entity: WorldEntity
    relationships: list[WorldEdge] = Field(default_factory=list)
    neighbors: list[WorldNode] = Field(default_factory=list)
    related_tasks: list[Task] = Field(default_factory=list)
    related_memories: list[MemoryRecord] = Field(default_factory=list)


class EntityHistory(BaseModel):
    """What "history of this entity" means.

    Two independent trails: ``fact_history`` is every version of every fact
    this entity has carried, newest first, superseded or current alike — the
    same shape ``Preference``'s history already has, per-key rather than
    per-entity, so "what was the mileage a version ago" is a real answer, not
    an inference from the audit log. ``memories`` is every version of every
    memory referencing the entity, including closed validity windows. Neither
    is the durable audit log (Phase 4, section 62) — ``covers`` states the
    actual scope explicitly so no consumer mistakes this for a complete
    "who changed what, when" record.
    """

    model_config = ConfigDict(extra="forbid")

    entity_id: str
    fact_history: list[EntityFact] = Field(default_factory=list)
    memories: list[MemoryRecord] = Field(default_factory=list)
    covers: list[str] = Field(default_factory=list)


# --- pure rules ---------------------------------------------------------------


def parse_relationship(value: str) -> WorldRelationship:
    """Parse a relationship type name, rejecting anything outside the vocabulary."""
    try:
        return WorldRelationship(value.strip().upper())
    except (ValueError, AttributeError):
        raise ValidationError(
            f"unknown relationship type: {value!r}",
            field="rel_type",
            allowed=[str(r) for r in WorldRelationship],
        ) from None


def parse_entity_types(values: list[str] | None) -> list[WorldEntityType] | None:
    """Parse World screen type filters, rejecting anything outside the model.

    ``None`` means "no filter" and is passed through; an unknown name is a
    caller error rather than an empty result, because silently returning
    nothing for a typo looks identical to an empty world.
    """
    if values is None:
        return None
    parsed: list[WorldEntityType] = []
    for value in values:
        try:
            entity_type = WorldEntityType(value.strip().lower())
        except (ValueError, AttributeError):
            raise ValidationError(
                f"unknown entity type: {value!r}",
                field="types",
                allowed=[str(t) for t in WorldEntityType],
            ) from None
        if entity_type not in parsed:
            parsed.append(entity_type)
    return parsed


def is_world_entity_id(entity_id: str) -> bool:
    """Whether an ID addresses a world entity, without raising.

    The vocabulary spans edges owned by other aggregates, so a graph walk
    routinely meets a ``task_`` or ``memory_`` endpoint. That is not a caller
    error — it is a node the World screen does not draw — so traversal asks
    this rather than catching an exception from ``entity_type_for_id``.
    """
    if not is_valid_id(entity_id):
        return False
    return entity_id.split("_", 1)[0] in _TYPE_FOR_PREFIX


def entity_type_for_id(entity_id: str) -> WorldEntityType:
    """The world entity type an ID addresses.

    Raises rather than guesses: an ID outside the four world prefixes must not
    silently become a graph node (a ``task_`` id is addressable, but it is not
    a world entity).
    """
    if not is_valid_id(entity_id):
        raise ValidationError(f"not a canonical LifeOps ID: {entity_id!r}", field="entity_id")
    prefix = entity_id.split("_", 1)[0]
    entity_type = _TYPE_FOR_PREFIX.get(prefix)
    if entity_type is None:
        raise ValidationError(
            f"{entity_id!r} is not a world entity id",
            field="entity_id",
            allowed=sorted(_TYPE_FOR_PREFIX),
        )
    return entity_type


def validate_facts(facts: dict[str, str]) -> dict[str, str]:
    """Normalise and bound the facts bag.

    Keys are stripped and must be non-empty; the bag is capped so an agent
    cannot turn one entity into an unbounded document store.
    """
    cleaned: dict[str, str] = {}
    for raw_key, raw_value in facts.items():
        key = raw_key.strip()
        value = raw_value.strip()
        if not key:
            raise ValidationError("fact keys must not be empty", field="facts")
        if len(key) > _MAX_FACT_KEY:
            raise ValidationError(
                f"fact key {key!r} exceeds {_MAX_FACT_KEY} characters", field="facts"
            )
        if len(value) > _MAX_FACT_VALUE:
            raise ValidationError(
                f"fact {key!r} exceeds {_MAX_FACT_VALUE} characters", field="facts"
            )
        cleaned[key] = value
    if len(cleaned) > _MAX_FACTS:
        raise ValidationError(
            f"an entity may carry at most {_MAX_FACTS} facts", field="facts"
        )
    return cleaned


def diff_facts(current: dict[str, str], incoming: dict[str, str]) -> dict[str, str]:
    """Which incoming facts actually change something.

    Re-stating an identical value is a no-op rather than a new version, the
    same rule ``save_preference`` applies — an agent re-confirming a mileage
    reading it already recorded must not pile up history that says nothing
    changed.
    """
    return {key: value for key, value in incoming.items() if current.get(key) != value}


def assemble_world_graph(
    entities: list[WorldEntity],
    edges: list[WorldEdge],
    *,
    limit: int,
) -> WorldGraph:
    """Build the World screen's read model from repository rows.

    Nodes are deduplicated by id and capped at ``limit``; edges are
    deduplicated and dropped when either endpoint fell outside the node set,
    so the Console never renders an arrow into nowhere.
    """
    nodes: dict[str, WorldNode] = {}
    for entity in entities:
        if entity.id in nodes or len(nodes) >= limit:
            continue
        nodes[entity.id] = WorldNode(
            id=entity.id,
            entity_type=entity.entity_type,
            label=entity.display_name,
        )

    seen: set[tuple[str, str, WorldRelationship]] = set()
    kept: list[WorldEdge] = []
    for edge in edges:
        key = (edge.source, edge.target, edge.type)
        if key in seen or edge.source not in nodes or edge.target not in nodes:
            continue
        seen.add(key)
        kept.append(edge)

    return WorldGraph(nodes=list(nodes.values()), edges=kept)
