"""Bill and payee persistence against a live NornicDB (BUILD_SPEC 72, 99).

The fakes prove the rules; only this proves the Cypher. Two properties here
cannot be checked any other way:

  * an amount survives as the exact string the domain validated — a repository
    that round-trips 89.10 as a float returns 89.09999999999999, and that
    value is hashed into an approval a human agreed to;
  * a payee's approval is not silently cleared by a later write, which is
    section 72's "new payee always requires approval" surviving an upsert
    rather than only a first insert.

Skipped automatically when NornicDB is not reachable.
"""

from __future__ import annotations

import pytest

from lifeops.domain.bills import Bill, BillStatus, Payee
from lifeops.repositories.nornic.bills import NornicBillRepository
from lifeops.repositories.nornic.client import NornicClient

pytestmark = [pytest.mark.integration, pytest.mark.persistence]

TS = "2026-01-01T00:00:00Z"


@pytest.fixture
async def bills(nornic_client: NornicClient, test_label: str):
    repo = NornicBillRepository(nornic_client)
    payee_id = f"payee_{test_label}"
    bill_id = f"bill_{test_label}"
    try:
        yield repo, payee_id, bill_id
    finally:
        await nornic_client.write(
            "MATCH (n) WHERE n.id IN $ids DETACH DELETE n", ids=[payee_id, bill_id]
        )


def _payee(payee_id: str, *, approved: bool = False) -> Payee:
    return Payee(
        id=payee_id,
        display_name="Utility Co",
        secret_ref="payee/utility",
        created_at=TS,
        approved_at=TS if approved else None,
        approved_by="lifeops-console" if approved else None,
    )


def _bill(bill_id: str, payee_id: str, *, amount: str = "89.10") -> Bill:
    return Bill(
        id=bill_id,
        payee_id=payee_id,
        description="Electricity",
        amount=amount,
        due_at="2026-02-01T00:00:00Z",
        created_at=TS,
        updated_at=TS,
    )


class TestRoundTrip:
    async def test_a_bill_and_its_payee_round_trip(self, bills) -> None:
        repo, payee_id, bill_id = bills
        await repo.upsert_payee(_payee(payee_id))
        await repo.create(_bill(bill_id, payee_id))

        stored = await repo.get(bill_id)
        assert stored is not None
        assert stored.payee_id == payee_id
        assert stored.status is BillStatus.DUE

    @pytest.mark.parametrize("amount", ["89.10", "0.05", "1200.00", "89.00"])
    async def test_the_amount_survives_as_written(self, bills, amount: str) -> None:
        """A float round trip turns 89.10 into 89.09999999999999, and that
        value is hashed into an approval binding."""
        repo, payee_id, bill_id = bills
        await repo.upsert_payee(_payee(payee_id))
        await repo.create(_bill(bill_id, payee_id, amount=amount))

        stored = await repo.get(bill_id)
        assert stored is not None
        assert stored.amount == amount
        assert isinstance(stored.amount, str)

    async def test_the_owed_to_edge_is_written(self, bills, nornic_client) -> None:
        repo, payee_id, bill_id = bills
        await repo.upsert_payee(_payee(payee_id))
        await repo.create(_bill(bill_id, payee_id))

        rows = await nornic_client.read(
            "MATCH (b:Bill {id: $bill})-[:OWED_TO]->(p:Payee {id: $payee}) "
            "RETURN count(*) AS n",
            bill=bill_id,
            payee=payee_id,
        )
        assert rows[0]["n"] == 1


class TestPayeeApprovalSurvives:
    async def test_an_upsert_does_not_clear_an_existing_approval(self, bills) -> None:
        """Section 72's gate must survive a later write, not only the first.

        If a routine re-save cleared approval, the next payment would be
        refused — or, worse, a re-approval would become routine enough that
        nobody reads it.
        """
        repo, payee_id, _ = bills
        await repo.upsert_payee(_payee(payee_id, approved=True))

        # A later write that knows nothing about the approval.
        await repo.upsert_payee(_payee(payee_id, approved=False))

        stored = await repo.get_payee(payee_id)
        assert stored is not None
        assert stored.is_approved is True
        assert stored.approved_by == "lifeops-console"

    async def test_an_unapproved_payee_stays_unapproved(self, bills) -> None:
        repo, payee_id, _ = bills
        await repo.upsert_payee(_payee(payee_id))
        stored = await repo.get_payee(payee_id)
        assert stored is not None
        assert stored.is_approved is False


class TestListing:
    async def test_status_filter_narrows_the_list(self, bills) -> None:
        repo, payee_id, bill_id = bills
        await repo.upsert_payee(_payee(payee_id))
        await repo.create(_bill(bill_id, payee_id))

        due = await repo.list_bills(statuses=[BillStatus.DUE], limit=500)
        assert bill_id in {b.id for b in due}

        paid = await repo.list_bills(statuses=[BillStatus.PAID], limit=500)
        assert bill_id not in {b.id for b in paid}

    async def test_settling_persists_the_confirmation(self, bills) -> None:
        repo, payee_id, bill_id = bills
        await repo.upsert_payee(_payee(payee_id))
        bill = await repo.create(_bill(bill_id, payee_id))

        bill.status = BillStatus.PAID
        bill.external_reference = "CONF-12345"
        bill.paid_at = "2026-02-02T00:00:00Z"
        await repo.update(bill)

        stored = await repo.get(bill_id)
        assert stored is not None
        assert stored.status is BillStatus.PAID
        assert stored.external_reference == "CONF-12345"
