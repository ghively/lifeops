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

from lifeops.domain.memory import MemoryRecord, MemoryType
from lifeops.domain.people import Person
from lifeops.domain.preferences import Preference
from lifeops.domain.tasks import Task, TaskState


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


@runtime_checkable
class HealthCheck(Protocol):
    async def ping(self) -> bool: ...
