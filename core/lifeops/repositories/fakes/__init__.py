"""In-memory repository fakes.

These exist so domain and policy tests can run without NornicDB. They are the
practical proof that the repository abstraction holds: if a domain test needs
Cypher to pass, the abstraction has leaked.

They are not a second storage backend and must never be wired into a running
LifeOps deployment — nothing here survives a process restart.
"""

from __future__ import annotations

import copy
from collections.abc import Sequence

from lifeops.domain.memory import MemoryRecord, MemoryType
from lifeops.domain.people import Person
from lifeops.domain.preferences import Preference
from lifeops.domain.tasks import Task, TaskState
from lifeops.domain.world import (
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

    async def list_related_to_entity(self, entity_id: str) -> list[Task]:
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


__all__ = [
    "FakeMemoryRepository",
    "FakePersonRepository",
    "FakePreferenceRepository",
    "FakeTaskRepository",
    "FakeWorldRepository",
]
