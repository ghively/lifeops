"""Bills, payees, and the payment path (BUILD_SPEC sections 56, 72, 99).

Section 72 states seven rules. Five were already true before Phase 10 existed
because the outbox was built first; these tests pin all seven anyway, because
"it follows from the architecture" is the kind of claim that stops being true
without anyone noticing.
"""

from __future__ import annotations

import pytest

from lifeops.clock import FrozenClock
from lifeops.core import LifeOpsCore
from lifeops.domain.actions import (
    ActionStatus,
    ActionType,
    RiskClass,
    payload_hash,
    requires_approval,
    risk_for_action,
)
from lifeops.domain.bills import (
    Bill,
    BillDraft,
    BillStatus,
    Payee,
    PayeeDraft,
    may_pay,
    validate_amount,
)
from lifeops.domain.people import Person
from lifeops.errors import LifeOpsError, ValidationError
from lifeops.policy.capabilities import CONSOLE, HERMES, Capability
from lifeops.repositories.fakes import (
    FakeActionRepository,
    FakeApprovalRepository,
    FakeAuditRepository,
    FakeBillRepository,
    FakeMemoryRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
    FakeWaitingRepository,
    FakeWorldRepository,
)

TS = "2026-01-01T00:00:00Z"


@pytest.fixture
async def core() -> LifeOpsCore:
    people = FakePersonRepository()
    await people.upsert(
        Person(id="person_u", display_name="U", is_primary=True,
               created_at=TS, updated_at=TS)
    )
    return LifeOpsCore(
        people=people, preferences=FakePreferenceRepository(), tasks=FakeTaskRepository(),
        memory=FakeMemoryRepository(), world=FakeWorldRepository(),
        waiting=FakeWaitingRepository(), actions=FakeActionRepository(),
        approvals=FakeApprovalRepository(), audit=FakeAuditRepository(),
        bills=FakeBillRepository(), clock=FrozenClock(),
    )


