"""Memory repository behaviour against a live NornicDB.

The fakes prove the domain rules; only these prove the Cypher is right, that
the SUPERSEDES/REMEMBERS edges exist for the World graph to traverse, that the
fulltext (BM25) index actually drives recall ranking, and that the temporal
invariants survive a real transaction.

Skipped automatically when NornicDB is not reachable.
"""

from __future__ import annotations

import pytest

from lifeops.clock import FrozenClock
from lifeops.core import LifeOpsCore
from lifeops.domain.memory import MemoryDraft, MemoryType
from lifeops.domain.people import Person
from lifeops.domain.preferences import PreferenceSource
from lifeops.errors import ValidationError
from lifeops.policy import HERMES
from lifeops.repositories.nornic.client import NornicClient
from lifeops.repositories.nornic.memory import (
    _FULLTEXT_INDEX,
    NornicMemoryRepository,
)
from lifeops.repositories.nornic.people import NornicPersonRepository
from lifeops.repositories.nornic.preferences import NornicPreferenceRepository
from lifeops.repositories.nornic.tasks import NornicTaskRepository

pytestmark = [pytest.mark.integration, pytest.mark.persistence]


@pytest.fixture
async def stack(nornic_client: NornicClient, test_label: str):
    """Repositories plus an isolated subject person for one test."""
    people = NornicPersonRepository(nornic_client)
    memory = NornicMemoryRepository(nornic_client)
    clock = FrozenClock()

    person = Person(
        id=f"person_{test_label}",
        display_name=f"Memory Subject {test_label}",
        is_primary=False,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    await people.upsert(person)

    # ensure_schema (run by the nornic_client fixture) creates the index;
    # wait for it so the BM25 assertions below are deterministic.
    await nornic_client.write(f"CALL db.awaitIndex('{_FULLTEXT_INDEX}')")

    core = LifeOpsCore(
        people=people,
        preferences=NornicPreferenceRepository(nornic_client),
        tasks=NornicTaskRepository(nornic_client),
        memory=memory,
        clock=clock,
    )
    try:
        yield core, person, clock, nornic_client
    finally:
        # Leave no residue in a shared database: everything this test created
        # hangs off its own Person.
        await nornic_client.write(
            "MATCH (m:Memory) WHERE m.subject_id = $id DETACH DELETE m",
            id=person.id,
        )
        await nornic_client.write(
            "MATCH (p:Person {id: $id}) DETACH DELETE p", id=person.id
        )


class TestRememberAndRecall:
    async def test_round_trip(self, stack) -> None:
        core, person, _, _ = stack
        saved = await core.remember(
            HERMES,
            MemoryDraft(
                content="The user is allergic to penicillin",
                subject_id=person.id,
                type=MemoryType.SEMANTIC,
                source_type=PreferenceSource.USER_EXPLICIT,
                importance=0.9,
                entity_ids=[person.id],
            ),
        )
        fetched = await core.get_memory(HERMES, memory_id=saved.id)
        assert fetched.content == "The user is allergic to penicillin"
        assert fetched.type is MemoryType.SEMANTIC
        assert fetched.entity_ids == [person.id]
        assert fetched.is_current

    async def test_remembers_edge_connects_person_to_memory(self, stack) -> None:
        core, person, _, client = stack
        saved = await core.remember(
            HERMES,
            MemoryDraft(content="likes strong coffee", subject_id=person.id),
        )
        rows = await client.read(
            "MATCH (:Person {id: $pid})-[:REMEMBERS]->(m:Memory {id: $mid}) "
            "RETURN m.id AS id",
            pid=person.id,
            mid=saved.id,
        )
        assert len(rows) == 1

    async def test_fulltext_index_drives_recall_ranking(self, stack) -> None:
        """BM25 must outrank importance ordering.

        The shorter, lexically tighter document scores higher in BM25 even
        though its importance is lower — the substring fallback would order by
        importance and return the other record first, so this fails loudly if
        the fulltext path is not the one serving recall.
        """
        core, person, _, _ = stack
        wordy = await core.remember(
            HERMES,
            MemoryDraft(
                content=(
                    "The user mentioned, at some length and with quite a lot of "
                    "surrounding detail, an upcoming zeppelin exhibition downtown"
                ),
                subject_id=person.id,
                importance=0.95,
            ),
        )
        tight = await core.remember(
            HERMES,
            MemoryDraft(
                content="zeppelin exhibition Saturday",
                subject_id=person.id,
                importance=0.1,
            ),
        )
        recalled = await core.recall(HERMES, query="zeppelin", subject_id=person.id)
        assert {m.id for m in recalled} == {wordy.id, tight.id}
        assert recalled[0].id == tight.id, "BM25 should rank the tighter document first"

    async def test_recall_filters_by_subject_and_type(self, stack) -> None:
        core, person, _, _ = stack
        await core.remember(
            HERMES,
            MemoryDraft(
                content="train commute takes forty minutes",
                subject_id=person.id,
                type=MemoryType.SEMANTIC,
            ),
        )
        episode = await core.remember(
            HERMES,
            MemoryDraft(
                content="missed the train on Monday",
                subject_id=person.id,
                type=MemoryType.EPISODIC,
            ),
        )
        found = await core.recall(
            HERMES,
            query="train",
            subject_id=person.id,
            memory_types=[MemoryType.EPISODIC],
        )
        assert [m.id for m in found] == [episode.id]

    async def test_recall_falls_back_to_substring_when_the_index_is_missing(
        self, stack, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A backend without the fulltext index must degrade, not break.

        Points the repository at a nonexistent index so the real driver raises
        the real error; the documented fallback is an all-terms substring
        match ordered by importance.
        """
        core, person, _, client = stack
        remembered = await core.remember(
            HERMES,
            MemoryDraft(
                content="collects vintage telescopes and star charts",
                subject_id=person.id,
            ),
        )

        monkeypatch.setattr(
            "lifeops.repositories.nornic.memory._FULLTEXT_INDEX",
            "lifeops_index_that_does_not_exist",
        )
        repo = NornicMemoryRepository(client)
        found = await repo.search(
            "vintage telescopes", subject_id=person.id, limit=5
        )
        assert [m.id for m in found] == [remembered.id]

    async def test_recall_uses_unique_terms_per_subject(self, stack) -> None:
        # Memories of *other* subjects must not leak into this subject's recall.
        core, person, _, _ = stack
        mine = await core.remember(
            HERMES,
            MemoryDraft(content="collects vintage telescopes", subject_id=person.id),
        )
        found = await core.recall(HERMES, query="telescopes", subject_id=person.id)
        assert [m.id for m in found] == [mine.id]

    async def test_restating_is_a_no_op(self, stack) -> None:
        core, person, clock, client = stack
        first = await core.remember(
            HERMES, MemoryDraft(content="drinks oat milk", subject_id=person.id)
        )
        clock.advance(60)
        second = await core.remember(
            HERMES, MemoryDraft(content="drinks oat milk", subject_id=person.id)
        )
        assert second.id == first.id
        rows = await client.read(
            "MATCH (m:Memory) WHERE m.subject_id = $id RETURN count(m) AS n",
            id=person.id,
        )
        assert rows[0]["n"] == 1

    async def test_secret_looking_content_never_reaches_the_database(
        self, stack
    ) -> None:
        core, person, _, client = stack
        with pytest.raises(ValidationError):
            await core.remember(
                HERMES,
                MemoryDraft(content="wifi password: hunter2", subject_id=person.id),
            )
        rows = await client.read(
            "MATCH (m:Memory) WHERE m.subject_id = $id RETURN count(m) AS n",
            id=person.id,
        )
        assert rows[0]["n"] == 0


class TestTemporalSupersession:
    async def test_correction_closes_old_window_and_links_supersedes(
        self, stack
    ) -> None:
        core, person, clock, client = stack
        original = await core.remember(
            HERMES,
            MemoryDraft(content="dentist is Dr. Patel", subject_id=person.id),
        )
        clock.advance(3600)
        corrected = await core.correct_memory(
            HERMES, memory_id=original.id, new_content="dentist is Dr. Nguyen"
        )

        rows = await client.read(
            "MATCH (new:Memory {id: $new})-[:SUPERSEDES]->(old:Memory) "
            "RETURN old.id AS old_id, old.valid_to AS valid_to",
            new=corrected.id,
        )
        assert [r["old_id"] for r in rows] == [original.id]
        assert rows[0]["valid_to"] is not None

        current = await core.recall(HERMES, query="dentist", subject_id=person.id)
        assert [m.id for m in current] == [corrected.id]

    async def test_history_returns_the_chain_newest_first(self, stack) -> None:
        core, person, clock, _ = stack
        first = await core.remember(
            HERMES, MemoryDraft(content="lives on Oak Street", subject_id=person.id)
        )
        clock.advance(60)
        second = await core.correct_memory(
            HERMES, memory_id=first.id, new_content="lives on Maple Street"
        )
        clock.advance(60)
        third = await core.correct_memory(
            HERMES, memory_id=second.id, new_content="lives on Birch Street"
        )

        history = await core.memory_history(HERMES, memory_id=first.id)
        assert [m.id for m in history] == [third.id, second.id, first.id]
        assert [m.content for m in history] == [
            "lives on Birch Street",
            "lives on Maple Street",
            "lives on Oak Street",
        ]

    async def test_invalidate_persists_window_and_reason(self, stack) -> None:
        core, person, _, client = stack
        saved = await core.remember(
            HERMES, MemoryDraft(content="has a dog named Rex", subject_id=person.id)
        )
        closed = await core.invalidate_memory(
            HERMES, memory_id=saved.id, reason="user asked to forget"
        )
        assert not closed.is_current

        rows = await client.read(
            "MATCH (m:Memory {id: $id}) "
            "RETURN m.valid_to AS valid_to, m.invalidation_reason AS reason",
            id=saved.id,
        )
        assert rows[0]["valid_to"] is not None
        assert rows[0]["reason"] == "user asked to forget"

        assert await core.recall(HERMES, query="Rex", subject_id=person.id) == []
