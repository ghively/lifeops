"""In-memory repository fakes.

These exist so domain and policy tests can run without NornicDB. They are the
practical proof that the repository abstraction holds: if a domain test needs
Cypher to pass, the abstraction has leaked.

They are not a second storage backend and must never be wired into a running
LifeOps deployment — nothing here survives a process restart.
"""

from __future__ import annotations

import builtins
import copy
from collections.abc import Sequence

from lifeops.domain.actions import Action, ActionStatus
from lifeops.domain.approvals import Approval
from lifeops.domain.audit import AuditRecord
from lifeops.domain.bills import Bill, BillStatus, Payee
from lifeops.domain.memory import MemoryRecord, MemoryType
from lifeops.domain.people import Person
from lifeops.domain.preferences import Preference
from lifeops.domain.service_request import ServiceRequest
from lifeops.domain.shopping import ShoppingList
from lifeops.domain.tasks import Task, TaskState
from lifeops.domain.waiting import ACTIVE_STATUSES, WaitingItem, WaitingStatus
from lifeops.domain.workflow_templates import WorkflowTemplate
from lifeops.domain.world import (
    WORLD_MANAGED_ENTITY_TYPES,
    WORLD_RELATIONSHIP_TYPES,
    WorldEdge,
    WorldEntity,
    WorldEntityType,
    WorldRelationship,
    entity_type_for_id,
    is_world_entity_id,
)
from lifeops.errors import NotFoundError


class FakePersonRepository:
    def __init__(self) -> None:
        self._people: dict[str, Person] = {}

    async def get(self, person_id: str) -> Person | None:
        found = self._people.get(person_id)
        return copy.deepcopy(found) if found else None

    async def get_primary(self) -> Person | None:
        for person in sorted(self._people.values(), key=lambda p: p.created_at):
            if person.is_primary:
                return copy.deepcopy(person)
        return None

    async def find_by_name(self, name: str) -> list[Person]:
        needle = name.strip().lower()
        return [
            copy.deepcopy(p)
            for p in self._people.values()
            if needle in p.display_name.lower()
            or any(needle in alias.lower() for alias in p.aliases)
        ]

    async def list_all(self, *, limit: int = 100) -> list[Person]:
        ordered = sorted(self._people.values(), key=lambda p: p.display_name)
        return [copy.deepcopy(p) for p in ordered[:limit]]

    async def upsert(self, person: Person) -> Person:
        if person.is_primary:
            for other in self._people.values():
                if other.id != person.id:
                    other.is_primary = False
        self._people[person.id] = copy.deepcopy(person)
        return copy.deepcopy(person)


class FakePreferenceRepository:
    def __init__(self) -> None:
        self._prefs: dict[str, Preference] = {}

    async def get(self, preference_id: str) -> Preference | None:
        found = self._prefs.get(preference_id)
        return copy.deepcopy(found) if found else None

    async def list_current(
        self, subject_id: str, *, key_prefix: str | None = None
    ) -> list[Preference]:
        matches = [
            p
            for p in self._prefs.values()
            if p.subject_id == subject_id
            and p.valid_to is None
            and (key_prefix is None or p.key.startswith(key_prefix))
        ]
        return [copy.deepcopy(p) for p in sorted(matches, key=lambda p: p.key)]

    async def list_all_current(self) -> list[Preference]:
        """Every current preference, across subjects.

        Exists for the world projection: NornicDB stores one ``:Preference``
        node that both the preference and world repositories read, and the
        fakes have to model that rather than drifting apart.
        """
        current = [p for p in self._prefs.values() if p.valid_to is None]
        return [copy.deepcopy(p) for p in sorted(current, key=lambda p: p.id)]

    async def get_current_by_key(self, subject_id: str, key: str) -> Preference | None:
        matches = [
            p
            for p in self._prefs.values()
            if p.subject_id == subject_id and p.key == key and p.valid_to is None
        ]
        if not matches:
            return None
        matches.sort(key=lambda p: p.valid_from, reverse=True)
        return copy.deepcopy(matches[0])

    async def search(self, query: str, *, limit: int = 25) -> list[Preference]:
        needle = query.strip().lower()
        matches = [
            p
            for p in self._prefs.values()
            if p.valid_to is None
            and (needle in p.key.lower() or needle in p.value.lower())
        ]
        matches.sort(key=lambda p: p.key)
        return [copy.deepcopy(p) for p in matches[:limit]]

    async def list_history(self, subject_id: str, key: str) -> list[Preference]:
        matches = [
            p
            for p in self._prefs.values()
            if p.subject_id == subject_id and p.key == key
        ]
        matches.sort(key=lambda p: p.valid_from, reverse=True)
        return [copy.deepcopy(p) for p in matches]

    async def save_superseding(
        self, preference: Preference, *, supersedes: Preference | None
    ) -> Preference:
        if supersedes is not None:
            stored = self._prefs.get(supersedes.id)
            if stored is not None:
                stored.valid_to = preference.valid_from
        self._prefs[preference.id] = copy.deepcopy(preference)
        return copy.deepcopy(preference)

    async def invalidate(self, preference_id: str, *, at: str) -> Preference | None:
        stored = self._prefs.get(preference_id)
        if stored is None:
            return None
        if stored.valid_to is None:
            stored.valid_to = at
        return copy.deepcopy(stored)


