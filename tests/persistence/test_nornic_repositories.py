"""Repository behaviour against a live NornicDB.

The fakes prove the domain rules; only these prove that the Cypher is right,
that the graph shape is what the World screen will later traverse, and that
the temporal invariants survive a real transaction.

Skipped automatically when NornicDB is not reachable.
"""

from __future__ import annotations

import pytest

from lifeops.clock import FrozenClock
from lifeops.core import LifeOpsCore
from lifeops.domain.people import Person
from lifeops.domain.preferences import PreferenceDraft
from lifeops.domain.tasks import TaskDraft, TaskState, TaskUpdate
from lifeops.errors import InvalidTransitionError, NotFoundError
from lifeops.policy import HERMES
from lifeops.repositories.nornic.client import NornicClient
from lifeops.repositories.nornic.people import NornicPersonRepository
from lifeops.repositories.nornic.preferences import NornicPreferenceRepository
from lifeops.repositories.nornic.tasks import NornicTaskRepository

pytestmark = [pytest.mark.integration, pytest.mark.persistence]


@pytest.fixture
async def stack(nornic_client: NornicClient, test_label: str):
    """Repositories plus an isolated primary person for one test."""
    people = NornicPersonRepository(nornic_client)
    preferences = NornicPreferenceRepository(nornic_client)
    tasks = NornicTaskRepository(nornic_client)
    clock = FrozenClock()

    person = Person(
        id=f"person_{test_label}",
        display_name=f"Subject {test_label}",
        is_primary=False,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    await people.upsert(person)

    core = LifeOpsCore(
        people=people, preferences=preferences, tasks=tasks, clock=clock
    )
    try:
        yield core, person, clock, nornic_client
    finally:
        # Leave no residue in a shared database. Everything this test created
        # hangs off its own Person, so matching on owner catches tasks whether
        # or not they set `source` — matching on `source` alone silently leaked
        # every task that did not.
        await nornic_client.write(
            "MATCH (t:Task) WHERE t.owner_entity_id = $id DETACH DELETE t",
            id=person.id,
        )
        await nornic_client.write(
            "MATCH (p:Preference) WHERE p.subject_id = $id DETACH DELETE p",
            id=person.id,
        )
        await nornic_client.write(
            "MATCH (p:Person {id: $id}) DETACH DELETE p", id=person.id
        )


class TestPersonRepository:
    async def test_round_trip(self, stack) -> None:
        core, person, _, _ = stack
        fetched = await core.get_person(HERMES, person_id=person.id)
        assert fetched.display_name == person.display_name

    async def test_find_by_name_is_case_insensitive(self, stack) -> None:
        core, person, _, _ = stack
        found = await core.find_people(HERMES, name=person.display_name.upper())
        assert person.id in {p.id for p in found}

    async def test_unknown_person_raises(self, stack) -> None:
        core, _, _, _ = stack
        with pytest.raises(NotFoundError):
            await core.get_person(HERMES, person_id="person_definitely_absent")


class TestPreferenceTemporalWrites:
    async def test_save_and_read_current(self, stack) -> None:
        core, person, _, _ = stack
        await core.save_preference(
            HERMES,
            PreferenceDraft(
                key="scheduling.earliest",
                value="No appointments before 10 AM",
                subject_id=person.id,
            ),
        )
        current = await core.get_preferences(HERMES, subject_id=person.id)
        assert [p.value for p in current] == ["No appointments before 10 AM"]

    async def test_supersession_leaves_exactly_one_current_value(self, stack) -> None:
        core, person, clock, _ = stack
        for value in ("after 10", "after 9", "after 8"):
            clock.advance(3600)
            await core.save_preference(
                HERMES,
                PreferenceDraft(
                    key="scheduling.earliest", value=value, subject_id=person.id
                ),
            )

        current = await core.get_preferences(HERMES, subject_id=person.id)
        assert len(current) == 1
        assert current[0].value == "after 8"

        history = await core.get_preference_history(
            HERMES, key="scheduling.earliest", subject_id=person.id
        )
        assert len(history) == 3
        assert sum(1 for p in history if p.is_current) == 1

    async def test_supersedes_edge_exists_in_the_graph(self, stack) -> None:
        core, person, clock, client = stack
        first = await core.save_preference(
            HERMES,
            PreferenceDraft(key="k.one", value="v1", subject_id=person.id),
        )
        clock.advance(60)
        second = await core.save_preference(
            HERMES,
            PreferenceDraft(key="k.one", value="v2", subject_id=person.id),
        )

        rows = await client.read(
            "MATCH (new:Preference {id: $new})-[:SUPERSEDES]->(old:Preference) "
            "RETURN old.id AS old_id",
            new=second.id,
        )
        assert [r["old_id"] for r in rows] == [first.id]

    async def test_prefers_edge_connects_person_to_preference(self, stack) -> None:
        core, person, _, client = stack
        pref = await core.save_preference(
            HERMES,
            PreferenceDraft(key="k.two", value="v", subject_id=person.id),
        )
        rows = await client.read(
            "MATCH (:Person {id: $pid})-[:PREFERS]->(p:Preference {id: $prid}) "
            "RETURN p.id AS id",
            pid=person.id,
            prid=pref.id,
        )
        assert len(rows) == 1

    async def test_invalidate_closes_the_window_without_deleting(self, stack) -> None:
        core, person, _, client = stack
        pref = await core.save_preference(
            HERMES, PreferenceDraft(key="k.three", value="v", subject_id=person.id)
        )
        await core.invalidate_preference(HERMES, preference_id=pref.id)

        assert await core.get_preferences(HERMES, subject_id=person.id) == []
        rows = await client.read(
            "MATCH (p:Preference {id: $id}) RETURN p.valid_to AS valid_to", id=pref.id
        )
        assert rows[0]["valid_to"] is not None


class TestTaskRepository:
    async def test_create_and_fetch(self, stack) -> None:
        core, person, _, _ = stack
        task = await core.create_task(
            HERMES,
            TaskDraft(
                title="Call dentist", owner_entity_id=person.id, source="test:tasks"
            ),
        )
        fetched = await core.get_task(HERMES, task_id=task.id)
        assert fetched.title == "Call dentist"
        assert fetched.state is TaskState.CAPTURED

    async def test_assigned_to_edge_exists(self, stack) -> None:
        core, person, _, client = stack
        task = await core.create_task(
            HERMES, TaskDraft(title="t", owner_entity_id=person.id)
        )
        rows = await client.read(
            "MATCH (t:Task {id: $tid})-[:ASSIGNED_TO]->(:Person {id: $pid}) "
            "RETURN t.id AS id",
            tid=task.id,
            pid=person.id,
        )
        assert len(rows) == 1

    async def test_state_transition_persists(self, stack) -> None:
        core, person, _, _ = stack
        task = await core.create_task(
            HERMES, TaskDraft(title="t", owner_entity_id=person.id)
        )
        await core.update_task(
            HERMES, task_id=task.id, update=TaskUpdate(state=TaskState.READY)
        )
        assert (await core.get_task(HERMES, task_id=task.id)).state is TaskState.READY

    async def test_illegal_transition_writes_nothing(self, stack) -> None:
        core, person, _, _ = stack
        task = await core.create_task(
            HERMES, TaskDraft(title="t", owner_entity_id=person.id)
        )
        with pytest.raises(InvalidTransitionError):
            await core.update_task(
                HERMES, task_id=task.id, update=TaskUpdate(state=TaskState.COMPLETED)
            )
        assert (await core.get_task(HERMES, task_id=task.id)).state is TaskState.CAPTURED

    async def test_list_filters_by_state(self, stack) -> None:
        core, person, _, _ = stack
        first = await core.create_task(
            HERMES, TaskDraft(title="one", owner_entity_id=person.id)
        )
        await core.create_task(HERMES, TaskDraft(title="two", owner_entity_id=person.id))
        await core.update_task(
            HERMES, task_id=first.id, update=TaskUpdate(state=TaskState.READY)
        )

        ready = await core.list_tasks(
            HERMES, states=[TaskState.READY], owner_entity_id=person.id
        )
        assert [t.title for t in ready] == ["one"]

    async def test_updating_a_missing_task_raises(self, stack) -> None:
        core, _, _, _ = stack
        with pytest.raises(NotFoundError):
            await core.update_task(
                HERMES, task_id="task_absent", update=TaskUpdate(state=TaskState.READY)
            )


class TestNoParallelStore:
    """BUILD_SPEC exit test I: NornicDB is the only source of truth."""

    async def test_written_state_is_visible_through_a_second_connection(
        self, stack, nornic_settings
    ) -> None:
        core, person, _, _ = stack
        await core.save_preference(
            HERMES,
            PreferenceDraft(
                key="scheduling.earliest", value="after 10", subject_id=person.id
            ),
        )

        # A separate driver connection reads the same row. Nothing is cached in
        # a second store or held only in process memory.
        other = NornicClient(nornic_settings)
        await other.connect()
        try:
            rows = await other.read(
                "MATCH (p:Preference) WHERE p.subject_id = $sid AND p.valid_to IS NULL "
                "RETURN p.value AS value",
                sid=person.id,
            )
        finally:
            await other.close()

        assert [r["value"] for r in rows] == ["after 10"]
