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

from lifeops.clock import Clock, SystemClock, now_iso
from lifeops.domain.people import Person, PersonDraft
from lifeops.domain.preferences import (
    Preference,
    PreferenceDraft,
    normalise_key,
)
from lifeops.domain.tasks import (
    Task,
    TaskDraft,
    TaskState,
    TaskUpdate,
    VerificationState,
    apply_transition,
)
from lifeops.errors import ConflictError, NotFoundError, ValidationError
from lifeops.ids import PREFIX_PERSON, slug_id
from lifeops.observability.logging import operation
from lifeops.policy import Capability, ClientIdentity, require
from lifeops.policy.trust import may_supersede
from lifeops.repositories.interfaces import (
    PersonRepository,
    PreferenceRepository,
    TaskRepository,
)

logger = logging.getLogger(__name__)


class LifeOpsCore:
    def __init__(
        self,
        *,
        people: PersonRepository,
        preferences: PreferenceRepository,
        tasks: TaskRepository,
        clock: Clock | None = None,
        safe_mode: bool = False,
    ) -> None:
        self._people = people
        self._preferences = preferences
        self._tasks = tasks
        self._clock = clock or SystemClock()
        self.safe_mode = safe_mode

    def _require(self, client: ClientIdentity, capability: Capability) -> None:
        require(client, capability, safe_mode=self.safe_mode)

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
            return await self._people.upsert(person)

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
            return await self._preferences.save_superseding(
                preference, supersedes=current
            )

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
            return await self._tasks.create(task)

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

        return await self._tasks.update(working)