class TestAmounts:
    def test_money_is_text_with_two_places(self) -> None:
        """Binary floats turn 89.10 into 89.09999999999999, and this value is
        hashed into an approval binding."""
        assert validate_amount("89") == "89.00"
        assert validate_amount("89.10") == "89.10"

    @pytest.mark.parametrize("bad", ["", "abc", "1.2.3", "-5.00", "89.1", "89.123"])
    def test_ambiguous_or_negative_amounts_are_refused(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            validate_amount(bad)


class TestSectionSeventyTwoRules:
    def test_a_new_payee_is_r4_and_always_needs_approval(self) -> None:
        """Rule 1. An unnoticed payee is how a later payment goes somewhere
        nobody chose, so section 56 puts it on the same rung as paying."""
        assert risk_for_action(ActionType.ADD_PAYEE) is RiskClass.R4_FINANCIAL_LEGAL_MEDICAL
        assert requires_approval(ActionType.ADD_PAYEE) is True
        assert (
            requires_approval(ActionType.ADD_PAYEE, approve_external_communication=False)
            is True
        )

    def test_payment_always_needs_approval_and_cannot_be_relaxed(self) -> None:
        """Rule 2."""
        for action_type in (ActionType.PREPARE_PAYMENT, ActionType.COMMIT_PAYMENT):
            assert risk_for_action(action_type) is RiskClass.R4_FINANCIAL_LEGAL_MEDICAL
            assert (
                requires_approval(action_type, approve_external_communication=False)
                is True
            )

    def test_an_amount_change_invalidates_the_approval(self) -> None:
        """Rule 3, as arithmetic rather than as a promise."""
        before = payload_hash({"bill_id": "bill_1", "amount": "89.10"})
        after = payload_hash({"bill_id": "bill_1", "amount": "890.10"})
        assert before != after

    def test_a_payee_record_refuses_to_carry_a_credential(self) -> None:
        """Rule 5: credentials never reach the graph, so they can never be
        exposed to Hermes from it."""
        with pytest.raises(ValueError):
            PayeeDraft(display_name="Utility", secret_ref="4111111111111111")
        assert PayeeDraft(display_name="Utility", secret_ref="payee/utility").secret_ref


class TestPayeeApprovalGate:
    def _payee(self, approved: bool) -> Payee:
        return Payee(
            id="payee_utility", display_name="Utility", created_at=TS,
            approved_at=TS if approved else None,
        )

    def _bill(self, status: BillStatus = BillStatus.DUE) -> Bill:
        return Bill(
            id="bill_1", payee_id="payee_utility", description="Electricity",
            amount="89.10", status=status, created_at=TS, updated_at=TS,
        )

    def test_an_unapproved_payee_cannot_be_paid(self) -> None:
        with pytest.raises(ValidationError):
            may_pay(self._bill(), self._payee(approved=False))

    def test_an_approved_payee_and_a_due_bill_may_be_paid(self) -> None:
        may_pay(self._bill(), self._payee(approved=True))

    def test_an_already_paid_bill_is_not_paid_again(self) -> None:
        with pytest.raises(ValidationError):
            may_pay(self._bill(BillStatus.PAID), self._payee(approved=True))


class TestWhoMayPay:
    """Section 72 plus section 56: money moves only where a human is present."""

    async def test_hermes_cannot_prepare_a_payment(self, core: LifeOpsCore) -> None:
        assert Capability.FINANCIAL_PAYMENT not in HERMES.capabilities
        with pytest.raises(LifeOpsError) as excinfo:
            await core.record_payee(HERMES, PayeeDraft(display_name="Utility"))
        assert excinfo.value.code == "capability_denied"

    async def test_hermes_can_still_see_what_is_owed(self, core: LifeOpsCore) -> None:
        """Knowing a bill is due is not being able to pay it — Hermes must be
        able to tell the user, or it cannot help at all."""
        await core.record_payee(CONSOLE, PayeeDraft(display_name="Utility"))
        await core.approve_payee(CONSOLE, payee_id="payee_utility")
        await core.record_bill(
            CONSOLE, BillDraft(payee_id="payee_utility", description="Electricity",
                               amount="89.10")
        )
        assert [b.description for b in await core.list_bills(HERMES)] == ["Electricity"]

    async def test_the_console_path_needs_approval_before_it_can_commit(
        self, core: LifeOpsCore
    ) -> None:
        await core.record_payee(CONSOLE, PayeeDraft(display_name="Utility"))
        await core.approve_payee(CONSOLE, payee_id="payee_utility")
        bill = await core.record_bill(
            CONSOLE, BillDraft(payee_id="payee_utility", description="Electricity",
                               amount="89.10")
        )
        action = await core.prepare_bill_payment(CONSOLE, bill_id=bill.id)
        assert action.status is ActionStatus.NEEDS_APPROVAL
        with pytest.raises(LifeOpsError) as excinfo:
            await core.commit_action(CONSOLE, action_id=action.id)
        assert excinfo.value.code == "conflict"

    async def test_preparing_twice_reuses_the_live_action(
        self, core: LifeOpsCore
    ) -> None:
        """Section 60: two live payment actions for one bill is how a bill
        gets paid twice."""
        await core.record_payee(CONSOLE, PayeeDraft(display_name="Utility"))
        await core.approve_payee(CONSOLE, payee_id="payee_utility")
        bill = await core.record_bill(
            CONSOLE, BillDraft(payee_id="payee_utility", description="Electricity",
                               amount="89.10")
        )
        first = await core.prepare_bill_payment(CONSOLE, bill_id=bill.id)
        second = await core.prepare_bill_payment(CONSOLE, bill_id=bill.id)
        assert first.id == second.id

    async def test_a_bill_is_settled_only_with_external_confirmation(
        self, core: LifeOpsCore
    ) -> None:
        """Rule 4 and section 53: not paid because LifeOps believes it is."""
        await core.record_payee(CONSOLE, PayeeDraft(display_name="Utility"))
        await core.approve_payee(CONSOLE, payee_id="payee_utility")
        bill = await core.record_bill(
            CONSOLE, BillDraft(payee_id="payee_utility", description="Electricity",
                               amount="89.10")
        )
        with pytest.raises(ValidationError):
            await core.settle_bill(CONSOLE, bill_id=bill.id, external_reference="  ")
        settled = await core.settle_bill(
            CONSOLE, bill_id=bill.id, external_reference="CONF-12345"
        )
        assert settled.status is BillStatus.PAID
        assert settled.external_reference == "CONF-12345"
