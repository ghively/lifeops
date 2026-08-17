"""Repository interfaces (BUILD_SPEC sections 41 and 81).

Domain code depends on these Protocols and never on NornicDB. That is what
makes the "escape plan" real rather than aspirational: replacing the database
means writing new implementations of these, with Hermes, the Console, the MCP
surface, and the domain layer untouched.

Repositories follow domain boundaries. There is deliberately no generic
``save(entity)`` mega-repository — a single blurred interface would let graph
concerns leak straight back into the domain.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from lifeops.domain.actions import Action, ActionStatus
from lifeops.domain.approvals import Approval
from lifeops.domain.audit import AuditRecord
from lifeops.domain.memory import MemoryRecord, MemoryType
from lifeops.domain.people import Person
from lifeops.domain.preferences import Preference
from lifeops.domain.tasks import Task, TaskState
from lifeops.domain.waiting import WaitingItem, WaitingStatus
from lifeops.domain.world import (
    WorldEdge,
    WorldEntity,
    WorldEntityType,
    WorldRelationship,
)


@runtime_checkable
class PersonRepository(Protocol):
    async def get(self, person_id: str) -> Person | None: ...

    async def get_primary(self) -> Person | None: ...

    async def find_by_name(self, name: str) -> list[Person]: ...

    async def list_all(self, *, limit: int = 100) -> list[Person]: ...

    async def upsert(self, person: Person) -> Person: ...


@runtime_checkable
class PreferenceRepository(Protocol):
    async def get(self, preference_id: str) -> Preference | None: ...

    async def list_current(
        self, subject_id: str, *, key_prefix: str | None = None
    ) -> list[Preference]:
        """Preferences whose validity window is still open."""
        ...

    async def get_current_by_key(self, subject_id: str, key: str) -> Preference | None: ...

    async def search(self, query: str, *, limit: int = 25) -> list[Preference]:
        """Case-insensitive substring match over key and value, current only."""
        ...

    async def list_history(self, subject_id: str, key: str) -> list[Preference]:
        """Every record for a key, newest first, including closed windows."""
        ...

    async def save_superseding(
        self, preference: Preference, *, supersedes: Preference | None
    ) -> Preference:
        """Persist a new preference, closing the record it replaces.

        Implementations must make the close-and-open pair atomic. A crash
        between the two writes would otherwise leave either two current values
        for one key or none at all.
        """
        ...

    async def invalidate(self, preference_id: str, *, at: str) -> Preference | None: ...


@runtime_checkable
class TaskRepository(Protocol):
    async def get(self, task_id: str) -> Task | None: ...

    async def list(
        self,
        *,
        states: list[TaskState] | None = None,
        owner_entity_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]: ...

    async def count_by_state(self) -> dict[str, int]: ...

    async def search(self, query: str, *, limit: int = 25) -> Sequence[Task]:
        """Case-insensitive substring match over title and description."""
        ...

    async def list_related_to_entity(self, entity_id: str) -> list[Task]:
        """Tasks whose ``related_entity_ids`` contain the entity.

        The property stays the source of truth for reads even though Phase 3
        also writes ``(:Task)-[:ABOUT]->(entity)`` edges: pre-Phase-3 tasks
        carry only the property and must stay readable.
        """
        ...

    async def create(self, task: Task) -> Task: ...

    async def update(self, task: Task) -> Task:
        """Persist a task that already exists. Raises NotFoundError if absent."""
        ...


@runtime_checkable
class MemoryRepository(Protocol):
    """Persistence for memory records (BUILD_SPEC sections 42–47).

    Deliberately disjoint from the task/preference repositories: memory
    observes the world and must never be a path back into transactional
    state (section 44).
    """

    async def get(self, memory_id: str) -> MemoryRecord | None: ...

    async def list_current(
        self,
        subject_id: str | None = None,
        *,
        memory_types: list[MemoryType] | None = None,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        """Current memories (validity window open), most important first."""
        ...

    async def search(
        self,
        query: str,
        *,
        subject_id: str | None = None,
        memory_types: list[MemoryType] | None = None,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        """Ranked text search over current memories (section 47 recall)."""
        ...

    async def list_history(self, memory_id: str) -> list[MemoryRecord]:
        """Every version in the record's SUPERSEDES chain, newest first."""
        ...

    async def get_current_duplicate(
        self, subject_id: str, memory_type: MemoryType, content: str
    ) -> MemoryRecord | None:
        """An identical current record, so re-stating a memory is a no-op."""
        ...

    async def save_superseding(
        self, memory: MemoryRecord, *, supersedes: MemoryRecord | None
    ) -> MemoryRecord:
        """Persist a new memory, closing the record it replaces.

        The close-and-open pair must be atomic, exactly as for preferences:
        a crash between the two writes would otherwise leave either two
        current versions of one memory or none at all.
        """
        ...

    async def invalidate(
        self, memory_id: str, *, at: str, reason: str | None = None
    ) -> MemoryRecord | None: ...

    async def list_for_entity(
        self, entity_id: str, *, current_only: bool = True, limit: int = 50
    ) -> list[MemoryRecord]:
        """Memories whose ``entity_ids`` reference the entity.

        ``current_only=False`` returns closed versions too — that is what
        ``entity_history`` reports as the Phase 3 audit-available truth about
        an entity.
        """
        ...


