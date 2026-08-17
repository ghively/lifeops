"""Phase 4 domain rules (BUILD_SPEC sections 54, 55, 57, 59, 60, 61).

Pure functions only. These are the rules that decide whether the user gets
contacted twice, whether an approval still means what it meant when it was
granted, and whether a retry books a second appointment — so they are pinned
here rather than discovered in an adapter.
"""

from __future__ import annotations

import pytest

from lifeops.domain.actions import (
    Action,
    ActionDraft,
    ActionStatus,
    ActionType,
    make_idempotency_key,
    may_execute,
    payload_hash,
    prepare,
    record_attempt,
    requires_approval,
)
from lifeops.domain.approvals import (
    ApprovalStatus,
    authorises,
    consume,
    decide,
    expires_at,
    is_usable,
)
from lifeops.domain.approvals import request as request_approval
from lifeops.domain.waiting import (
    DEFAULT_MAX_FOLLOWUPS,
    WaitingItem,
    WaitingStatus,
    is_due,
    next_followup_at,
    record_followup,
    resolve,
)
from lifeops.errors import ValidationError

NOW = "2026-08-17T12:00:00Z"
LATER = "2026-08-20T12:00:00Z"


def _item(**overrides) -> WaitingItem:
    base = dict(
        id="waiting_01",
        task_id="task_01",
        subject="Availability from ABC Electric",
        waiting_since=NOW,
        next_action_at=NOW,
    )
    return WaitingItem(**{**base, **overrides})


class TestFollowupSchedule:
    def test_backoff_widens_rather_than_nagging(self) -> None:
        """Chasing a provider on a fixed short cadence is how an assistant
        becomes a nuisance."""
        first = next_followup_at(0, now=NOW)
        second = next_followup_at(1, now=NOW)
        third = next_followup_at(2, now=NOW)
        assert first < second < third

    def test_the_last_interval_repeats_rather_than_overflowing(self) -> None:
        assert next_followup_at(99, now=NOW) == next_followup_at(2, now=NOW)


class TestDueness:
    def test_an_item_past_its_wake_time_is_due(self) -> None:
        assert is_due(_item(next_action_at=NOW), now=LATER) is True

    def test_an_item_before_its_wake_time_is_not(self) -> None:
        assert is_due(_item(next_action_at=LATER), now=NOW) is False

    def test_an_item_held_under_a_live_lease_belongs_to_another_worker(self) -> None:
        """Two workers following up with one provider is the duplicate contact
        the lease exists to prevent."""
        held = _item(lease_owner="worker-a", lease_until=LATER)
        assert is_due(held, now=NOW) is False

    def test_an_expired_lease_is_reclaimable(self) -> None:
        """A worker that dies mid-item must not strand it forever."""
        stale = _item(lease_owner="worker-a", lease_until=NOW)
        assert is_due(stale, now=LATER) is True

    def test_resolved_items_are_never_woken(self) -> None:
        assert is_due(_item(status=WaitingStatus.RESOLVED), now=LATER) is False


class TestFollowupRecording:
    def test_a_followup_counts_and_reschedules(self) -> None:
        updated = record_followup(_item(), now=NOW)
        assert updated.followup_count == 1
        assert updated.last_contact_at == NOW
        assert updated.next_action_at is not None
        assert updated.status is WaitingStatus.WAITING

    def test_the_lease_is_released_so_the_next_tick_can_claim_it(self) -> None:
        updated = record_followup(_item(lease_owner="w", lease_until=LATER), now=NOW)
        assert updated.lease_owner is None
        assert updated.lease_until is None

    def test_exhausting_the_budget_escalates_rather_than_closing(self) -> None:
        """Silently giving up on the user's behalf is worse than saying
        'this needs you'."""
        item = _item(followup_count=DEFAULT_MAX_FOLLOWUPS - 1)
        updated = record_followup(item, now=NOW)
        assert updated.status is WaitingStatus.ESCALATED
        assert updated.next_action_at is None

    def test_attempt_count_tracks_separately_from_followups(self) -> None:
        updated = record_followup(_item(attempt_count=5), now=NOW)
        assert updated.attempt_count == 6
        assert updated.followup_count == 1

    def test_a_closed_item_takes_no_followup(self) -> None:
        with pytest.raises(ValidationError):
            record_followup(_item(status=WaitingStatus.RESOLVED), now=NOW)

    def test_resolving_stops_the_worker(self) -> None:
        updated = resolve(_item(), now=NOW)
        assert updated.status is WaitingStatus.RESOLVED
        assert updated.next_action_at is None


class TestPayloadHashing:
    def test_key_order_does_not_change_the_hash(self) -> None:
        """Otherwise an approval would be invalidated by a dict reordering
        that changed nothing."""
        assert payload_hash({"a": 1, "b": 2}) == payload_hash({"b": 2, "a": 1})

    def test_a_changed_value_changes_the_hash(self) -> None:
        assert payload_hash({"when": "1pm"}) != payload_hash({"when": "2pm"})


