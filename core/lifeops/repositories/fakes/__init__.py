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

from lifeops.domain.people import Person
from lifeops.domain.preferences import Preference
from lifeops.domain.tasks import Task, TaskState
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

    async def create(self, task: Task) -> Task:
        self._tasks[task.id] = copy.deepcopy(task)
        return copy.deepcopy(task)

    async def update(self, task: Task) -> Task:
        if task.id not in self._tasks:
            raise NotFoundError(f"task {task.id} does not exist", task_id=task.id)
        self._tasks[task.id] = copy.deepcopy(task)
        return copy.deepcopy(task)


__all__ = [
    "FakePersonRepository",
    "FakePreferenceRepository",
    "FakeTaskRepository",
]
