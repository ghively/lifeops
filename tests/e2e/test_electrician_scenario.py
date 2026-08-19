"""Electrician end-to-end acceptance scenario (BUILD_SPEC section 101).

Input: "Get an electrician next week for the outlet behind the TV. Nothing
before ten."

Section 101 lists sixteen steps. This suite covers what phases 0-8 have
built; the two it cannot yet exercise are called out explicitly rather than
faked:

  1.  identify relevant asset               -- covered (``TestElectricianScenario``)
  2.  retrieve scheduling preference         -- covered
  3.  look for provider history              -- covered
  4.  inspect calendar                       -- covered
  5.  find/contact appropriate provider      -- covered
  6.  collect availability                   -- covered
  7.  collect diagnostic fee                 -- covered
  8.  create waiting item when necessary     -- covered (``TestWaitingWhenNecessary``)
  9.  never authorize repairs                -- covered (asserted on every call payload)
  10. prepare booking                        -- covered
  11. request approval if required           -- covered
  12. book exactly once                      -- covered (a second execute is refused)
  13. verify booking                         -- covered
  14. record provider/action history         -- covered (via the audit log)
  15. create calendar event                  -- covered (Phase 7's booking execution
                                                 creates the event; this asserts it exists)
  16. mark task completed only after verification -- covered

Nothing here calls a real telephone or a real calendar server (BUILD_SPEC
section 88: no telephony SDK dependency, CI must never need a phone line).
``FakeTelephonyProvider`` and ``FakeCalendarProvider`` are injected exactly as
production would inject a real backend, through
``TelephonyProviderService``/``CalendarProviderService``'s ``factories``
argument — the only wiring difference from a real deployment.

Payment (BUILD_SPEC section 99, phase 10) does not appear anywhere in this
scenario: the fee collected in step 7 is recorded as a fact, never paid, and
no payment action appears in the audit trail, and the client that runs the
scenario (Hermes) is asserted not to hold ``Capability.FINANCIAL_PAYMENT`` —
which Phase 10 granted to the Console alone.

This runs against a real NornicDB (skipped when unreachable) rather than the
subprocess MCP harness ``test_phase4_durable_work.py`` uses: the MCP
subprocess launches a production ``Container``, whose ``TelephonyProviderService``
has no real factory registered by design (section 88) and so cannot place
even a fake call. Driving the same ``LifeOpsCore`` operations directly, over
real Nornic repositories, proves the same persistence guarantee — work
survives outside any one Python process — while keeping telephony and
calendar on fakes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lifeops.calendar.fake import FakeCalendarProvider
from lifeops.calendar.service import CalendarProviderService
from lifeops.clock import FrozenClock
from lifeops.config.service import ConfigurationService
from lifeops.core import LifeOpsCore
from lifeops.domain.actions import ActionStatus, ActionType
from lifeops.domain.approvals import ApprovalStatus
from lifeops.domain.calendar import AppointmentHoldDraft, AppointmentStatus
from lifeops.domain.people import PersonDraft
from lifeops.domain.preferences import PreferenceDraft
from lifeops.domain.service_request import ServiceRequestDraft, ServiceRequestStatus
from lifeops.domain.tasks import TaskDraft, TaskState, TaskUpdate
from lifeops.domain.world import EntityDraft, WorldEntityType, WorldRelationship
from lifeops.errors import ConflictError
from lifeops.policy.capabilities import CONSOLE, HERMES, Capability, all_clients
from lifeops.repositories.nornic.actions import NornicActionRepository
from lifeops.repositories.nornic.approvals import NornicApprovalRepository
from lifeops.repositories.nornic.audit import NornicAuditRepository
from lifeops.repositories.nornic.client import NornicClient
from lifeops.repositories.nornic.people import NornicPersonRepository
from lifeops.repositories.nornic.preferences import NornicPreferenceRepository
from lifeops.repositories.nornic.service_requests import (
    NornicServiceRequestRepository,
)
from lifeops.repositories.nornic.tasks import NornicTaskRepository
from lifeops.repositories.nornic.waiting import NornicWaitingRepository
from lifeops.repositories.nornic.world import NornicWorldRepository
from lifeops.secrets.local_encrypted import InMemorySecretStore
from lifeops.telephony.fake import FakeTelephonyProvider
from lifeops.telephony.service import TelephonyProviderService

pytestmark = [pytest.mark.integration, pytest.mark.persistence]


@pytest.fixture
async def scenario(nornic_client: NornicClient, test_label: str, tmp_path: Path):
    """A real ``LifeOpsCore`` over NornicDB, with fake calendar and telephony
    providers standing in for the outside world (section 88)."""
    people = NornicPersonRepository(nornic_client)
    preferences = NornicPreferenceRepository(nornic_client)
    tasks = NornicTaskRepository(nornic_client)
    world = NornicWorldRepository(nornic_client)
    service_requests = NornicServiceRequestRepository(nornic_client)
    waiting = NornicWaitingRepository(nornic_client)
    actions = NornicActionRepository(nornic_client)
    approvals = NornicApprovalRepository(nornic_client)
    audit = NornicAuditRepository(nornic_client)

    config = ConfigurationService(
        config_dir=tmp_path / "config", secret_store=InMemorySecretStore(), clock=FrozenClock()
    )
    fake_calendar = FakeCalendarProvider()
    config.update_provider(
            "calendar",
            # password is a required secret now (an empty credential cannot
            # log in); the fake never reads it, but the configured/enabled
            # gate is the same one production applies.
            {"enabled": True, "backend": "caldav", "password": "test-password"},
        )
    calendar = CalendarProviderService(
        config=config,
        secret_store=InMemorySecretStore(),
        factories={"caldav": lambda settings, secrets: fake_calendar},
    )
    fake_telephony = FakeTelephonyProvider(
        availability=[f"Thursday {test_label} 1:00-3:00 PM"], diagnostic_fee="$89"
    )
    config.update_provider(
        "telephony",
        {
            "enabled": True,
            "account_sid": "AC" + "0" * 32,
            "auth_token": "test-auth-token",
            "from_number": "+15551234567",
        },
    )
    telephony = TelephonyProviderService(
        config=config,
        secret_store=InMemorySecretStore(),
        factories={"telephony": lambda settings, secrets: fake_telephony},
    )

    core = LifeOpsCore(
        people=people,
        preferences=preferences,
        tasks=tasks,
        world=world,
        service_requests=service_requests,
        waiting=waiting,
        actions=actions,
        approvals=approvals,
        audit=audit,
        calendar=calendar,
        telephony=telephony,
        clock=FrozenClock(),
    )

    created_ids: list[str] = []
    try:
        yield core, fake_calendar, fake_telephony, created_ids
    finally:
        for entity_id in created_ids:
            await nornic_client.write(
                "MATCH (n {id: $id}) DETACH DELETE n", id=entity_id
            )


class TestElectricianScenario:
    """Steps 1-7, 9-16 of section 101, in order."""

    async def test_the_full_scenario(self, scenario, test_label: str) -> None:
        core, fake_calendar, fake_telephony, created_ids = scenario

        # --- setup: the household this scenario belongs to -------------------
        primary = await core.create_person(
            HERMES, PersonDraft(display_name=f"Gene {test_label}", is_primary=True)
        )
        created_ids.append(primary.id)

        # Step 1: identify the relevant asset.
        asset = await core.create_entity(
            HERMES,
            EntityDraft(
                entity_type=WorldEntityType.ASSET,
                display_name=f"Living Room Outlet {test_label}",
                facts={"location": "behind the TV"},
            ),
        )
        created_ids.append(asset.id)

        task = await core.create_task(
            HERMES,
            TaskDraft(
                title="Get an electrician next week for the outlet behind the TV",
                related_entity_ids=[asset.id],
                verification_required=True,
            ),
        )
        created_ids.append(task.id)

        service_request = await core.create_service_request(
            HERMES,
            ServiceRequestDraft(
                subject="Living Room Outlet: nothing before ten",
                task_id=task.id,
                asset_entity_id=asset.id,
            ),
        )
        created_ids.append(service_request.id)
        assert service_request.status is ServiceRequestStatus.RESEARCHING

        # Step 2: retrieve the scheduling preference ("nothing before ten").
        await core.save_preference(
            HERMES,
            PreferenceDraft(
                key="scheduling.earliest_appointment_time",
                value="10:00 AM",
                subject_id=primary.id,
            ),
        )
        preferences = await core.get_preferences(HERMES, subject_id=primary.id)
        earliest = next(
            p for p in preferences if p.key == "scheduling.earliest_appointment_time"
        )
        assert earliest.value == "10:00 AM"

        # Step 3: look for provider history. None exists yet for this
        # household, so LifeOps must find one — this is the negative case;
        # a household that already uses a provider is what
        # ``test_mcp_world_tools.py``'s USES_PROVIDER graph proves separately.
        household = await core.create_entity(
            HERMES,
            EntityDraft(
                entity_type=WorldEntityType.HOUSEHOLD, display_name=f"Main House {test_label}"
            ),
        )
        created_ids.append(household.id)
        await core.link_entities(
            HERMES, source_id=primary.id, target_id=household.id,
            rel_type=str(WorldRelationship.MEMBER_OF),
        )
        neighborhood = await core.world_neighborhood(HERMES, entity_id=household.id, depth=1)
        prior_providers = [
            n for n in neighborhood.nodes if n.entity_type is WorldEntityType.PROVIDER
        ]
        assert prior_providers == []  # no provider history -> research is needed

        provider = await core.create_entity(
            HERMES,
            EntityDraft(
                entity_type=WorldEntityType.PROVIDER,
                display_name=f"ABC Electric {test_label}",
                facts={"phone": "555-0100"},
            ),
        )
        created_ids.append(provider.id)
        await core.link_entities(
            HERMES, source_id=household.id, target_id=provider.id,
            rel_type=str(WorldRelationship.USES_PROVIDER),
        )

        # Step 4: inspect the calendar before proposing anything.
        free_busy = await core.check_calendar_free_busy(
            HERMES, start_at="2026-09-01T00:00:00Z", end_at="2026-09-08T00:00:00Z"
        )
        assert free_busy.slots == []  # nothing on the calendar yet

        # Step 5-7: contact the provider, collect availability and the fee.
        # Section 97's hard rule and section 101 step 9 apply to every call —
        # asserted here, not assumed.
        call_action = await core.request_provider_call(
            HERMES,
            service_request_id=service_request.id,
            provider_entity_id=provider.id,
            objective="schedule_electrician",
            collect=["availability", "diagnostic_fee"],
        )
        created_ids.append(call_action.id)
        assert call_action.type is ActionType.PLACE_PHONE_CALL
        assert call_action.payload["authority"]["authorize_charge"] is False
        assert call_action.payload["authority"]["authorize_repairs"] is False
        # R2, policy-controlled: Hermes places this call on its own.
        assert call_action.status is ActionStatus.PREPARED

        executed_call = await core.execute_action(HERMES, action_id=call_action.id)
        assert executed_call.status is ActionStatus.EXECUTED
        assert len(fake_telephony.calls) == 1

        service_request = await core.get_service_request(
            HERMES, service_request_id=service_request.id
        )
        assert service_request.status is ServiceRequestStatus.QUOTE_COLLECTED
        assert service_request.availability
        assert service_request.diagnostic_fee == "$89"

        # Step 10: prepare booking. Nothing books yet.
        appointment = await core.create_appointment_hold(
            HERMES,
            AppointmentHoldDraft(
                subject="Electrician: Living Room Outlet",
                start_at="2026-09-04T13:00:00Z",  # after 10 AM, matches the preference
                end_at="2026-09-04T15:00:00Z",
                provider_entity_id=provider.id,
                task_id=task.id,
            ),
        )
        created_ids.append(appointment.id)
        assert appointment.status is AppointmentStatus.HELD

        booking_action = await core.request_service_booking(
            HERMES, service_request_id=service_request.id, appointment_id=appointment.id
        )
        created_ids.append(booking_action.id)
        assert booking_action.type is ActionType.BOOK_APPOINTMENT
        # R3: always requires approval (domain/actions.py) — step 11.
        assert booking_action.status is ActionStatus.NEEDS_APPROVAL

        service_request = await core.get_service_request(
            HERMES, service_request_id=service_request.id
        )
        assert service_request.status is ServiceRequestStatus.BOOKING_REQUESTED

        # Step 11: request approval if required — a human, not Hermes, decides.
        pending = await core.list_pending_approvals(CONSOLE)
        (approval,) = [a for a in pending if a.action_id == booking_action.id]
        assert approval.authorises_action == "Book appointment"
        assert "Authorize repair work" in approval.does_not_authorise
        assert "Authorize additional charges" in approval.does_not_authorise
        decided = await core.decide_approval(CONSOLE, approval_id=approval.id, approved=True)
        assert decided.status is ApprovalStatus.APPROVED

        # Step 12: book exactly once.
        booked = await core.execute_action(CONSOLE, action_id=booking_action.id)
        assert booked.status is ActionStatus.EXECUTED
        with pytest.raises(ConflictError):
            # The approval was already consumed; a second commit is refused,
            # not silently repeated.
            await core.commit_action(CONSOLE, action_id=booking_action.id)

        # Step 13: verify the booking independently. Not booked on the
        # strength of the execute call alone (section 63's warning).
        still_held = await core.get_appointment(CONSOLE, appointment_id=appointment.id)
        assert still_held.status is AppointmentStatus.HELD

        verified = await core.verify_action_externally(
            CONSOLE, action_id=booking_action.id
        )
        assert verified.status is ActionStatus.VERIFIED

        now_booked = await core.get_appointment(CONSOLE, appointment_id=appointment.id)
        assert now_booked.status is AppointmentStatus.BOOKED
        # Step 15: a calendar event was created as part of the verified
        # booking (Phase 7's execute_booking -> the fake calendar's store).
        assert now_booked.external_event_id is not None
        assert await fake_calendar.get_event(now_booked.external_event_id) is not None

        service_request = await core.confirm_service_booking(
            CONSOLE, service_request_id=service_request.id, appointment_id=appointment.id
        )
        assert service_request.status is ServiceRequestStatus.BOOKED

        completed_request = await core.complete_service_request(
            CONSOLE, service_request_id=service_request.id
        )
        assert completed_request.status is ServiceRequestStatus.COMPLETED

        # Step 16: mark the task completed only after verification. The task
        # was created with verification_required=True, so it must pass
        # READY -> EXECUTING -> VERIFYING -> COMPLETED with the verified
        # action's evidence (domain/tasks.py's state machine).
        task = await core.update_task(
            HERMES, task_id=task.id, update=TaskUpdate(state=TaskState.READY)
        )
        task = await core.update_task(
            HERMES, task_id=task.id, update=TaskUpdate(state=TaskState.EXECUTING)
        )
        task = await core.update_task(
            HERMES, task_id=task.id, update=TaskUpdate(state=TaskState.VERIFYING)
        )
        task = await core.update_task(
            HERMES,
            task_id=task.id,
            update=TaskUpdate(
                state=TaskState.COMPLETED,
                verification_evidence=(
                    f"booked and verified via action {booking_action.id}: "
                    f"{verified.external_reference}"
                ),
            ),
        )
        assert task.state is TaskState.COMPLETED
        assert task.verification_evidence

        # Step 14: provider/action history is recorded and retrievable — the
        # answer to "why did Hermes do that?" (section 62). Audit's ``target``
        # field is the action's ``target_entity_id`` (the provider here), not
        # the action id, so this filters recent records by ``action`` instead.
        recent = await core.read_audit(CONSOLE, limit=200)
        intents = {r.intent for r in recent if r.action == booking_action.id}
        assert "prepare_action" in intents
        assert "commit_action" in intents
        assert "verify_action" in intents
        call_intents = {r.intent for r in recent if r.action == call_action.id}
        assert "prepare_action" in call_intents

        # Section 97's hard rule: no phone-based payment authorization. Phase
        # 10 granted FINANCIAL_PAYMENT to the Console alone, so the assertion
        # is that nothing in *this* scenario touched payment and that the
        # client which ran it cannot pay — not that the capability is unheld
        # anywhere, which stopped being true when bills landed.
        assert Capability.FINANCIAL_PAYMENT not in HERMES.capabilities
        for client in all_clients():
            if client.has(Capability.SEND_EXTERNAL_MESSAGE):
                assert Capability.FINANCIAL_PAYMENT not in client.capabilities or (
                    client.client_id == CONSOLE.client_id
                ), client.client_id

        payment_types = {"prepare_payment", "commit_payment", "add_payee"}
        assert not payment_types & {str(r.tool) for r in recent if r.tool}


class TestWaitingWhenNecessary:
    """Step 8: create a waiting item when necessary — the provider does not
    pick up on the first call, and Hermes must not fabricate an answer."""

    async def test_no_answer_opens_a_waiting_item_then_a_followup_collects_the_quote(
        self, scenario
    ) -> None:
        core, _fake_calendar, fake_telephony, created_ids = scenario

        person = await core.create_person(
            HERMES, PersonDraft(display_name="Gene", is_primary=True)
        )
        created_ids.append(person.id)
        task = await core.create_task(HERMES, TaskDraft(title="Get the furnace serviced"))
        created_ids.append(task.id)
        provider = await core.create_entity(
            HERMES,
            EntityDraft(entity_type=WorldEntityType.PROVIDER, display_name="ABC HVAC"),
        )
        created_ids.append(provider.id)
        service_request = await core.create_service_request(
            HERMES, ServiceRequestDraft(subject="Furnace tune-up", task_id=task.id)
        )
        created_ids.append(service_request.id)

        fake_telephony.connected = False
        first_call = await core.request_provider_call(
            HERMES,
            service_request_id=service_request.id,
            provider_entity_id=provider.id,
            objective="schedule_hvac",
            collect=["availability", "diagnostic_fee"],
        )
        created_ids.append(first_call.id)
        await core.execute_action(HERMES, action_id=first_call.id)

        service_request = await core.get_service_request(
            HERMES, service_request_id=service_request.id
        )
        assert service_request.status is ServiceRequestStatus.AWAITING_PROVIDER
        assert service_request.waiting_item_id is not None
        created_ids.append(service_request.waiting_item_id)

        waiting_item = await core.get_waiting_item(
            HERMES, waiting_id=service_request.waiting_item_id
        )
        assert waiting_item.task_id == task.id
        assert waiting_item.waiting_on_entity_id == provider.id

        # The provider calls back: a follow-up call collects the quote. A
        # distinct objective from the first call's, both because that is
        # what a real follow-up looks like ("confirm" rather than "ask
        # fresh") and because section 61's idempotency key is derived from
        # the exact payload (domain/actions.py) — two structurally identical
        # requests are, by design, one intent, not two.
        fake_telephony.connected = True
        fake_telephony.follow_up_required = False
        followup_call = await core.request_provider_call(
            HERMES,
            service_request_id=service_request.id,
            provider_entity_id=provider.id,
            objective="confirm_hvac_followup",
            collect=["availability", "diagnostic_fee"],
        )
        created_ids.append(followup_call.id)
        await core.execute_action(HERMES, action_id=followup_call.id)

        service_request = await core.get_service_request(
            HERMES, service_request_id=service_request.id
        )
        assert service_request.status is ServiceRequestStatus.QUOTE_COLLECTED
        assert service_request.diagnostic_fee == "$89"

        resolved = await core.resolve_waiting_item(
            HERMES, waiting_id=waiting_item.id
        )
        assert resolved.status.value == "resolved"