class TestIdempotency:
    def test_the_same_intent_yields_the_same_key(self) -> None:
        """A random key per attempt would defeat the mechanism it is named
        for (section 61)."""
        payload = {"provider": "abc", "slot": "thu-1pm"}
        assert make_idempotency_key(
            ActionType.BOOK_APPOINTMENT, payload
        ) == make_idempotency_key(ActionType.BOOK_APPOINTMENT, payload)

    def test_a_different_intent_yields_a_different_key(self) -> None:
        assert make_idempotency_key(
            ActionType.BOOK_APPOINTMENT, {"slot": "thu"}
        ) != make_idempotency_key(ActionType.BOOK_APPOINTMENT, {"slot": "fri"})

    def test_the_action_type_is_part_of_the_key(self) -> None:
        payload = {"x": 1}
        assert make_idempotency_key(
            ActionType.SEND_EMAIL, payload
        ) != make_idempotency_key(ActionType.REQUEST_QUOTE, payload)


class TestActionPreparation:
    def test_a_consequential_action_starts_needing_approval(self) -> None:
        action = prepare(
            ActionDraft(type=ActionType.BOOK_APPOINTMENT, payload={"slot": "thu"}),
            now=NOW,
            client_id="hermes-personal",
        )
        assert action.status is ActionStatus.NEEDS_APPROVAL
        assert requires_approval(ActionType.BOOK_APPOINTMENT)

    def test_a_low_risk_action_is_prepared_outright(self) -> None:
        action = prepare(
            ActionDraft(type=ActionType.REQUEST_QUOTE, payload={}),
            now=NOW,
            client_id="hermes-personal",
        )
        assert action.status is ActionStatus.PREPARED

    def test_an_action_needing_approval_may_not_execute_without_one(self) -> None:
        action = prepare(
            ActionDraft(type=ActionType.COMMIT_PAYMENT, payload={"amount": "89"}),
            now=NOW,
            client_id="hermes-personal",
        )
        assert may_execute(action) is False
        with pytest.raises(ValidationError):
            record_attempt(action, now=NOW)

    def test_recording_an_attempt_counts_it(self) -> None:
        action = prepare(
            ActionDraft(type=ActionType.REQUEST_QUOTE, payload={}),
            now=NOW,
            client_id="c",
        )
        attempted = record_attempt(action, now=NOW)
        assert attempted.attempt_count == 1
        assert attempted.status is ActionStatus.EXECUTING
        assert attempted.last_attempt_at == NOW


def _approved_pair(payload: dict) -> tuple[Action, object]:
    action = prepare(
        ActionDraft(type=ActionType.BOOK_APPOINTMENT, payload=payload),
        now=NOW,
        client_id="hermes-personal",
    )
    approval = request_approval(action, now=NOW, requested_by="hermes-personal")
    approval = decide(approval, approved=True, by="lifeops-console", now=NOW)
    return action, approval


class TestApprovalBinding:
    def test_an_approval_authorises_the_action_it_was_shown_for(self) -> None:
        action, approval = _approved_pair({"slot": "thu-1pm"})
        assert authorises(approval, action, now=NOW) is True

    def test_material_change_invalidates_the_approval(self) -> None:
        """Section 57, enforced as arithmetic rather than judgement: edit the
        payload after approval and the hashes stop matching."""
        action, approval = _approved_pair({"slot": "thu-1pm"})
        action.payload["slot"] = "fri-9am"
        action.payload_hash = payload_hash(action.payload)
        assert authorises(approval, action, now=NOW) is False

    def test_an_expired_approval_authorises_nothing(self) -> None:
        action, approval = _approved_pair({"slot": "thu"})
        assert authorises(approval, action, now="2027-01-01T00:00:00Z") is False

    def test_a_consumed_approval_cannot_be_replayed(self) -> None:
        """Otherwise one captured yes could authorise a second identical
        booking — the failure idempotency exists to prevent."""
        action, approval = _approved_pair({"slot": "thu"})
        spent = consume(approval, now=NOW)
        assert is_usable(spent, now=NOW) is False
        assert authorises(spent, action, now=NOW) is False

    def test_a_declined_approval_authorises_nothing(self) -> None:
        action, approval = _approved_pair({"slot": "thu"})
        declined = decide(approval, approved=False, by="lifeops-console", now=NOW)
        assert declined.status is ApprovalStatus.DECLINED
        assert authorises(declined, action, now=NOW) is False

    def test_deciding_after_expiry_expires_rather_than_approves(self) -> None:
        action = prepare(
            ActionDraft(type=ActionType.BOOK_APPOINTMENT, payload={}),
            now=NOW,
            client_id="c",
        )
        approval = request_approval(action, now=NOW, requested_by="c")
        late = decide(approval, approved=True, by="lifeops-console", now="2027-01-01T00:00:00Z")
        assert late.status is ApprovalStatus.EXPIRED

    def test_the_amount_travels_onto_the_approval(self) -> None:
        """Section 58's screen shows the fee; it must come from the payload,
        not be re-entered by whoever renders it."""
        action = prepare(
            ActionDraft(type=ActionType.BOOK_APPOINTMENT, payload={"amount": "89"}),
            now=NOW,
            client_id="c",
        )
        approval = request_approval(action, now=NOW, requested_by="c")
        assert approval.amount == "89"

    def test_expiry_is_bounded(self) -> None:
        assert expires_at(NOW) > NOW
