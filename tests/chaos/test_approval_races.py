"""Approval-flow races and strands (BUILD_SPEC sections 57, 60, 86).

Pinned here after the 2026-08-18 audit found four ways section 57's
guarantees could bend under concurrency or mid-flight state changes:

- two concurrent commits could both spend one approval (the consume was a
  read-check-write, not a conditional write);
- ``update_payload`` left the old approval card PENDING, and ``decide``
  moved the action unconditionally — so declining the stale card and then
  approving the fresh one resurrected an explicitly-cancelled action;
- the telephony executor did service-request bookkeeping *after* the call
  was placed, inside the failure path — a bookkeeping refusal recorded a
  placed call as FAILED and discarded the provider's reference;
- engaging safe mode mid-execution made the result-recording write raise
  ``SafeModeError``, stranding the action in EXECUTING with its approval
  spent.

Fakes only — this file belongs in ``make test-fast``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from lifeops.calendar.fake import FakeCalendarProvider
from lifeops.calendar.service import CalendarProviderService
from lifeops.clock import FrozenClock
from lifeops.config.service import ConfigurationService
from lifeops.core import ActionService, LifeOpsCore
from lifeops.domain.actions import Action, ActionDraft, ActionStatus, ActionType
from lifeops.domain.actions import prepare as prepare_action_domain
from lifeops.domain.approvals import Approval, ApprovalStatus
from lifeops.domain.approvals import request as request_approval
from lifeops.domain.people import Person
from lifeops.domain.service_request import ServiceRequestDraft
from lifeops.domain.tasks import TaskDraft
from lifeops.domain.world import WorldEntity, WorldEntityType
from lifeops.errors import ConflictError, SafeModeError, ValidationError
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

NOW = "2026-09-01T00:00:00Z"
PRIMARY = "person_races_user"


def _service(
    approvals: FakeApprovalRepository | None = None,
) -> tuple[ActionService, FakeActionRepository, FakeApprovalRepository]:
    actions = FakeActionRepository()
    approvals = approvals if approvals is not None else FakeApprovalRepository()
    return (
        ActionService(actions=actions, approvals=approvals, clock=FrozenClock()),
        actions,
        approvals,
    )


async def _approved_action(
    service: ActionService,
    actions: FakeActionRepository,
    approvals: FakeApprovalRepository,
) -> Action:
    action = prepare_action_domain(
        ActionDraft(
            type=ActionType.BOOK_APPOINTMENT,
            payload={"appointment_id": "appointment_races_01"},
            target_entity_id="provider_races",
        ),
        now=NOW,
        client_id="hermes-personal",
    )
    created = await actions.create(action)
    approval = request_approval(created, now=NOW, requested_by="hermes-personal")
    await approvals.create(approval)
    decided = await service.decide(approval.id, approved=True, by="console-user")
    assert decided.status is ApprovalStatus.APPROVED
    return await service.get(created.id)


class _YieldingApprovalRepository(FakeApprovalRepository):
    """Forces the interleaving under test: every read yields the event loop,
    so two concurrent ``begin_commit`` coroutines both get past the
    ``authorises`` check before either reaches ``consume``. Without the
    conditional consume, both would then proceed to the external call."""

    async def get_for_action(self, action_id: str) -> Approval | None:
        result = await super().get_for_action(action_id)
        await asyncio.sleep(0)
        return result


class TestConcurrentCommit:
    async def test_two_concurrent_commits_spend_one_approval_exactly_once(
        self,
    ) -> None:
        """Section 57: an approval authorises exactly one commit — under
        concurrency, not just in sequence. The loser must fail *before* the
        external call, not after."""
        service, actions, approvals = _service(_YieldingApprovalRepository())
        action = await _approved_action(service, actions, approvals)

        results = await asyncio.gather(
            service.begin_commit(action.id, client_id="console"),
            service.begin_commit(action.id, client_id="console"),
            return_exceptions=True,
        )

        conflicts = [r for r in results if isinstance(r, ConflictError)]
        committed = [r for r in results if isinstance(r, Action)]
        assert len(conflicts) == 1, results
        assert len(committed) == 1, results
        # And exactly one attempt was recorded against the action.
        stored = await service.get(action.id)
        assert stored.attempt_count == 1

    async def test_the_fake_consume_is_a_compare_and_set(self) -> None:
        """The repository contract itself: the second consume of one
        approval gets None, never a second win."""
        service, actions, approvals = _service()
        action = await _approved_action(service, actions, approvals)
        approval = await approvals.get_for_action(action.id)
        assert approval is not None

        first = await approvals.consume(approval.id, consumed_at=NOW)
        second = await approvals.consume(approval.id, consumed_at=NOW)
        assert first is not None
        assert first.consumed_at == NOW
        assert second is None


class TestStaleApprovalCards:
    async def test_update_payload_supersedes_the_old_pending_card(self) -> None:
        """One action, one decidable card. The card for the old payload must
        stop being decidable the moment a new payload needs approval."""
        service, actions, approvals = _service()
        action = prepare_action_domain(
            ActionDraft(
                type=ActionType.SUBMIT_GROCERY_ORDER,
                payload={"shopping_list_id": "list_01", "total": "20.00"},
            ),
            now=NOW,
            client_id="hermes-personal",
        )
        created = await actions.create(action)
        first_card = request_approval(created, now=NOW, requested_by="hermes-personal")
        await approvals.create(first_card)

        await service.update_payload(
            created.id,
            payload={"shopping_list_id": "list_01", "total": "22.50"},
            client_id="console",
        )

        stale = await approvals.get(first_card.id)
        assert stale is not None
        assert stale.status is ApprovalStatus.EXPIRED
        # Deciding the superseded card is refused as final, so the old
        # resurrection sequence cannot even begin.
        with pytest.raises(ValidationError):
            await service.decide(first_card.id, approved=False, by="console-user")

    async def test_a_stale_hash_card_cannot_be_decided(self) -> None:
        """Defence in depth for cards written before the supersession rule
        (or by a racing process): a PENDING card whose hash no longer matches
        the action's payload is refused, not applied."""
        service, actions, approvals = _service()
        action = prepare_action_domain(
            ActionDraft(
                type=ActionType.SUBMIT_GROCERY_ORDER,
                payload={"shopping_list_id": "list_01", "total": "20.00"},
            ),
            now=NOW,
            client_id="hermes-personal",
        )
        created = await actions.create(action)
        stale_card = request_approval(created, now=NOW, requested_by="hermes-personal")
        await approvals.create(stale_card)
        # The payload moves on; the stale card stays PENDING (pre-fix data).
        created.payload = {"shopping_list_id": "list_01", "total": "22.50"}
        from lifeops.domain.actions import payload_hash

        created.payload_hash = payload_hash(created.payload)
        await actions.update(created)

        with pytest.raises(ConflictError) as excinfo:
            await service.decide(stale_card.id, approved=True, by="console-user")
        assert excinfo.value.details["reason"] == "approval_superseded"

    async def test_a_decision_cannot_move_an_action_no_longer_awaiting_one(
        self,
    ) -> None:
        """The resurrection bug, pinned directly: an action already CANCELLED
        must not be flipped back to APPROVED by a leftover matching card."""
        service, actions, approvals = _service()
        action = prepare_action_domain(
            ActionDraft(
                type=ActionType.SUBMIT_GROCERY_ORDER,
                payload={"shopping_list_id": "list_01", "total": "20.00"},
            ),
            now=NOW,
            client_id="hermes-personal",
        )
        created = await actions.create(action)
        card = request_approval(created, now=NOW, requested_by="hermes-personal")
        await approvals.create(card)
        created.status = ActionStatus.CANCELLED
        created.failure_reason = "declined by the user"
        await actions.update(created)

        with pytest.raises(ConflictError) as excinfo:
            await service.decide(card.id, approved=True, by="console-user")
        assert excinfo.value.details["reason"] == "action_not_awaiting_approval"
        stored = await service.get(created.id)
        assert stored.status is ActionStatus.CANCELLED


