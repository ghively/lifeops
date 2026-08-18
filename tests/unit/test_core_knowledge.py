"""LifeOpsCore's knowledge operations (BUILD_SPEC sections 18, 36, 50),
exercised against fakes — record_knowledge (Console/HTTP, WRITE_WORLD),
get_knowledge and search_knowledge (any client with READ_WORLD).
"""

from __future__ import annotations

import pytest

from lifeops.clock import FrozenClock
from lifeops.core import LifeOpsCore
from lifeops.domain.knowledge import KnowledgeDraft
from lifeops.domain.people import Person
from lifeops.errors import CapabilityDeniedError, NotFoundError
from lifeops.policy.capabilities import CONSOLE, HERMES, INTERACTIVE_CLIENT
from lifeops.repositories.fakes import (
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
    FakeWorldRepository,
)

PRIMARY = "person_knowledge_user"
TS = "2026-01-01T00:00:00Z"


@pytest.fixture
async def core(clock: FrozenClock) -> LifeOpsCore:
    people = FakePersonRepository()
    await people.upsert(
        Person(id=PRIMARY, display_name="Test User", is_primary=True, created_at=TS, updated_at=TS)
    )
    return LifeOpsCore(
        people=people,
        preferences=FakePreferenceRepository(),
        tasks=FakeTaskRepository(),
        world=FakeWorldRepository(),
        clock=clock,
    )


class TestRecordKnowledge:
    async def test_console_can_record_knowledge(self, core: LifeOpsCore) -> None:
        knowledge = await core.record_knowledge(
            CONSOLE,
            KnowledgeDraft(
                title="Furnace filter size", category="manual", content="16x25x1"
            ),
        )
        assert knowledge.title == "Furnace filter size"
        assert knowledge.id.startswith("knowledge_")

        fetched = await core.get_knowledge(CONSOLE, knowledge_id=knowledge.id)
        assert fetched.content == "16x25x1"

    async def test_hermes_can_also_record_knowledge(self, core: LifeOpsCore) -> None:
        # Hermes holds WRITE_WORLD (CLAUDE.md), same as record_document —
        # the MCP surface just never spends it here (no MCP tool calls this).
        knowledge = await core.record_knowledge(
            HERMES, KnowledgeDraft(title="Trash day", content="Tuesdays")
        )
        assert knowledge.created_by_client == "hermes-personal"

    async def test_an_interactive_client_cannot_record_knowledge(
        self, core: LifeOpsCore
    ) -> None:
        with pytest.raises(CapabilityDeniedError):
            await core.record_knowledge(
                INTERACTIVE_CLIENT, KnowledgeDraft(title="Nope")
            )


class TestGetKnowledge:
    async def test_unknown_id_is_not_found(self, core: LifeOpsCore) -> None:
        with pytest.raises(NotFoundError):
            await core.get_knowledge(HERMES, knowledge_id="knowledge_nope")


class TestSearchKnowledge:
    @pytest.fixture(autouse=True)
    async def _seed(self, core: LifeOpsCore) -> None:
        await core.record_knowledge(
            CONSOLE,
            KnowledgeDraft(
                title="Water heater warranty",
                category="warranty",
                content="10-year tank warranty, registered 2024.",
            ),
        )
        await core.record_knowledge(
            CONSOLE,
            KnowledgeDraft(title="Trash day", category="household", content="Tuesdays and Fridays"),
        )

    async def test_empty_query_returns_everything(self, core: LifeOpsCore) -> None:
        results = await core.search_knowledge(HERMES)
        assert {k.title for k in results} == {"Water heater warranty", "Trash day"}

    async def test_matches_on_title(self, core: LifeOpsCore) -> None:
        results = await core.search_knowledge(HERMES, query="trash")
        assert [k.title for k in results] == ["Trash day"]

    async def test_matches_on_content_not_just_title(self, core: LifeOpsCore) -> None:
        # This is the whole reason search_knowledge doesn't reuse world_graph's
        # text filter — that only matches display_name, never facts.
        results = await core.search_knowledge(HERMES, query="tank warranty")
        assert [k.title for k in results] == ["Water heater warranty"]

    async def test_matches_on_category(self, core: LifeOpsCore) -> None:
        results = await core.search_knowledge(HERMES, query="household")
        assert [k.title for k in results] == ["Trash day"]

    async def test_no_match_is_an_empty_list(self, core: LifeOpsCore) -> None:
        assert await core.search_knowledge(HERMES, query="nonexistent") == []
