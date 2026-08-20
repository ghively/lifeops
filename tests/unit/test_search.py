"""Universal search (BUILD_SPEC section 19): all twelve categories — people,
preferences, tasks, providers, assets, appointments, events, memory,
documents, knowledge, bills, actions, and historical facts.
"""

from __future__ import annotations

import pytest

from lifeops.clock import FrozenClock
from lifeops.core import LifeOpsCore
from lifeops.domain.actions import ActionDraft, ActionType
from lifeops.domain.bills import BillDraft, PayeeDraft
from lifeops.domain.calendar import (
    Appointment,
    AppointmentStatus,
    CalendarEvent,
    calendar_event_to_entity,
)
from lifeops.domain.documents import DocumentDraft
from lifeops.domain.knowledge import KnowledgeDraft
from lifeops.domain.memory import MemoryDraft
from lifeops.domain.people import Person, PersonDraft
from lifeops.domain.preferences import PreferenceDraft
from lifeops.domain.tasks import TaskDraft
from lifeops.domain.world import EntityDraft, WorldEntityType
from lifeops.errors import CapabilityDeniedError
from lifeops.policy import Capability
from lifeops.policy.capabilities import CONSOLE, HERMES, ClientIdentity, ClientRole
from lifeops.repositories.fakes import (
    FakeActionRepository,
    FakeApprovalRepository,
    FakeAuditRepository,
    FakeBillRepository,
    FakeMemoryRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
    FakeWorldRepository,
)

TS = "2026-01-01T00:00:00Z"

NO_ACCESS = ClientIdentity(
    client_id="no-access",
    role=ClientRole.ENGINEERING_ASSISTANT,
    display_name="No Access",
    capabilities=frozenset(),
)


async def _seed(core: LifeOpsCore) -> None:
    await core.create_person(CONSOLE, PersonDraft(display_name="Alex Rivera"))
    await core.save_preference(
        CONSOLE, PreferenceDraft(key="coffee.roast", value="light roast")
    )
    await core.create_task(
        CONSOLE, TaskDraft(title="Repair living room outlet", description="call Alex")
    )


class TestSearch:
    async def test_matches_across_all_three_domains(self, core: LifeOpsCore) -> None:
        await _seed(core)

        by_name = await core.search(CONSOLE, query="tori")
        assert [p.display_name for p in by_name.people] == ["Alex Rivera"]
        assert [t.title for t in by_name.tasks] == ["Repair living room outlet"]
        assert by_name.preferences == []

        by_key = await core.search(CONSOLE, query="ROAST")
        assert [p.key for p in by_key.preferences] == ["coffee.roast"]

    async def test_substring_and_case_insensitive(self, core: LifeOpsCore) -> None:
        await _seed(core)
        results = await core.search(CONSOLE, query="OUTLET")
        assert [t.title for t in results.tasks] == ["Repair living room outlet"]

    async def test_superseded_preferences_do_not_match(self, core: LifeOpsCore) -> None:
        await core.save_preference(CONSOLE, PreferenceDraft(key="coffee.roast", value="dark"))
        await core.save_preference(CONSOLE, PreferenceDraft(key="coffee.roast", value="light"))

        results = await core.search(CONSOLE, query="dark")
        assert results.preferences == []

    async def test_no_matches_returns_empty_groups(self, core: LifeOpsCore) -> None:
        results = await core.search(CONSOLE, query="zzzz-nothing")
        assert results.people == [] and results.preferences == [] and results.tasks == []

    async def test_limit_bounds_each_group(self, core: LifeOpsCore) -> None:
        for index in range(8):
            await core.create_task(CONSOLE, TaskDraft(title=f"chore {index}"))
        results = await core.search(CONSOLE, query="chore", limit=3)
        assert len(results.tasks) == 3

    async def test_requires_read_world(self, core: LifeOpsCore) -> None:
        with pytest.raises(CapabilityDeniedError):
            await core.search(NO_ACCESS, query="anything")

    async def test_people_search_matches_aliases(self, core: LifeOpsCore) -> None:
        await core.create_person(
            CONSOLE, PersonDraft(display_name="Alex Rivera", aliases=["AR"])
        )
        results = await core.search(CONSOLE, query="tj")
        assert [p.display_name for p in results.people] == ["Alex Rivera"]


