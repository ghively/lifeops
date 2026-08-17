"""LifeOpsCore — the single application service.

Every meaningful state change passes through here (BUILD_SPEC section 3).
Agents do not mutate NornicDB, the Console does not mutate NornicDB, and
integrations do not mutate NornicDB. They call these operations.

The HTTP API and the MCP server are both thin adapters over this class. That
is deliberate: if each surface orchestrated its own repository calls, the
capability checks and state-machine rules would drift apart, and the MCP path
is precisely the one where drift is least visible.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from lifeops.clock import Clock, SystemClock, now_iso
from lifeops.domain.memory import (
    MemoryDraft,
    MemoryRecord,
    MemoryType,
    validate_durable_content,
)
from lifeops.domain.people import Person, PersonDraft
from lifeops.domain.preferences import (
    Preference,
    PreferenceDraft,
    PreferenceSource,
    normalise_key,
)
from lifeops.domain.search import SearchResults
from lifeops.domain.tasks import (
    Task,
    TaskDraft,
    TaskState,
    TaskUpdate,
    VerificationState,
    apply_transition,
)
from lifeops.errors import (
    ConfigurationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from lifeops.events import (
    MEMORY_CHANGED,
    PERSON_CHANGED,
    PREFERENCE_CHANGED,
    TASK_CHANGED,
    EventBus,
)
from lifeops.ids import PREFIX_PERSON, slug_id
from lifeops.observability.logging import operation
from lifeops.policy import Capability, ClientIdentity, require
from lifeops.policy.trust import may_supersede
from lifeops.repositories.interfaces import (
    MemoryRepository,
    PersonRepository,
    PreferenceRepository,
    TaskRepository,
)

logger = logging.getLogger(__name__)


class MemoryService:
    """Memory operations (BUILD_SPEC sections 42–47).

    Section 44 is enforced by construction: this service holds only a
    ``MemoryRepository`` (plus clock and event publishing). It has no
    reference to tasks, preferences, approvals, payments, or idempotency
    state, so no memory operation — whatever a caller asks for — can rewrite
    transactional reality. Subject resolution and capability checks stay on
    ``LifeOpsCore``, which delegates here once they pass.
    """

    def __init__(
        self,
        *,
        memories: MemoryRepository,
        clock: Clock,
        publish: Callable[[str], None] | None = None,
    ) -> None:
        self._memories = memories
        self._clock = clock
        self._publish_event = publish

    def _notify(self, memory: MemoryRecord) -> None:
        if self._publish_event is not None:
            self._publish_event(memory.id)

    async def remember(
        self, draft: MemoryDraft, *, subject_id: str, client_id: str
    ) -> MemoryRecord:
        """Persist a memory after the section 47 durability rules pass."""
        content = validate_durable_content(draft.content)

        # Re-stating an identical memory is a no-op rather than a new record,
        # so repeated conversation turns do not pile up duplicates.
        duplicate = await self._memories.get_current_duplicate(
            subject_id, draft.type, content
        )
        if duplicate is not None:
            return duplicate

        now = now_iso(self._clock)
        memory = MemoryRecord(
            id=MemoryRecord.make_id(),
            subject_id=subject_id,
            type=draft.type,
            content=content,
            source_type=draft.source_type,
            source_id=draft.source_id,
            confidence=draft.confidence,
            importance=draft.importance,
            observed_at=draft.observed_at or now,
            created_at=now,
            valid_from=now,
            valid_to=None,
            supersedes=None,
            entity_ids=draft.entity_ids,
            created_by_client=client_id,
        )
        with operation(
            "memory.write",
            memory_type=str(memory.type),
            subject_id=subject_id,
            client_id=client_id,
        ):
            saved = await self._memories.save_superseding(memory, supersedes=None)
        self._notify(saved)
        return saved

    async def recall(
        self,
        *,
        query: str = "",
        subject_id: str | None = None,
        memory_types: list[MemoryType] | None = None,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        """Current memories matching a query; blank query lists the most relevant."""
        if query.strip():
            return await self._memories.search(
                query, subject_id=subject_id, memory_types=memory_types, limit=limit
            )
        return await self._memories.list_current(
            subject_id, memory_types=memory_types, limit=limit
        )

    async def get(self, memory_id: str) -> MemoryRecord:
        memory = await self._memories.get(memory_id)
        if memory is None:
            raise NotFoundError(f"no such memory: {memory_id}", memory_id=memory_id)
        return memory

    async def history(self, memory_id: str) -> list[MemoryRecord]:
        memory = await self._memories.get(memory_id)
        if memory is None:
            raise NotFoundError(f"no such memory: {memory_id}", memory_id=memory_id)
        return await self._memories.list_history(memory_id)

    async def invalidate(
        self, memory_id: str, *, reason: str | None, client_id: str
    ) -> MemoryRecord:
        """Close a memory's validity window without replacing it."""
        with operation("memory.invalidate", memory_id=memory_id, client_id=client_id):
            updated = await self._memories.invalidate(
                memory_id, at=now_iso(self._clock), reason=reason
            )
        if updated is None:
            raise NotFoundError(f"no such memory: {memory_id}", memory_id=memory_id)
        self._notify(updated)
        return updated

    async def correct(
        self,
        memory_id: str,
        *,
        new_content: str,
        source_type: PreferenceSource,
        confidence: float,
        importance: float | None,
        client_id: str,
    ) -> MemoryRecord:
        """Replace a memory's content through temporal supersession.

        Nothing is edited in place: the old record's window closes and the
        correction opens a new record pointing back with SUPERSEDES.
        """
        existing = await self._memories.get(memory_id)
        if existing is None:
            raise NotFoundError(f"no such memory: {memory_id}", memory_id=memory_id)
        if not existing.is_current:
            raise ConflictError(
                f"memory {memory_id} is already invalidated or superseded; "
                "correct the current version instead",
                memory_id=memory_id,
                reason="memory_not_current",
            )
        # A weaker source may not silently displace a stronger one (section 46).
        if not may_supersede(source_type, existing.source_type):
            raise ConflictError(
                f"memory was recorded from a more authoritative source "
                f"({existing.source_type}); this correction ({source_type}) "
                "cannot replace it",
                memory_id=memory_id,
                existing_source=str(existing.source_type),
                incoming_source=str(source_type),
            )

        content = validate_durable_content(new_content)
        if existing.content == content:
            return existing

        now = now_iso(self._clock)
        correction = MemoryRecord(
            id=MemoryRecord.make_id(),
            subject_id=existing.subject_id,
            type=existing.type,
            content=content,
            source_type=source_type,
            source_id=None,
            confidence=confidence,
            importance=importance if importance is not None else existing.importance,
            observed_at=now,
            created_at=now,
            valid_from=now,
            valid_to=None,
            supersedes=existing.id,
            entity_ids=list(existing.entity_ids),
            created_by_client=client_id,
        )
        with operation(
            "memory.correct",
            memory_id=memory_id,
            supersedes=existing.id,
            client_id=client_id,
        ):
            saved = await self._memories.save_superseding(correction, supersedes=existing)
        self._notify(saved)
        return saved


