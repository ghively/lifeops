"""LifeOpsCore's document operations (BUILD_SPEC sections 36, 64, 96):
create_document (Console/HTTP, WRITE_WORLD), get_document and
search_documents (any client with READ_WORLD).
"""

from __future__ import annotations

import pytest

from lifeops.clock import FrozenClock
from lifeops.core import LifeOpsCore
from lifeops.domain.documents import DocumentDraft
from lifeops.domain.people import Person
from lifeops.errors import CapabilityDeniedError, NotFoundError
from lifeops.policy.capabilities import CONSOLE, HERMES, INTERACTIVE_CLIENT
from lifeops.repositories.fakes import (
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
    FakeWorldRepository,
)

PRIMARY = "person_document_user"
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


class TestCreateDocument:
    async def test_console_can_create_a_document(self, core: LifeOpsCore) -> None:
        document = await core.create_document(
            CONSOLE,
            DocumentDraft(
                title="ABC Electric quote",
                source="email",
                source_ref="msg-123",
                summary="Quote for panel upgrade: $2,400",
            ),
        )
        assert document.title == "ABC Electric quote"
        assert document.id.startswith("document_")

        fetched = await core.get_document(CONSOLE, document_id=document.id)
        assert fetched.source_ref == "msg-123"

    async def test_hermes_can_also_create_a_document(self, core: LifeOpsCore) -> None:
        document = await core.create_document(
            HERMES,
            DocumentDraft(title="Trash pickup notice", source="manual"),
        )
        assert document.created_by_client == "hermes-personal"

    async def test_an_interactive_client_cannot_create_a_document(
        self, core: LifeOpsCore
    ) -> None:
        with pytest.raises(CapabilityDeniedError):
            await core.create_document(
                INTERACTIVE_CLIENT, DocumentDraft(title="Nope", source="manual")
            )


class TestGetDocument:
    async def test_unknown_id_is_not_found(self, core: LifeOpsCore) -> None:
        with pytest.raises(NotFoundError):
            await core.get_document(HERMES, document_id="document_nope")


class TestSearchDocuments:
    @pytest.fixture(autouse=True)
    async def _seed(self, core: LifeOpsCore) -> None:
        await core.create_document(
            CONSOLE,
            DocumentDraft(
                title="Water heater installation receipt",
                source="email",
                source_ref="msg-1",
                summary="Installed by ABC Plumbing, $1,800.",
            ),
        )
        await core.create_document(
            CONSOLE,
            DocumentDraft(title="Trash pickup notice", source="manual", summary="Holiday schedule"),
        )

    async def test_empty_query_returns_everything(self, core: LifeOpsCore) -> None:
        results = await core.search_documents(HERMES)
        assert {d.title for d in results} == {
            "Water heater installation receipt",
            "Trash pickup notice",
        }

    async def test_matches_on_title(self, core: LifeOpsCore) -> None:
        results = await core.search_documents(HERMES, query="trash")
        assert [d.title for d in results] == ["Trash pickup notice"]

    async def test_matches_on_summary_not_just_title(self, core: LifeOpsCore) -> None:
        results = await core.search_documents(HERMES, query="abc plumbing")
        assert [d.title for d in results] == ["Water heater installation receipt"]

    async def test_no_match_is_an_empty_list(self, core: LifeOpsCore) -> None:
        assert await core.search_documents(HERMES, query="nonexistent") == []