@pytest.fixture
async def full_core(clock: FrozenClock) -> LifeOpsCore:
    """A LifeOpsCore with world, memory, bills, and audit wired, for the
    categories the two 2026-08-18 audit passes found universal search
    missing."""
    people = FakePersonRepository()
    await people.upsert(
        Person(
            id="person_full_search_user", display_name="Test User", is_primary=True,
            created_at=TS, updated_at=TS,
        )
    )
    return LifeOpsCore(
        people=people,
        preferences=FakePreferenceRepository(),
        tasks=FakeTaskRepository(),
        world=FakeWorldRepository(),
        memory=FakeMemoryRepository(),
        bills=FakeBillRepository(),
        actions=FakeActionRepository(),
        approvals=FakeApprovalRepository(),
        audit=FakeAuditRepository(),
        clock=clock,
    )


class TestWidenedCategories:
    """The seven categories the 2026-08-18 audit found missing: providers,
    assets, appointments, memory, documents, knowledge, bills."""

    async def test_matches_a_provider_by_name(self, full_core: LifeOpsCore) -> None:
        await full_core.create_entity(
            CONSOLE,
            EntityDraft(entity_type=WorldEntityType.PROVIDER, display_name="ABC Electric"),
        )
        results = await full_core.search(CONSOLE, query="electric")
        assert [p.display_name for p in results.providers] == ["ABC Electric"]

    async def test_matches_an_asset_by_name(self, full_core: LifeOpsCore) -> None:
        await full_core.create_entity(
            CONSOLE,
            EntityDraft(entity_type=WorldEntityType.ASSET, display_name="Land Rover"),
        )
        results = await full_core.search(CONSOLE, query="rover")
        assert [a.display_name for a in results.assets] == ["Land Rover"]

    async def test_matches_an_appointment_by_subject(self, full_core: LifeOpsCore) -> None:
        from lifeops.domain.calendar import appointment_to_entity

        appointment = Appointment(
            id=Appointment.make_id(),
            subject="Electrician visit",
            status=AppointmentStatus.HELD,
            start_at=TS,
            end_at=TS,
            created_at=TS,
            updated_at=TS,
        )
        await full_core._world_repo.create(appointment_to_entity(appointment))
        results = await full_core.search(CONSOLE, query="electrician")
        assert [a.subject for a in results.appointments] == ["Electrician visit"]

    async def test_matches_memory_by_content(self, full_core: LifeOpsCore) -> None:
        await full_core.remember(HERMES, MemoryDraft(content="drives a blue car"))
        results = await full_core.search(HERMES, query="blue car")
        assert [m.content for m in results.memories] == ["drives a blue car"]

    async def test_memory_is_empty_without_read_memory(self, full_core: LifeOpsCore) -> None:
        await full_core.remember(HERMES, MemoryDraft(content="drives a blue car"))
        # READ_WORLD alone (the base gate for search()) must not be a side
        # door to memory — the same per-category gate preferences/tasks use.
        world_only_client = ClientIdentity(
            client_id="world-only",
            role=ClientRole.INTERACTIVE_ASSISTANT,
            display_name="World only",
            capabilities=frozenset({Capability.READ_WORLD}),
        )
        results = await full_core.search(world_only_client, query="blue car")
        assert results.memories == []

    async def test_matches_a_document_by_title(self, full_core: LifeOpsCore) -> None:
        await full_core.create_document(
            CONSOLE, DocumentDraft(title="ABC Electric quote", source="email")
        )
        results = await full_core.search(CONSOLE, query="quote")
        assert [d.title for d in results.documents] == ["ABC Electric quote"]

    async def test_matches_knowledge_by_content_not_just_title(
        self, full_core: LifeOpsCore
    ) -> None:
        await full_core.record_knowledge(
            CONSOLE,
            KnowledgeDraft(title="Water heater", content="10-year tank warranty"),
        )
        results = await full_core.search(CONSOLE, query="tank warranty")
        assert [k.title for k in results.knowledge] == ["Water heater"]

    async def test_matches_a_bill_by_description(self, full_core: LifeOpsCore) -> None:
        await full_core.record_payee(CONSOLE, PayeeDraft(display_name="ABC Electric"))
        await full_core.record_bill(
            CONSOLE,
            BillDraft(
                payee_id="payee_abc_electric", description="March invoice", amount="89.10"
            ),
        )
        results = await full_core.search(CONSOLE, query="march")
        assert [b.description for b in results.bills] == ["March invoice"]

    async def test_widened_categories_are_empty_without_world_or_bills(
        self, core: LifeOpsCore
    ) -> None:
        """The base `core` fixture (people/preferences/tasks only) must not
        crash when world/memory/bills aren't configured — it degrades to
        empty groups, the same as a fresh Phase-0-only deployment would."""
        results = await core.search(CONSOLE, query="anything")
        assert results.providers == []
        assert results.assets == []
        assert results.appointments == []
        assert results.events == []
        assert results.memories == []
        assert results.documents == []
        assert results.knowledge == []
        assert results.bills == []
        assert results.actions == []
        assert results.historical_facts == []