class FakeTaskRepository:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}

    async def get(self, task_id: str) -> Task | None:
        found = self._tasks.get(task_id)
        return copy.deepcopy(found) if found else None

    async def list(
        self,
        *,
        states: list[TaskState] | None = None,
        owner_entity_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        matches = list(self._tasks.values())
        if states:
            wanted = set(states)
            matches = [t for t in matches if t.state in wanted]
        if owner_entity_id:
            matches = [t for t in matches if t.owner_entity_id == owner_entity_id]
        matches.sort(key=lambda t: (t.created_at, t.id), reverse=True)
        return [copy.deepcopy(t) for t in matches[offset : offset + limit]]

    async def count_by_state(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for task in self._tasks.values():
            counts[str(task.state)] = counts.get(str(task.state), 0) + 1
        return counts

    async def search(self, query: str, *, limit: int = 25) -> Sequence[Task]:
        needle = query.strip().lower()
        matches = [
            t
            for t in self._tasks.values()
            if needle in t.title.lower()
            or (t.description is not None and needle in t.description.lower())
        ]
        matches.sort(key=lambda t: (t.created_at, t.id), reverse=True)
        return [copy.deepcopy(t) for t in matches[:limit]]

    async def list_related_to_entity(self, entity_id: str) -> builtins.list[Task]:
        matches = [
            t for t in self._tasks.values() if entity_id in t.related_entity_ids
        ]
        matches.sort(key=lambda t: (t.created_at, t.id), reverse=True)
        return [copy.deepcopy(t) for t in matches]

    async def create(self, task: Task) -> Task:
        self._tasks[task.id] = copy.deepcopy(task)
        return copy.deepcopy(task)

    async def update(self, task: Task) -> Task:
        if task.id not in self._tasks:
            raise NotFoundError(f"task {task.id} does not exist", task_id=task.id)
        self._tasks[task.id] = copy.deepcopy(task)
        return copy.deepcopy(task)


class FakeMemoryRepository:
    def __init__(self) -> None:
        self._memories: dict[str, MemoryRecord] = {}

    async def get(self, memory_id: str) -> MemoryRecord | None:
        found = self._memories.get(memory_id)
        return copy.deepcopy(found) if found else None

    async def list_current(
        self,
        subject_id: str | None = None,
        *,
        memory_types: list[MemoryType] | None = None,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        matches = [
            m
            for m in self._memories.values()
            if m.valid_to is None
            and (subject_id is None or m.subject_id == subject_id)
            and (memory_types is None or m.type in memory_types)
        ]
        matches.sort(key=lambda m: (m.importance, m.observed_at, m.id), reverse=True)
        return [copy.deepcopy(m) for m in matches[:limit]]

    async def list_for_entity(
        self, entity_id: str, *, current_only: bool = True, limit: int = 50
    ) -> list[MemoryRecord]:
        matches = [
            m
            for m in self._memories.values()
            if entity_id in m.entity_ids and (not current_only or m.valid_to is None)
        ]
        matches.sort(key=lambda m: (m.created_at, m.id), reverse=True)
        return [copy.deepcopy(m) for m in matches[:limit]]

    async def search(
        self,
        query: str,
        *,
        subject_id: str | None = None,
        memory_types: list[MemoryType] | None = None,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        # All-terms substring match: the fake mirrors the repository's
        # fallback ranking, not the fulltext scoring (which is persistence's
        # job to prove).
        terms = query.strip().lower().split()
        if not terms:
            return []
        matches = [
            m
            for m in self._memories.values()
            if m.valid_to is None
            and (subject_id is None or m.subject_id == subject_id)
            and (memory_types is None or m.type in memory_types)
            and all(term in m.content.lower() for term in terms)
        ]
        matches.sort(key=lambda m: (m.importance, m.observed_at, m.id), reverse=True)
        return [copy.deepcopy(m) for m in matches[:limit]]

    async def list_history(self, memory_id: str) -> list[MemoryRecord]:
        if memory_id not in self._memories:
            return []
        chain: dict[str, MemoryRecord] = {}
        # Walk up the chain via supersedes pointers, then down by scanning for
        # records that supersede an id already in the chain.
        current: MemoryRecord | None = self._memories[memory_id]
        while current is not None and current.id not in chain:
            chain[current.id] = current
            current = (
                self._memories.get(current.supersedes) if current.supersedes else None
            )
        changed = True
        while changed:
            changed = False
            for m in self._memories.values():
                if m.id not in chain and m.supersedes in chain:
                    chain[m.id] = m
                    changed = True
        ordered = sorted(chain.values(), key=lambda m: (m.valid_from, m.id), reverse=True)
        return [copy.deepcopy(m) for m in ordered]

    async def get_current_duplicate(
        self, subject_id: str, memory_type: MemoryType, content: str
    ) -> MemoryRecord | None:
        matches = [
            m
            for m in self._memories.values()
            if m.subject_id == subject_id
            and m.type == memory_type
            and m.content == content
            and m.valid_to is None
        ]
        if not matches:
            return None
        matches.sort(key=lambda m: m.valid_from, reverse=True)
        return copy.deepcopy(matches[0])

    async def save_superseding(
        self, memory: MemoryRecord, *, supersedes: MemoryRecord | None
    ) -> MemoryRecord:
        if supersedes is not None:
            stored = self._memories.get(supersedes.id)
            if stored is not None:
                stored.valid_to = memory.valid_from
        self._memories[memory.id] = copy.deepcopy(memory)
        return copy.deepcopy(memory)

    async def invalidate(
        self, memory_id: str, *, at: str, reason: str | None = None
    ) -> MemoryRecord | None:
        stored = self._memories.get(memory_id)
        if stored is None:
            return None
        if stored.valid_to is None:
            stored.valid_to = at
            stored.invalidation_reason = reason
        return copy.deepcopy(stored)


class FakeWorldRepository:
    """In-memory world graph.

    Mirrors the NornicDB repository's contract rather than its storage: edges
    are stored as a set of ``(source, target, type)`` triples so ``link`` is
    idempotent the same way ``MERGE`` is, and ``neighborhood`` walks edges in
    both directions from the starting entity.
    """

    def __init__(self, preferences: FakePreferenceRepository | None = None) -> None:
        self._entities: dict[str, WorldEntity] = {}
        self._edges: set[tuple[str, str, WorldRelationship]] = set()
        # Preferences are projected from their own store, never copied into
        # this one — the same arrangement NornicDB has, where one
        # ``:Preference`` node is read by two repositories.
        self._preferences = preferences

    @staticmethod
    def _preference_entity(preference: Preference) -> WorldEntity:
        """Project a preference into a graph node (BUILD_SPEC section 15)."""
        facts = {"key": preference.key, "source": str(preference.source_type)}
        if preference.confidence is not None:
            facts["confidence"] = str(preference.confidence)
        return WorldEntity(
            id=preference.id,
            entity_type=WorldEntityType.PREFERENCE,
            display_name=preference.value,
            facts=facts,
            created_at=preference.created_at,
            # A preference is never edited; a new version opens instead.
            updated_at=preference.valid_from,
            created_by_client=preference.created_by_client,
        )

    async def _current_preference(self, preference_id: str) -> WorldEntity | None:
        if self._preferences is None:
            return None
        found = await self._preferences.get(preference_id)
        if found is None or found.valid_to is not None:
            return None
        return self._preference_entity(found)

    def seed(self, entity: WorldEntity) -> WorldEntity:
        """Place an entity directly, bypassing the create path.

        Tests use this for persons and for pre-existing worlds; production code
        must go through ``LifeOpsCore``.
        """
        self._entities[entity.id] = copy.deepcopy(entity)
        return copy.deepcopy(entity)

    async def get(self, entity_id: str) -> WorldEntity | None:
        # The NornicDB repository resolves a label from the ID prefix before it
        # can query at all, so a non-world ID raises there. The fake validates
        # explicitly to keep that behaviour identical.
        if entity_type_for_id(entity_id) is WorldEntityType.PREFERENCE:
            return await self._current_preference(entity_id)
        found = self._entities.get(entity_id)
        return copy.deepcopy(found) if found else None

    async def exists(self, entity_id: str) -> bool:
        return await self.get(entity_id) is not None

    async def create(self, entity: WorldEntity) -> WorldEntity:
        # The same guard the NornicDB repository enforces (domain/world.py
        # keeps the set in one place so both backends refuse identically).
        if entity.entity_type not in WORLD_MANAGED_ENTITY_TYPES:
            raise ValueError(
                f"{entity.entity_type} is not created by the world repository"
            )
        self._entities[entity.id] = copy.deepcopy(entity)
        return copy.deepcopy(entity)

    async def list_entities(
        self, *, types: list[WorldEntityType] | None = None, limit: int = 500
    ) -> list[WorldEntity]:
        matches = [
            e for e in self._entities.values() if types is None or e.entity_type in types
        ]
        wants_preferences = types is None or WorldEntityType.PREFERENCE in types
        if wants_preferences and self._preferences is not None:
            # Current versions only: a superseded preference is not part of the
            # current world, and its PREFERS edge drops with it.
            matches.extend(
                self._preference_entity(p)
                for p in await self._preferences.list_all_current()
            )
        matches.sort(key=lambda e: e.id)
        return [copy.deepcopy(e) for e in matches[:limit]]

    async def list_edges(
        self,
        *,
        rel_types: list[WorldRelationship] | None = None,
        limit: int = 2000,
    ) -> list[WorldEdge]:
        wanted = set(rel_types) if rel_types is not None else set(WORLD_RELATIONSHIP_TYPES)
        edges = [
            WorldEdge(source=s, target=t, type=r)
            for s, t, r in sorted(self._edges)
            if r in wanted
        ]
        return edges[:limit]

    async def list_edges_for(
        self, entity_id: str, *, rel_types: list[WorldRelationship] | None = None
    ) -> list[WorldEdge]:
        wanted = set(rel_types) if rel_types is not None else set(WORLD_RELATIONSHIP_TYPES)
        return [
            WorldEdge(source=s, target=t, type=r)
            for s, t, r in sorted(self._edges)
            if r in wanted and entity_id in (s, t)
        ]

    async def neighborhood(
        self,
        entity_id: str,
        *,
        depth: int,
        rel_types: list[WorldRelationship] | None = None,
    ) -> tuple[list[WorldEntity], list[WorldEdge]]:
        start = await self.get(entity_id)
        if start is None:
            return [], []

        entities: dict[str, WorldEntity] = {start.id: start}
        edges: dict[tuple[str, str, WorldRelationship], WorldEdge] = {}
        frontier = [entity_id]

        for _ in range(depth):
            next_frontier: list[str] = []
            for current in frontier:
                for edge in await self.list_edges_for(current, rel_types=rel_types):
                    edges[(edge.source, edge.target, edge.type)] = edge
                    for endpoint in (edge.source, edge.target):
                        # Endpoints owned by other aggregates (a Task, a
                        # Memory) are not world nodes — same rule as the
                        # NornicDB repository.
                        if endpoint in entities or not is_world_entity_id(endpoint):
                            continue
                        found = await self.get(endpoint)
                        if found is not None:
                            entities[endpoint] = found
                            next_frontier.append(endpoint)
            frontier = next_frontier
            if not frontier:
                break

        return list(entities.values()), list(edges.values())

    async def link(
        self, source_id: str, target_id: str, rel_type: WorldRelationship
    ) -> WorldEdge:
        self._edges.add((source_id, target_id, rel_type))
        return WorldEdge(source=source_id, target=target_id, type=rel_type)

    async def unlink(
        self, source_id: str, target_id: str, rel_type: WorldRelationship
    ) -> bool:
        key = (source_id, target_id, rel_type)
        if key not in self._edges:
            return False
        self._edges.discard(key)
        return True


class FakeWaitingRepository:
    def __init__(self) -> None:
        self._items: dict[str, WaitingItem] = {}

    async def get(self, waiting_id: str) -> WaitingItem | None:
        found = self._items.get(waiting_id)
        return copy.deepcopy(found) if found else None

    async def list_for_task(self, task_id: str) -> list[WaitingItem]:
        matches = [i for i in self._items.values() if i.task_id == task_id]
        matches.sort(key=lambda i: i.waiting_since, reverse=True)
        return [copy.deepcopy(i) for i in matches]

    async def list_by_status(
        self, *, statuses: list[WaitingStatus] | None = None, limit: int = 100
    ) -> list[WaitingItem]:
        wanted = set(statuses) if statuses is not None else None
        matches = [
            i for i in self._items.values() if wanted is None or i.status in wanted
        ]
        matches.sort(key=lambda i: (i.waiting_since, i.id), reverse=True)
        return [copy.deepcopy(i) for i in matches[:limit]]

    async def list_due(self, *, now: str, limit: int = 50) -> list[WaitingItem]:
        matches = [
            i
            for i in self._items.values()
            if i.status in ACTIVE_STATUSES
            and i.next_action_at is not None
            and i.next_action_at <= now
            and (i.lease_until is None or i.lease_until <= now)
        ]
        matches.sort(key=lambda i: (i.next_action_at or "", i.id))
        return [copy.deepcopy(i) for i in matches[:limit]]

    async def claim(
        self, waiting_id: str, *, owner: str, until: str, now: str
    ) -> WaitingItem | None:
        stored = self._items.get(waiting_id)
        if stored is None:
            return None
        # Mirrors the conditional Cypher write: only an unheld or expired
        # lease may be taken, so two workers cannot both win the same item.
        if stored.lease_until is not None and stored.lease_until > now:
            return None
        stored.lease_owner = owner
        stored.lease_until = until
        return copy.deepcopy(stored)

    async def create(self, item: WaitingItem) -> WaitingItem:
        self._items[item.id] = copy.deepcopy(item)
        return copy.deepcopy(item)

    async def update(self, item: WaitingItem) -> WaitingItem:
        if item.id not in self._items:
            raise NotFoundError(
                f"waiting item {item.id} does not exist", waiting_id=item.id
            )
        self._items[item.id] = copy.deepcopy(item)
        return copy.deepcopy(item)


class FakeActionRepository:
    def __init__(self) -> None:
        self._actions: dict[str, Action] = {}

    async def get(self, action_id: str) -> Action | None:
        found = self._actions.get(action_id)
        return copy.deepcopy(found) if found else None

    async def get_by_idempotency_key(self, key: str) -> Action | None:
        for action in self._actions.values():
            if action.idempotency_key == key:
                return copy.deepcopy(action)
        return None

    async def list_for_task(self, task_id: str) -> list[Action]:
        matches = [a for a in self._actions.values() if a.task_id == task_id]
        matches.sort(key=lambda a: (a.created_at, a.id), reverse=True)
        return [copy.deepcopy(a) for a in matches]

    async def list_by_status(
        self, *, statuses: list[ActionStatus] | None = None, limit: int = 100
    ) -> list[Action]:
        wanted = set(statuses) if statuses is not None else None
        matches = [
            a for a in self._actions.values() if wanted is None or a.status in wanted
        ]
        matches.sort(key=lambda a: (a.created_at, a.id), reverse=True)
        return [copy.deepcopy(a) for a in matches[:limit]]

    async def create(self, action: Action) -> Action:
        self._actions[action.id] = copy.deepcopy(action)
        return copy.deepcopy(action)

    async def update(self, action: Action) -> Action:
        if action.id not in self._actions:
            raise NotFoundError(
                f"action {action.id} does not exist", action_id=action.id
            )
        self._actions[action.id] = copy.deepcopy(action)
        return copy.deepcopy(action)


class FakeApprovalRepository:
    def __init__(self) -> None:
        self._approvals: dict[str, Approval] = {}

    async def get(self, approval_id: str) -> Approval | None:
        found = self._approvals.get(approval_id)
        return copy.deepcopy(found) if found else None

    async def get_for_action(self, action_id: str) -> Approval | None:
        matches = [a for a in self._approvals.values() if a.action_id == action_id]
        if not matches:
            return None
        # Tiebreak on id (ULIDs sort by real creation time even under a
        # frozen domain clock), matching NornicApprovalRepository's
        # ``ORDER BY created_at DESC, id DESC`` — otherwise two approvals
        # created under FrozenClock, with identical ``created_at``, would
        # resolve to whichever happened to be inserted first rather than the
        # most recent one (BUILD_SPEC section 57: a refreshed approval must
        # actually supersede the stale one it replaces).
        matches.sort(key=lambda a: (a.created_at, a.id), reverse=True)
        return copy.deepcopy(matches[0])

    async def list_pending(self, *, limit: int = 50) -> list[Approval]:
        from lifeops.domain.approvals import ApprovalStatus

        matches = [
            a for a in self._approvals.values() if a.status is ApprovalStatus.PENDING
        ]
        matches.sort(key=lambda a: (a.created_at, a.id))
        return [copy.deepcopy(a) for a in matches[:limit]]

    async def create(self, approval: Approval) -> Approval:
        self._approvals[approval.id] = copy.deepcopy(approval)
        return copy.deepcopy(approval)

    async def update(self, approval: Approval) -> Approval:
        if approval.id not in self._approvals:
            raise NotFoundError(
                f"approval {approval.id} does not exist", approval_id=approval.id
            )
        self._approvals[approval.id] = copy.deepcopy(approval)
        return copy.deepcopy(approval)


class FakeAuditRepository:
    """Append-only, like the real one — no update method exists to call."""

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []

    async def append(self, record: AuditRecord) -> AuditRecord:
        self._records.append(copy.deepcopy(record))
        return copy.deepcopy(record)

    async def list_recent(self, *, limit: int = 100) -> list[AuditRecord]:
        ordered = sorted(
            self._records, key=lambda r: (r.timestamp, r.id), reverse=True
        )
        return [copy.deepcopy(r) for r in ordered[:limit]]

    async def list_for_target(
        self, target: str, *, limit: int = 100
    ) -> list[AuditRecord]:
        matches = [r for r in self._records if r.target == target]
        matches.sort(key=lambda r: (r.timestamp, r.id), reverse=True)
        return [copy.deepcopy(r) for r in matches[:limit]]


class FakeBillRepository:
    def __init__(self) -> None:
        self._bills: dict[str, Bill] = {}
        self._payees: dict[str, Payee] = {}

    async def get(self, bill_id: str) -> Bill | None:
        found = self._bills.get(bill_id)
        return copy.deepcopy(found) if found else None

    async def list_bills(
        self, *, statuses: list[BillStatus] | None = None, limit: int = 100
    ) -> list[Bill]:
        wanted = set(statuses) if statuses is not None else None
        matches = [b for b in self._bills.values() if wanted is None or b.status in wanted]
        # Soonest due first, undated last: a bill with no due date is not more
        # urgent than one due tomorrow.
        matches.sort(key=lambda b: (b.due_at is None, b.due_at or "", b.id))
        return [copy.deepcopy(b) for b in matches[:limit]]

    async def list_for_payee(self, payee_id: str) -> list[Bill]:
        matches = [b for b in self._bills.values() if b.payee_id == payee_id]
        matches.sort(key=lambda b: (b.created_at, b.id), reverse=True)
        return [copy.deepcopy(b) for b in matches]

    async def create(self, bill: Bill) -> Bill:
        self._bills[bill.id] = copy.deepcopy(bill)
        return copy.deepcopy(bill)

    async def update(self, bill: Bill) -> Bill:
        if bill.id not in self._bills:
            raise NotFoundError(f"bill {bill.id} does not exist", bill_id=bill.id)
        self._bills[bill.id] = copy.deepcopy(bill)
        return copy.deepcopy(bill)

    async def get_payee(self, payee_id: str) -> Payee | None:
        found = self._payees.get(payee_id)
        return copy.deepcopy(found) if found else None

    async def list_payees(self) -> list[Payee]:
        ordered = sorted(self._payees.values(), key=lambda p: p.display_name)
        return [copy.deepcopy(p) for p in ordered]

    async def upsert_payee(self, payee: Payee) -> Payee:
        existing = self._payees.get(payee.id)
        stored = copy.deepcopy(payee)
        if existing is not None:
            stored.created_at = existing.created_at or stored.created_at
            if existing.is_approved and not stored.is_approved:
                # Section 72: approval is a fact about a payee, not a field a
                # later write may quietly reset.
                stored.approved_at = existing.approved_at
                stored.approved_by = existing.approved_by
        self._payees[payee.id] = stored
        return copy.deepcopy(stored)

    async def clear_payee_approval(self, payee_id: str) -> Payee:
        stored = self._payees.get(payee_id)
        if stored is None:
            raise NotFoundError(f"no such payee: {payee_id}", payee_id=payee_id)
        stored.approved_at = None
        stored.approved_by = None
        return copy.deepcopy(stored)


class FakeWorkflowTemplateRepository:
    def __init__(self) -> None:
        self._templates: dict[str, WorkflowTemplate] = {}

    async def get(self, template_id: str) -> WorkflowTemplate | None:
        found = self._templates.get(template_id)
        return copy.deepcopy(found) if found else None

    async def list_templates(self, *, limit: int = 100) -> list[WorkflowTemplate]:
        ordered = sorted(self._templates.values(), key=lambda t: t.name)
        return [copy.deepcopy(t) for t in ordered[:limit]]

    async def list_due(self, *, now: str, limit: int = 50) -> list[WorkflowTemplate]:
        due = [
            t for t in self._templates.values()
            if t.enabled and t.next_run_at is not None and t.next_run_at <= now
        ]
        due.sort(key=lambda t: (t.next_run_at or "", t.id))
        return [copy.deepcopy(t) for t in due[:limit]]

    async def upsert(self, template: WorkflowTemplate) -> WorkflowTemplate:
        self._templates[template.id] = copy.deepcopy(template)
        return copy.deepcopy(template)

    async def delete(self, template_id: str) -> bool:
        return self._templates.pop(template_id, None) is not None


class FakeShoppingRepository:
    def __init__(self) -> None:
        self._lists: dict[str, ShoppingList] = {}

    async def get(self, list_id: str) -> ShoppingList | None:
        found = self._lists.get(list_id)
        return copy.deepcopy(found) if found else None

    async def list_all(self, *, limit: int = 100) -> list[ShoppingList]:
        ordered = sorted(
            self._lists.values(), key=lambda s: (s.created_at, s.id), reverse=True
        )
        return [copy.deepcopy(s) for s in ordered[:limit]]

    async def find_lists_containing(self, item_name: str) -> list[ShoppingList]:
        needle = item_name.strip().lower()
        matches = [
            s
            for s in self._lists.values()
            if any(needle in item.name.lower() for item in s.items)
        ]
        matches.sort(key=lambda s: (s.created_at, s.id), reverse=True)
        return [copy.deepcopy(s) for s in matches]

    async def upsert(self, shopping_list: ShoppingList) -> ShoppingList:
        self._lists[shopping_list.id] = copy.deepcopy(shopping_list)
        return copy.deepcopy(shopping_list)

    async def delete(self, list_id: str) -> bool:
        return self._lists.pop(list_id, None) is not None


class FakeServiceRequestRepository:
    def __init__(self) -> None:
        self._requests: dict[str, ServiceRequest] = {}

    async def get(self, request_id: str) -> ServiceRequest | None:
        found = self._requests.get(request_id)
        return copy.deepcopy(found) if found else None

    async def list_all(self, *, limit: int = 100) -> list[ServiceRequest]:
        ordered = sorted(
            self._requests.values(), key=lambda r: (r.created_at, r.id), reverse=True
        )
        return [copy.deepcopy(r) for r in ordered[:limit]]

    async def list_for_provider(self, provider_entity_id: str) -> list[ServiceRequest]:
        matches = [
            r for r in self._requests.values()
            if r.provider_entity_id == provider_entity_id
        ]
        matches.sort(key=lambda r: (r.created_at, r.id), reverse=True)
        return [copy.deepcopy(r) for r in matches]

    async def upsert(self, request: ServiceRequest) -> ServiceRequest:
        self._requests[request.id] = copy.deepcopy(request)
        return copy.deepcopy(request)


__all__ = [
    "FakeActionRepository",
    "FakeApprovalRepository",
    "FakeBillRepository",
    "FakeAuditRepository",
    "FakeMemoryRepository",
    "FakePersonRepository",
    "FakePreferenceRepository",
    "FakeServiceRequestRepository",
    "FakeShoppingRepository",
    "FakeTaskRepository",
    "FakeWaitingRepository",
    "FakeWorkflowTemplateRepository",
    "FakeWorldRepository",
]