# --- executor-level strands ---------------------------------------------------


def _config(tmp_path: Path) -> ConfigurationService:
    return ConfigurationService(
        config_dir=tmp_path / "config",
        secret_store=InMemorySecretStore(),
        clock=FrozenClock(),
    )


async def _core_with_telephony(
    tmp_path: Path, fake: FakeTelephonyProvider
) -> LifeOpsCore:
    config = _config(tmp_path)
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
        factories={"telephony": lambda settings, secrets: fake},
    )
    people = FakePersonRepository()
    await people.upsert(
        Person(
            id=PRIMARY,
            display_name="Races User",
            is_primary=True,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    preferences = FakePreferenceRepository()
    world = FakeWorldRepository(preferences=preferences)
    world.seed(
        WorldEntity(
            id="provider_races_electric",
            entity_type=WorldEntityType.PROVIDER,
            display_name="Races Electric",
            facts={"phone": "+15550100"},
            created_at=NOW,
            updated_at=NOW,
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
        telephony=telephony,
        clock=FrozenClock(),
    )


class TestPlacedCallBookkeepingFailure:
    async def test_a_bookkeeping_refusal_cannot_record_a_placed_call_as_failed(
        self, tmp_path: Path
    ) -> None:
        """The dial is the external effect; everything after it is
        bookkeeping. If the service request went terminal while the call was
        being placed, the outbox must still say the call happened — with the
        provider's reference — because it did. Recording it FAILED invited a
        retry that dialled the provider twice."""
        fake = FakeTelephonyProvider()
        core = await _core_with_telephony(tmp_path, fake)

        task = await core.create_task(HERMES, TaskDraft(title="Fix the outlet"))
        request = await core.create_service_request(
            HERMES,
            ServiceRequestDraft(subject="Outlet repair", task_id=task.id),
        )
        action = await core.request_provider_call(
            HERMES,
            service_request_id=request.id,
            provider_entity_id="provider_races_electric",
            objective="schedule_electrician",
            collect=["availability"],
        )
        # The request goes terminal between prepare and execute.
        await core.cancel_service_request(CONSOLE, service_request_id=request.id)

        executed = await core.execute_action(HERMES, action_id=action.id)

        assert len(fake.calls) == 1  # the call really was placed, once
        assert executed.status is ActionStatus.EXECUTED
        assert executed.external_reference is not None
        assert executed.failure_reason is None


class TestSafeModeCannotStrandAnAction:
    async def test_result_recording_survives_a_mid_flight_safe_mode_flip(
        self, tmp_path: Path
    ) -> None:
        """Safe mode stops NEW effects; it must not refuse the bookkeeping
        write for an effect that already happened — that only strands the
        action in EXECUTING with its approval spent and nothing left able to
        finish it."""
        config = _config(tmp_path)
        config.update_provider("calendar", {"enabled": True, "backend": "caldav"})
        safe_mode = {"on": False}

        class FlippingCalendar(FakeCalendarProvider):
            async def create_event(self, **kwargs: object) -> str:
                # The emergency stop is hit while the booking is in flight.
                safe_mode["on"] = True
                return await super().create_event(**kwargs)  # type: ignore[arg-type]

        calendar = CalendarProviderService(
            config=config,
            secret_store=InMemorySecretStore(),
            factories={"caldav": lambda settings, secrets: FlippingCalendar()},
        )
        people = FakePersonRepository()
        await people.upsert(
            Person(
                id=PRIMARY,
                display_name="Races User",
                is_primary=True,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        preferences = FakePreferenceRepository()
        core = LifeOpsCore(
            people=people,
            preferences=preferences,
            tasks=FakeTaskRepository(),
            world=FakeWorldRepository(preferences=preferences),
            waiting=FakeWaitingRepository(),
            actions=FakeActionRepository(),
            approvals=FakeApprovalRepository(),
            audit=FakeAuditRepository(),
            calendar=calendar,
            clock=FrozenClock(),
            safe_mode=lambda: safe_mode["on"],
        )

        from lifeops.domain.calendar import AppointmentHoldDraft

        appointment = await core.create_appointment_hold(
            HERMES,
            AppointmentHoldDraft(
                subject="Electrician visit",
                start_at="2026-09-02T13:00:00Z",
                end_at="2026-09-02T15:00:00Z",
            ),
        )
        action = await core.book_appointment(HERMES, appointment_id=appointment.id)
        await core.decide_approval(CONSOLE, approval_id=(
            (await core.list_pending_approvals(CONSOLE, limit=10))[0].id
        ), approved=True)

        executed = await core.execute_action(CONSOLE, action_id=action.id)

        # The booking went out before the flip; the record must say so.
        assert executed.status is ActionStatus.EXECUTED
        # And safe mode still blocks NEW effects exactly as before.
        with pytest.raises(SafeModeError):
            await core.commit_action(CONSOLE, action_id=action.id)