class TestLastTwoCategories:
    """The two categories the second 2026-08-18 audit pass found still
    missing: events (a real Event projection already existed —
    domain/calendar.py's calendar_event_to_entity — search just never
    reached for it) and actions/historical facts (both map to a concrete,
    already-persisted object: Action and AuditRecord)."""

    async def test_matches_an_event_by_title(self, full_core: LifeOpsCore) -> None:
        event = CalendarEvent(
            id="event_dentist",
            external_event_id="ext_1",
            title="Dentist follow-up",
            start_at=TS,
            end_at=TS,
        )
        await full_core._world_repo.create(calendar_event_to_entity(event, now=TS))
        results = await full_core.search(CONSOLE, query="dentist")
        assert [e.display_name for e in results.events] == ["Dentist follow-up"]

    async def test_matches_an_action_by_type(self, full_core: LifeOpsCore) -> None:
        await full_core.prepare_action(
            CONSOLE, ActionDraft(type=ActionType.SEND_EMAIL, payload={})
        )
        results = await full_core.search(CONSOLE, query="email")
        assert [str(a.type) for a in results.actions] == ["send_email"]

    async def test_actions_are_empty_without_read_tasks(
        self, full_core: LifeOpsCore
    ) -> None:
        await full_core.prepare_action(
            CONSOLE, ActionDraft(type=ActionType.SEND_EMAIL, payload={})
        )
        world_only_client = ClientIdentity(
            client_id="world-only-actions",
            role=ClientRole.INTERACTIVE_ASSISTANT,
            display_name="World only",
            capabilities=frozenset({Capability.READ_WORLD}),
        )
        results = await full_core.search(world_only_client, query="email")
        assert results.actions == []

    async def test_matches_a_historical_fact_by_intent(
        self, full_core: LifeOpsCore
    ) -> None:
        await full_core.audit(
            CONSOLE, result="ok", intent="schedule_electrician",
            target="provider_abc_electric",
        )
        results = await full_core.search(CONSOLE, query="electrician")
        assert [r.intent for r in results.historical_facts] == ["schedule_electrician"]

    async def test_historical_facts_are_empty_without_read_tasks(
        self, full_core: LifeOpsCore
    ) -> None:
        await full_core.audit(CONSOLE, result="ok", intent="schedule_electrician")
        world_only_client = ClientIdentity(
            client_id="world-only-facts",
            role=ClientRole.INTERACTIVE_ASSISTANT,
            display_name="World only",
            capabilities=frozenset({Capability.READ_WORLD}),
        )
        results = await full_core.search(world_only_client, query="electrician")
        assert results.historical_facts == []
