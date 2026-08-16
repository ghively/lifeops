"""Repository search behaviour against a live NornicDB.

The fakes prove the substring semantics; only these prove the Cypher is right.
Skipped automatically when NornicDB is not reachable.
"""

from __future__ import annotations

import pytest

from lifeops.clock import FrozenClock
from lifeops.core import LifeOpsCore
from lifeops.domain.people import Person
from lifeops.domain.preferences import PreferenceDraft
from lifeops.domain.tasks import TaskDraft
from lifeops.policy import CONSOLE
from lifeops.repositories.nornic.client import NornicClient
from lifeops.repositories.nornic.people import NornicPersonRepository
from lifeops.repositories.nornic.preferences import NornicPreferenceRepository
from lifeops.repositories.nornic.tasks import NornicTaskRepository

pytestmark = [pytest.mark.integration, pytest.mark.persistence]


@pytest.fixture
async def stack(nornic_client: NornicClient, test_label: str):
    people = NornicPersonRepository(nornic_client)
    preferences = NornicPreferenceRepository(nornic_client)
    tasks = NornicTaskRepository(nornic_client)
    clock = FrozenClock()

    person = Person(
        id=f"person_{test_label}",
        display_name=f"Searchable {test_label}",
        is_primary=False,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    await people.upsert(person)

    core = LifeOpsCore(
        people=people, preferences=preferences, tasks=tasks, clock=clock
    )
    try:
        yield core, person, test_label
    finally:
        # Everything created here hangs off this person; clean up by
        # owner/subject so a shared database keeps no residue.
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


class TestNornicSearch:
    async def test_task_search_matches_title_case_insensitively(self, stack) -> None:
        core, person, label = stack
        await core.create_task(
            CONSOLE,
            TaskDraft(title=f"Repair outlet {label}", owner_entity_id=person.id),
        )
        results = await core.search(CONSOLE, query=f"OUTLET {label}")
        assert [t.title for t in results.tasks] == [f"Repair outlet {label}"]

    async def test_preference_search_matches_current_values_only(self, stack) -> None:
        core, person, label = stack
        await core.save_preference(
            CONSOLE,
            PreferenceDraft(key=f"search.{label}", value="dark", subject_id=person.id),
        )
        await core.save_preference(
            CONSOLE,
            PreferenceDraft(key=f"search.{label}", value="light", subject_id=person.id),
        )
        superseded = await core.search(CONSOLE, query="dark")
        assert superseded.preferences == []
        current = await core.search(CONSOLE, query=label)
        assert [p.value for p in current.preferences] == ["light"]

    async def test_person_search_matches_display_name(self, stack) -> None:
        core, person, label = stack
        results = await core.search(CONSOLE, query=f"searchable {label}")
        assert person.id in {p.id for p in results.people}
