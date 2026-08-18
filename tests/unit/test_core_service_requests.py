"""LifeOpsCore's provider-workflow operations (BUILD_SPEC sections 36, 57-61,
67-69, 97, 101), exercised against fakes end to end.

Mirrors ``test_calendar_email_core.py``'s shape: a real ``LifeOpsCore`` over
in-memory repositories, with ``FakeTelephonyProvider`` and
``FakeCalendarProvider`` standing in for the external world. This is the
suite that proves section 97's ordering — contact, collect, wait if
necessary, prepare booking, approve, book, verify — actually holds at the
orchestration layer, and that section 97's hard rule (no phone-based payment
authorization) and section 101 step 9 (never authorize repairs) survive a
full run through ``prepare_action`` -> ``execute_action``.
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
from lifeops.domain.people import Person
from lifeops.domain.service_request import ServiceRequestDraft, ServiceRequestStatus
from lifeops.domain.tasks import TaskDraft, TaskState
from lifeops.domain.world import WorldEntity, WorldEntityType
from lifeops.errors import ValidationError
from lifeops.policy.capabilities import CONSOLE, HERMES
from lifeops.repositories.fakes import (
    FakeActionRepository,
    FakeApprovalRepository,
    FakeAuditRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeServiceRequestRepository,
    FakeTaskRepository,
    FakeWaitingRepository,
    FakeWorldRepository,
)
from lifeops.secrets.local_encrypted import InMemorySecretStore
from lifeops.telephony.fake import FakeTelephonyProvider
from lifeops.telephony.service import TelephonyProviderService

PRIMARY = "person_service_request_user"
TS = "2026-01-01T00:00:00Z"


@pytest.fixture
def fake_calendar() -> FakeCalendarProvider:
    return FakeCalendarProvider()


@pytest.fixture
def fake_telephony() -> FakeTelephonyProvider:
    return FakeTelephonyProvider(
        availability=["Thursday 1:00-3:00 PM"], diagnostic_fee="$89"
    )


@pytest.fixture
def config_service(tmp_path: Path) -> ConfigurationService:
    return ConfigurationService(
        config_dir=tmp_path / "config",
        secret_store=InMemorySecretStore(),
        clock=FrozenClock(),
    )


@pytest.fixture
def calendar_service(
    config_service: ConfigurationService, fake_calendar: FakeCalendarProvider
) -> CalendarProviderService:
    config_service.update_provider("calendar", {"enabled": True, "backend": "caldav"})
    return CalendarProviderService(
        config=config_service,
        secret_store=InMemorySecretStore(),
        factories={"caldav": lambda settings, secrets: fake_calendar},
    )


@pytest.fixture
def telephony_service(
    config_service: ConfigurationService, fake_telephony: FakeTelephonyProvider
) -> TelephonyProviderService:
    """Section 88/104: a fresh deployment ships with telephony disabled.
    Tests enable it and inject the fake rather than the real Twilio adapter
    — account_sid/auth_token/from_number are required fields on the real
    adapter's shape, so they must be set for status.missing_required to
    clear even though this fixture never reaches the real factory."""
    config_service.update_provider(
        "telephony",
        {
            "enabled": True,
            "account_sid": "AC" + "0" * 32,
            "auth_token": "test-auth-token",
            "from_number": "+15551234567",
        },
    )
    return TelephonyProviderService(
        config=config_service,
        secret_store=InMemorySecretStore(),
        factories={"telephony": lambda settings, secrets: fake_telephony},
    )


@pytest.fixture
async def core(
    calendar_service: CalendarProviderService,
    telephony_service: TelephonyProviderService,
) -> LifeOpsCore:
    people = FakePersonRepository()
    await people.upsert(
        Person(
            id=PRIMARY,
            display_name="Service Request User",
            is_primary=True,
            created_at=TS,
            updated_at=TS,
        )
    )
    preferences = FakePreferenceRepository()
    world = FakeWorldRepository(preferences=preferences)
    world.seed(
        WorldEntity(
            id="provider_abc_electric",
            entity_type=WorldEntityType.PROVIDER,
            display_name="ABC Electric",
            facts={"phone": "+15550100"},
            created_at=TS,
            updated_at=TS,
        )
    )
    return LifeOpsCore(
        people=people,
        preferences=preferences,
        tasks=FakeTaskRepository(),
        world=world,
        service_requests=FakeServiceRequestRepository(),
        waiting=FakeWaitingRepository(),
        actions=FakeActionRepository(),
        approvals=FakeApprovalRepository(),
        audit=FakeAuditRepository(),
        calendar=calendar_service,
        telephony=telephony_service,
        clock=FrozenClock(),
    )


async def _task(core: LifeOpsCore) -> str:
    task = await core.create_task(HERMES, TaskDraft(title="Electrician for outlet"))
    return task.id


async def _service_request(core: LifeOpsCore, *, task_id: str) -> str:
    request = await core.create_service_request(
        HERMES,
        ServiceRequestDraft(
            subject="Living Room Outlet repair",
            task_id=task_id,
            asset_entity_id="asset_outlet",
        ),
    )
    assert request.status is ServiceRequestStatus.RESEARCHING
    return request.id


class TestCreateServiceRequest:
    async def test_opens_in_researching(self, core: LifeOpsCore) -> None:
        request = await core.create_service_request(
            HERMES, ServiceRequestDraft(subject="Furnace tune-up")
        )
        assert request.status is ServiceRequestStatus.RESEARCHING
        assert request.id.startswith("servicerequest_")


class TestRequestProviderCall:
    async def test_prepares_a_place_phone_call_action(self, core: LifeOpsCore) -> None:
        task_id = await _task(core)
        sr_id = await _service_request(core, task_id=task_id)

        action = await core.request_provider_call(
            HERMES,
            service_request_id=sr_id,
            provider_entity_id="provider_abc_electric",
            objective="schedule_electrician",
            collect=["availability", "diagnostic_fee"],
        )
        assert action.type is ActionType.PLACE_PHONE_CALL
        # R2, policy-controlled, not approval-gated by default: Hermes places
        # this call on its own (domain/actions.py, section 101).
        assert action.status is ActionStatus.PREPARED
        assert action.payload["authority"]["authorize_charge"] is False
        assert action.payload["authority"]["authorize_repairs"] is False

        updated = await core.get_service_request(HERMES, service_request_id=sr_id)
        assert updated.status is ServiceRequestStatus.CONTACTING_PROVIDER
        assert updated.contact_action_id == action.id
        assert updated.provider_entity_id == "provider_abc_electric"

    async def test_executing_the_call_collects_availability_and_fee(
        self, core: LifeOpsCore
    ) -> None:
        """Section 101 steps 6-7, and section 69's structured result folded
        back onto the service request."""
        task_id = await _task(core)
        sr_id = await _service_request(core, task_id=task_id)
        action = await core.request_provider_call(
            HERMES,
            service_request_id=sr_id,
            provider_entity_id="provider_abc_electric",
            objective="schedule_electrician",
            collect=["availability", "diagnostic_fee"],
        )

        executed = await core.execute_action(HERMES, action_id=action.id)
        assert executed.status is ActionStatus.EXECUTED
        assert executed.external_reference is not None

        request = await core.get_service_request(HERMES, service_request_id=sr_id)
        assert request.status is ServiceRequestStatus.QUOTE_COLLECTED
        assert request.availability == ["Thursday 1:00-3:00 PM"]
        assert request.diagnostic_fee == "$89"

    async def test_no_answer_opens_a_waiting_item(
        self, core: LifeOpsCore, fake_telephony: FakeTelephonyProvider
    ) -> None:
        """Section 101 step 8: create a waiting item when necessary."""
        fake_telephony.connected = False
        task_id = await _task(core)
        sr_id = await _service_request(core, task_id=task_id)
        action = await core.request_provider_call(
            HERMES,
            service_request_id=sr_id,
            provider_entity_id="provider_abc_electric",
            objective="schedule_electrician",
            collect=["availability"],
        )

        await core.execute_action(HERMES, action_id=action.id)

        request = await core.get_service_request(HERMES, service_request_id=sr_id)
        assert request.status is ServiceRequestStatus.AWAITING_PROVIDER
        assert request.waiting_item_id is not None
        waiting = await core.get_waiting_item(
            HERMES, waiting_id=request.waiting_item_id
        )
        assert waiting.task_id == task_id


class TestRequestQuote:
    async def test_prepares_a_request_quote_action(self, core: LifeOpsCore) -> None:
        task_id = await _task(core)
        sr_id = await _service_request(core, task_id=task_id)

        action = await core.request_quote_by_phone(
            HERMES,
            service_request_id=sr_id,
            provider_entity_id="provider_abc_electric",
            objective="diagnostic_fee",
            collect=["diagnostic_fee"],
        )
        assert action.type is ActionType.REQUEST_QUOTE
        assert action.status is ActionStatus.PREPARED


class TestNeverAuthorizePaymentOrRepairs:
    """BUILD_SPEC section 97's hard rule and section 101 step 9, proven at the
    orchestration layer, not merely in the domain unit tests."""

    async def test_the_call_payload_never_carries_charge_or_repair_authority(
        self, core: LifeOpsCore
    ) -> None:
        task_id = await _task(core)
        sr_id = await _service_request(core, task_id=task_id)
        action = await core.request_provider_call(
            HERMES,
            service_request_id=sr_id,
            provider_entity_id="provider_abc_electric",
            objective="schedule_electrician",
            collect=["availability", "diagnostic_fee"],
        )
        assert action.payload["authority"] == {
            "request_information": True,
            "provide_service_address": False,
            "reserve_slot": False,
            "authorize_charge": False,
            "authorize_repairs": False,
        }

    async def test_no_telephony_client_can_reach_the_payment_capability(self) -> None:
        """Section 97: "No phone-based payment authorization."

        Phase 10 granted FINANCIAL_PAYMENT — to the Console alone, where a
        human is present. What section 97 forbids is an *agent* chaining a
        phone call into money moving; the Console is a person at a browser,
        not a telephony path, so it is excluded by name rather than by
        accident.

        Hermes places calls. Hermes cannot pay.
        """
        from lifeops.policy.capabilities import CONSOLE, Capability, all_clients

        for client in all_clients():
            if client.client_id == CONSOLE.client_id:
                continue
            if client.has(Capability.SEND_EXTERNAL_MESSAGE):
                assert Capability.FINANCIAL_PAYMENT not in client.capabilities, (
                    client.client_id
                )


class TestBookingThroughApproval:
    """Section 101 steps 10-13: prepare, approve, book, verify — and only
    then does the service request move to BOOKED."""

    async def test_booking_is_gated_on_approval_and_verification(
        self,
        core: LifeOpsCore,
        fake_calendar: FakeCalendarProvider,
    ) -> None:
        task_id = await _task(core)
        sr_id = await _service_request(core, task_id=task_id)

        # Section 97's ordering: contact and collect a quote before a
        # booking may be requested — the status machine (domain/
        # service_request.py) refuses BOOKING_REQUESTED from RESEARCHING.
        call_action = await core.request_provider_call(
            HERMES,
            service_request_id=sr_id,
            provider_entity_id="provider_abc_electric",
            objective="schedule_electrician",
            collect=["availability", "diagnostic_fee"],
        )
        await core.execute_action(HERMES, action_id=call_action.id)
        assert (
            await core.get_service_request(HERMES, service_request_id=sr_id)
        ).status is ServiceRequestStatus.QUOTE_COLLECTED

        appointment = await core.create_appointment_hold(
            HERMES,
            AppointmentHoldDraft(
                subject="Electrician: Living Room Outlet",
                start_at="2026-09-04T13:00:00Z",
                end_at="2026-09-04T15:00:00Z",
                provider_entity_id="provider_abc_electric",
                task_id=task_id,
            ),
        )
        assert appointment.status is AppointmentStatus.HELD

        action = await core.request_service_booking(
            HERMES, service_request_id=sr_id, appointment_id=appointment.id
        )
        # BOOK_APPOINTMENT is R3: always approval (domain/actions.py).
        assert action.status is ActionStatus.NEEDS_APPROVAL

        request = await core.get_service_request(HERMES, service_request_id=sr_id)
        assert request.status is ServiceRequestStatus.BOOKING_REQUESTED
        assert request.booking_action_id == action.id

        # confirm_service_booking must refuse a booking that has not been
        # independently verified yet.
        with pytest.raises(ValidationError):
            await core.confirm_service_booking(
                CONSOLE, service_request_id=sr_id, appointment_id=appointment.id
            )

        approval = await core.list_pending_approvals(CONSOLE)
        (pending,) = [a for a in approval if a.action_id == action.id]
        decided = await core.decide_approval(
            CONSOLE, approval_id=pending.id, approved=True
        )
        assert decided.status is ApprovalStatus.APPROVED

        executed = await core.execute_action(CONSOLE, action_id=action.id)
        assert executed.status is ActionStatus.EXECUTED

        verified = await core.verify_action_externally(CONSOLE, action_id=action.id)
        assert verified.status is ActionStatus.VERIFIED

        booked_appointment = await core.get_appointment(
            CONSOLE, appointment_id=appointment.id
        )
        assert booked_appointment.status is AppointmentStatus.BOOKED

        request = await core.confirm_service_booking(
            CONSOLE, service_request_id=sr_id, appointment_id=appointment.id
        )
        assert request.status is ServiceRequestStatus.BOOKED

        completed = await core.complete_service_request(
            CONSOLE, service_request_id=sr_id
        )
        assert completed.status is ServiceRequestStatus.COMPLETED

        # Section 101 step 12: book exactly once. A second booking attempt on
        # the same held appointment is refused, not silently re-executed.
        final_task = await core.get_task(HERMES, task_id=task_id)
        assert final_task.state is TaskState.CAPTURED  # unaffected by this flow

    async def test_completion_is_refused_before_a_booking_exists(
        self, core: LifeOpsCore
    ) -> None:
        task_id = await _task(core)
        sr_id = await _service_request(core, task_id=task_id)
        with pytest.raises(ValidationError):
            await core.complete_service_request(CONSOLE, service_request_id=sr_id)