@runtime_checkable
class WorldRepository(Protocol):
    """Persistence for the world graph (BUILD_SPEC sections 36–39, 92).

    Covers reads across all four Phase 3 entity labels (Person, Household,
    Provider, Asset) as graph projections, plus the world relationship edges
    between them. Writes are limited to the three new types — persons keep
    their own richer model and repository.
    """

    async def get(self, entity_id: str) -> WorldEntity | None:
        """Any world entity by canonical id, whatever its label."""
        ...

    async def exists(self, entity_id: str) -> bool: ...

    async def create(self, entity: WorldEntity) -> WorldEntity:
        """Persist a Household, Provider, or Asset (never a Person)."""
        ...

    async def list_entities(
        self, *, types: list[WorldEntityType] | None = None, limit: int = 500
    ) -> list[WorldEntity]: ...

    async def list_edges(
        self,
        *,
        rel_types: list[WorldRelationship] | None = None,
        limit: int = 2000,
    ) -> list[WorldEdge]:
        """Every world relationship edge. ``rel_types=None`` means the whole
        implemented vocabulary, not every edge in the database."""
        ...

    async def list_edges_for(
        self, entity_id: str, *, rel_types: list[WorldRelationship] | None = None
    ) -> list[WorldEdge]:
        """Edges where the entity is source or target."""
        ...

    async def neighborhood(
        self,
        entity_id: str,
        *,
        depth: int,
        rel_types: list[WorldRelationship] | None = None,
    ) -> tuple[list[WorldEntity], list[WorldEdge]]:
        """Entities and edges within ``depth`` hops, walking edges in either
        direction. Includes the starting entity itself when it exists."""
        ...

    async def link(
        self, source_id: str, target_id: str, rel_type: WorldRelationship
    ) -> WorldEdge:
        """Create the edge if absent; re-linking an existing pair is a no-op."""
        ...

    async def unlink(
        self, source_id: str, target_id: str, rel_type: WorldRelationship
    ) -> bool:
        """Remove the edge. Returns False when no such edge existed."""
        ...


@runtime_checkable
class WaitingRepository(Protocol):
    """Persistence for waiting items (BUILD_SPEC sections 13, 54, 55)."""

    async def get(self, waiting_id: str) -> WaitingItem | None: ...

    async def list_for_task(self, task_id: str) -> list[WaitingItem]: ...

    async def list_by_status(
        self, *, statuses: list[WaitingStatus] | None = None, limit: int = 100
    ) -> list[WaitingItem]:
        """Waiting items for the Waiting screen, newest first."""
        ...

    async def list_due(self, *, now: str, limit: int = 50) -> list[WaitingItem]:
        """Active items whose next action has come due and whose lease is free.

        The due-work worker's only read. Filtering in the query rather than in
        Python keeps a growing backlog from being pulled into memory every
        tick.
        """
        ...

    async def claim(
        self, waiting_id: str, *, owner: str, until: str, now: str
    ) -> WaitingItem | None:
        """Take the lease on an item, or return None if another worker holds it.

        Section 55: the claim must be atomic, because two workers following up
        with the same provider is exactly the duplicate-contact failure the
        lease exists to prevent.
        """
        ...

    async def create(self, item: WaitingItem) -> WaitingItem: ...

    async def update(self, item: WaitingItem) -> WaitingItem: ...


@runtime_checkable
class ActionRepository(Protocol):
    """Persistence for the action outbox (BUILD_SPEC sections 60, 61)."""

    async def get(self, action_id: str) -> Action | None: ...

    async def get_by_idempotency_key(self, key: str) -> Action | None:
        """The existing action for this key, if any.

        Section 60: before retrying, inspect whether the previous request may
        have succeeded. This is that inspection.
        """
        ...

    async def list_for_task(self, task_id: str) -> list[Action]: ...

    async def list_by_status(
        self, *, statuses: list[ActionStatus] | None = None, limit: int = 100
    ) -> list[Action]: ...

    async def create(self, action: Action) -> Action: ...

    async def update(self, action: Action) -> Action: ...


@runtime_checkable
class ApprovalRepository(Protocol):
    """Persistence for approvals (BUILD_SPEC sections 57-59)."""

    async def get(self, approval_id: str) -> Approval | None: ...

    async def get_for_action(self, action_id: str) -> Approval | None: ...

    async def list_pending(self, *, limit: int = 50) -> list[Approval]: ...

    async def create(self, approval: Approval) -> Approval: ...

    async def update(self, approval: Approval) -> Approval: ...


@runtime_checkable
class AuditRepository(Protocol):
    """The durable audit log (BUILD_SPEC section 62).

    Append-only by construction: there is deliberately no update or delete.
    An audit log a caller can rewrite answers no question worth asking.
    """

    async def append(self, record: AuditRecord) -> AuditRecord: ...

    async def list_recent(self, *, limit: int = 100) -> list[AuditRecord]: ...

    async def list_for_target(
        self, target: str, *, limit: int = 100
    ) -> list[AuditRecord]:
        """Every recorded action against one entity — "why did Hermes do that?"
        asked of a specific thing."""
        ...


@runtime_checkable
class HealthCheck(Protocol):
    async def ping(self) -> bool: ...