class LifeOpsCore:
    def __init__(
        self,
        *,
        people: PersonRepository,
        preferences: PreferenceRepository,
        tasks: TaskRepository,
        memory: MemoryRepository | None = None,
        clock: Clock | None = None,
        safe_mode: bool = False,
        events: EventBus | None = None,
    ) -> None:
        self._people = people
        self._preferences = preferences
        self._tasks = tasks
        self._clock = clock or SystemClock()
        self.safe_mode = safe_mode
        self._events = events
        # Memory is deliberately segregated behind its own service (section
        # 44): nothing here hands it the task or preference repositories.
        self._memory_service = (
            MemoryService(
                memories=memory,
                clock=self._clock,
                publish=(
                    lambda memory_id: self._publish(MEMORY_CHANGED, memory_id=memory_id)
                ),
            )
            if memory is not None
            else None
        )

    def _require(self, client: ClientIdentity, capability: Capability) -> None:
        require(client, capability, safe_mode=self.safe_mode)

    def _publish(self, event_type: str, **fields: object) -> None:
        """Notify Console subscribers after a successful mutation.

        Best-effort by design: a missed event costs one refetch, so a broker
        failure must never fail the mutation that triggered it (events.py).
        """
        if self._events is not None:
            self._events.publish({"type": event_type, **fields})

    # --- people -------------------------------------------------------------

    async def get_person(
        self, client: ClientIdentity, *, person_id: str | None = None
    ) -> Person:
        """Fetch a person, defaulting to the primary user.

        ``get_person()`` with no argument is the common case: an agent asking
        "who am I acting for?".
        """
        self._require(client, Capability.READ_WORLD)

        with operation("person.get", person_id=person_id, client_id=client.client_id):
            person = (
                await self._people.get(person_id)
                if person_id
                else await self._people.get_primary()
            )

        if person is None:
            raise NotFoundError(
                f"no such person: {person_id}" if person_id else "no primary person is set",
                person_id=person_id,
            )
        return person

    async def find_people(self, client: ClientIdentity, *, name: str) -> list[Person]:
        self._require(client, Capability.READ_WORLD)
        return await self._people.find_by_name(name)

    async def list_people(self, client: ClientIdentity, *, limit: int = 100) -> list[Person]:
        self._require(client, Capability.READ_WORLD)
        return await self._people.list_all(limit=limit)

    async def create_person(
        self, client: ClientIdentity, draft: PersonDraft
    ) -> Person:
        # Creating people is world-shaping rather than preference-stating, so
        # it sits behind the same capability that guards preference writes
        # until Phase 3 gives it a capability of its own.
        self._require(client, Capability.WRITE_PREFERENCE)

        now = now_iso(self._clock)
        person_id = slug_id(PREFIX_PERSON, draft.display_name)

        existing = await self._people.get(person_id)
        if existing is not None:
            raise ConflictError(
                f"person {person_id} already exists", person_id=person_id
            )

        person = Person(
            id=person_id,
            display_name=draft.display_name,
            is_primary=draft.is_primary,
            aliases=draft.aliases,
            timezone=draft.timezone,
            created_at=now,
            updated_at=now,
        )
        with operation("person.create", person_id=person_id, client_id=client.client_id):
            created = await self._people.upsert(person)
        self._publish(PERSON_CHANGED, person_id=created.id)
        return created

    async def ensure_primary_person(self, display_name: str) -> Person:
        """Create the primary person if none exists yet.

        Used by first-run setup. Idempotent, so re-running bootstrap does not
        fork the user's identity.
        """
        existing = await self._people.get_primary()
        if existing is not None:
            return existing

        now = now_iso(self._clock)
        person = Person(
            id=slug_id(PREFIX_PERSON, display_name),
            display_name=display_name,
            is_primary=True,
            created_at=now,
            updated_at=now,
        )
        return await self._people.upsert(person)

    async def _resolve_subject(self, subject_id: str | None) -> str:
        if subject_id:
            person = await self._people.get(subject_id)
            if person is None:
                raise NotFoundError(f"no such person: {subject_id}", person_id=subject_id)
            return person.id

        primary = await self._people.get_primary()
        if primary is None:
            raise NotFoundError(
                "no primary person is set; run first-run setup before saving "
                "preferences"
            )
        return primary.id

    # --- memory (BUILD_SPEC sections 42–47) -----------------------------------

    def _memory(self) -> MemoryService:
        if self._memory_service is None:
            raise ConfigurationError(
                "no memory repository is configured", component="memory"
            )
        return self._memory_service

    async def remember(self, client: ClientIdentity, draft: MemoryDraft) -> MemoryRecord:
        """Store a durable memory (section 47 durability rules apply).

        This records an observation; it executes nothing and changes no
        transactional state (section 44).
        """
        self._require(client, Capability.WRITE_MEMORY)
        resolved = await self._resolve_subject(draft.subject_id)
        return await self._memory().remember(
            draft, subject_id=resolved, client_id=client.client_id
        )

    async def recall(
        self,
        client: ClientIdentity,
        *,
        query: str = "",
        subject_id: str | None = None,
        memory_types: list[MemoryType] | None = None,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        """Search current memories. A blank query lists the most relevant."""
        self._require(client, Capability.READ_MEMORY)
        if subject_id is not None:
            resolved: str | None = await self._resolve_subject(subject_id)
        else:
            resolved = None  # recall spans subjects unless one is named
        with operation("memory.recall", client_id=client.client_id):
            return await self._memory().recall(
                query=query, subject_id=resolved, memory_types=memory_types, limit=limit
            )

    async def get_memory(self, client: ClientIdentity, *, memory_id: str) -> MemoryRecord:
        self._require(client, Capability.READ_MEMORY)
        return await self._memory().get(memory_id)

    async def memory_history(
        self, client: ClientIdentity, *, memory_id: str
    ) -> list[MemoryRecord]:
        """Every version of a memory, newest first (section 45 provenance)."""
        self._require(client, Capability.READ_MEMORY)
        return await self._memory().history(memory_id)

    async def invalidate_memory(
        self, client: ClientIdentity, *, memory_id: str, reason: str | None = None
    ) -> MemoryRecord:
        """Close a memory's validity window. The record is kept, not deleted."""
        self._require(client, Capability.WRITE_MEMORY)
        return await self._memory().invalidate(
            memory_id, reason=reason, client_id=client.client_id
        )

    async def correct_memory(
        self,
        client: ClientIdentity,
        *,
        memory_id: str,
        new_content: str,
        source_type: PreferenceSource = PreferenceSource.USER_EXPLICIT,
        confidence: float = 1.0,
        importance: float | None = None,
    ) -> MemoryRecord:
        """Correct a memory by superseding it; the old version stays queryable."""
        self._require(client, Capability.WRITE_MEMORY)
        return await self._memory().correct(
            memory_id,
            new_content=new_content,
            source_type=source_type,
            confidence=confidence,
            importance=importance,
            client_id=client.client_id,
        )

    # --- preferences --------------------------------------------------------

    async def get_preferences(
        self,
        client: ClientIdentity,
        *,
        subject_id: str | None = None,
        key_prefix: str | None = None,
    ) -> list[Preference]:
        """Current preferences for a subject."""
        self._require(client, Capability.READ_PREFERENCES)
        resolved = await self._resolve_subject(subject_id)

        with operation(
            "preference.list", subject_id=resolved, client_id=client.client_id
        ):
            return await self._preferences.list_current(
                resolved, key_prefix=normalise_key(key_prefix) if key_prefix else None
            )

    async def get_preference_history(
        self, client: ClientIdentity, *, key: str, subject_id: str | None = None
    ) -> list[Preference]:
        self._require(client, Capability.READ_PREFERENCES)
        resolved = await self._resolve_subject(subject_id)
        return await self._preferences.list_history(resolved, normalise_key(key))

    async def save_preference(
        self, client: ClientIdentity, draft: PreferenceDraft
    ) -> Preference:
        """Record a preference, superseding any current value for the key.

        Nothing is overwritten. The previous record's validity window is
        closed and the new one points at it with SUPERSEDES, so the history in
        BUILD_SPEC section 40 is queryable rather than lost.
        """
        self._require(client, Capability.WRITE_PREFERENCE)

        key = normalise_key(draft.key)
        if not key:
            raise ValidationError("preference key must not be empty", field="key")

        resolved = await self._resolve_subject(draft.subject_id)
        now = now_iso(self._clock)
        current = await self._preferences.get_current_by_key(resolved, key)

        if current is not None:
            # A weaker source may not silently displace a stronger one. A web
            # page or a model guess does not get to overwrite something the
            # user stated directly (section 46).
            if not may_supersede(draft.source_type, current.source_type):
                raise ConflictError(
                    f"a preference for {key!r} from a more authoritative source "
                    f"({current.source_type}) is already recorded; this claim "
                    f"({draft.source_type}) cannot replace it",
                    key=key,
                    existing_source=str(current.source_type),
                    incoming_source=str(draft.source_type),
                    existing_preference_id=current.id,
                )
            # Re-stating an identical value is a no-op rather than a new
            # record, so repeated conversation turns do not pile up history.
            if current.value.strip() == draft.value.strip():
                return current

        preference = Preference(
            id=Preference.make_id(),
            subject_id=resolved,
            key=key,
            value=draft.value.strip(),
            source_type=draft.source_type,
            source_id=draft.source_id,
            confidence=draft.confidence,
            importance=draft.importance,
            observed_at=draft.observed_at or now,
            created_at=now,
            valid_from=now,
            valid_to=None,
            supersedes=current.id if current else None,
            created_by_client=client.client_id,
            notes=draft.notes,
        )

        with operation(
            "preference.write",
            key=key,
            subject_id=resolved,
            client_id=client.client_id,
            supersedes=current.id if current else None,
        ):
            saved = await self._preferences.save_superseding(
                preference, supersedes=current
            )
        self._publish(PREFERENCE_CHANGED, key=key, subject_id=resolved)
        return saved

    async def invalidate_preference(
        self, client: ClientIdentity, *, preference_id: str
    ) -> Preference:
        """Close a preference's validity window without replacing it."""
        self._require(client, Capability.WRITE_PREFERENCE)

        updated = await self._preferences.invalidate(
            preference_id, at=now_iso(self._clock)
        )
        if updated is None:
            raise NotFoundError(
                f"no such preference: {preference_id}", preference_id=preference_id
            )
        self._publish(PREFERENCE_CHANGED, key=updated.key, subject_id=updated.subject_id)
        return updated

    # --- tasks --------------------------------------------------------------

    async def create_task(self, client: ClientIdentity, draft: TaskDraft) -> Task:
        self._require(client, Capability.CREATE_TASK)

        now = now_iso(self._clock)
        owner = draft.owner_entity_id
        if owner is None:
            primary = await self._people.get_primary()
            owner = primary.id if primary else None
        elif await self._people.get(owner) is None:
            raise NotFoundError(f"no such person: {owner}", person_id=owner)

        task = Task(
            id=Task.make_id(),
            title=draft.title.strip(),
            description=draft.description,
            state=draft.state,
            priority=draft.priority,
            created_at=now,
            updated_at=now,
            due_at=draft.due_at,
            owner_entity_id=owner,
            assigned_client=None,
            verification_required=draft.verification_required,
            verification_state=(
                VerificationState.PENDING
                if draft.verification_required
                else VerificationState.NOT_REQUIRED
            ),
            related_entity_ids=draft.related_entity_ids,
            source=draft.source,
            created_by_client=client.client_id,
        )

        with operation("task.create", task_id=task.id, client_id=client.client_id):
            created = await self._tasks.create(task)
        self._publish(TASK_CHANGED, task_id=created.id)
        return created

    async def get_task(self, client: ClientIdentity, *, task_id: str) -> Task:
        self._require(client, Capability.READ_TASKS)
        task = await self._tasks.get(task_id)
        if task is None:
            raise NotFoundError(f"no such task: {task_id}", task_id=task_id)
        return task

    async def list_tasks(
        self,
        client: ClientIdentity,
        *,
        states: list[TaskState] | None = None,
        owner_entity_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        self._require(client, Capability.READ_TASKS)
        with operation("task.list", client_id=client.client_id):
            return await self._tasks.list(
                states=states,
                owner_entity_id=owner_entity_id,
                limit=limit,
                offset=offset,
            )

    async def count_tasks_by_state(self, client: ClientIdentity) -> dict[str, int]:
        self._require(client, Capability.READ_TASKS)
        return await self._tasks.count_by_state()

    async def update_task(
        self, client: ClientIdentity, *, task_id: str, update: TaskUpdate
    ) -> Task:
        """Apply a partial update, validating any state change.

        The state change runs through the state machine rather than being
        assigned, so an illegal transition proposed by a model is rejected
        here instead of being written and discovered later.
        """
        self._require(client, Capability.UPDATE_TASK)

        task = await self._tasks.get(task_id)
        if task is None:
            raise NotFoundError(f"no such task: {task_id}", task_id=task_id)

        now = now_iso(self._clock)
        working = task.model_copy(deep=True)

        for field in (
            "title",
            "description",
            "priority",
            "due_at",
            "current_action",
            "related_entity_ids",
            "verification_evidence",
        ):
            value = getattr(update, field)
            if value is not None:
                setattr(working, field, value)

        if update.owner_entity_id is not None:
            if await self._people.get(update.owner_entity_id) is None:
                raise NotFoundError(
                    f"no such person: {update.owner_entity_id}",
                    person_id=update.owner_entity_id,
                )
            working.owner_entity_id = update.owner_entity_id

        working.updated_at = now

        if update.state is not None and update.state != task.state:
            with operation(
                "task.transition",
                task_id=task_id,
                from_state=str(task.state),
                to_state=str(update.state),
                client_id=client.client_id,
            ):
                working = apply_transition(
                    working,
                    update.state,
                    now=now,
                    verification_evidence=update.verification_evidence,
                    actor_client=client.client_id,
                )

        updated = await self._tasks.update(working)
        self._publish(TASK_CHANGED, task_id=updated.id)
        return updated

    # --- search -------------------------------------------------------------

    async def search(
        self, client: ClientIdentity, *, query: str, limit: int = 10
    ) -> SearchResults:
        """Universal search over people, preferences, and tasks (section 19).

        Phase 1 is a case-insensitive substring match; ranking and semantic
        retrieval arrive with the memory layer (Phase 2).
        """
        self._require(client, Capability.READ_WORLD)
        with operation("search.query", client_id=client.client_id):
            return SearchResults(
                people=await self._people.find_by_name(query),
                preferences=await self._preferences.search(query, limit=limit),
                tasks=list(await self._tasks.search(query, limit=limit)),
            )
