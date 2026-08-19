"""Conditional writes really are atomic under concurrency (BUILD_SPEC 55, 57).

Two guarantees in this system rest on one Cypher idiom — a single write whose
``WHERE`` clause is the race guard, returning a row only to the caller that
won:

  * ``WaitingRepository.claim`` — one worker takes a lease, so a provider is
    never chased twice for the same waiting item (section 55);
  * ``ApprovalRepository.consume`` — one commit spends an approval, so a
    captured "yes" cannot authorise a second payment (section 57).

Both were written to the same shape and reviewed as correct, but neither had
ever been *run* concurrently. Reviewing a conditional write tells you the
query is well-formed; only racing it tells you the database isolates it. This
suite races them.

`docs/REMAINING_WORK.md` listed exactly this as open, needing a real NornicDB.

Skipped automatically when NornicDB is not reachable.
"""

from __future__ import annotations

import asyncio

import pytest

from lifeops.domain.approvals import Approval, ApprovalStatus
from lifeops.domain.waiting import WaitingItem
from lifeops.repositories.nornic.approvals import NornicApprovalRepository
from lifeops.repositories.nornic.client import NornicClient
from lifeops.repositories.nornic.waiting import NornicWaitingRepository

pytestmark = [pytest.mark.integration, pytest.mark.persistence]

TS = "2026-01-01T00:00:00Z"
LATER = "2026-01-01T01:00:00Z"

#: Enough contenders that a lost update would show up rather than being luck.
RACERS = 12


@pytest.fixture
async def waiting(nornic_client: NornicClient, test_label: str):
    repo = NornicWaitingRepository(nornic_client)
    item = WaitingItem(
        id=f"waiting_{test_label}",
        task_id=f"task_{test_label}",
        subject="Availability from ABC Electric",
        waiting_since=TS,
        next_action_at=TS,
    )
    await repo.create(item)
    try:
        yield repo, item
    finally:
        await nornic_client.write(
            "MATCH (w:WaitingItem {id: $id}) DETACH DELETE w", id=item.id
        )


@pytest.fixture
async def approval(nornic_client: NornicClient, test_label: str):
    repo = NornicApprovalRepository(nornic_client)
    record = Approval(
        id=f"approval_{test_label}",
        action_id=f"action_{test_label}",
        payload_hash="deadbeef",
        requested_by="hermes-personal",
        expires_at=LATER,
        status=ApprovalStatus.APPROVED,
        approved_by="lifeops-console",
        approved_at=TS,
        action_type="book_appointment",
        authorises_action="Book appointment",
        created_at=TS,
    )
    await repo.create(record)
    try:
        yield repo, record
    finally:
        await nornic_client.write(
            "MATCH (ap:Approval {id: $id}) DETACH DELETE ap", id=record.id
        )


class TestLeaseClaim:
    async def test_exactly_one_worker_wins_the_lease(self, waiting) -> None:
        """Section 55. Two workers following up with one provider is the
        duplicate contact the lease exists to prevent."""
        repo, item = waiting

        results = await asyncio.gather(
            *(
                repo.claim(item.id, owner=f"worker-{n}", until=LATER, now=TS)
                for n in range(RACERS)
            )
        )

        winners = [r for r in results if r is not None]
        assert len(winners) == 1, f"{len(winners)} workers claimed the same item"

        # And the lease that stuck belongs to the worker that was told it won.
        stored = await repo.get(item.id)
        assert stored is not None
        assert stored.lease_owner == winners[0].lease_owner

    async def test_a_held_lease_is_refused_until_it_expires(self, waiting) -> None:
        repo, item = waiting
        assert await repo.claim(item.id, owner="first", until=LATER, now=TS) is not None
        assert await repo.claim(item.id, owner="second", until=LATER, now=TS) is None

        # Once the lease has lapsed, the item is reclaimable — a worker that
        # died mid-item must not strand it forever.
        reclaimed = await repo.claim(
            item.id, owner="second", until="2026-01-01T02:00:00Z", now=LATER
        )
        assert reclaimed is not None
        assert reclaimed.lease_owner == "second"

    async def test_racing_a_reclaim_still_yields_one_winner(self, waiting) -> None:
        repo, item = waiting
        await repo.claim(item.id, owner="dead-worker", until=LATER, now=TS)

        results = await asyncio.gather(
            *(
                repo.claim(item.id, owner=f"worker-{n}", until="2026-01-01T02:00:00Z",
                           now=LATER)
                for n in range(RACERS)
            )
        )
        assert len([r for r in results if r is not None]) == 1


class TestApprovalConsume:
    async def test_an_approval_is_spent_exactly_once(self, approval) -> None:
        """Section 57. A captured 'yes' replayed against a second identical
        action is precisely the double-charge idempotency exists to stop."""
        repo, record = approval

        results = await asyncio.gather(
            *(repo.consume(record.id, consumed_at=TS) for _ in range(RACERS))
        )

        spent = [r for r in results if r is not None]
        assert len(spent) == 1, f"{len(spent)} commits spent one approval"

        stored = await repo.get(record.id)
        assert stored is not None
        assert stored.consumed_at is not None

    async def test_a_spent_approval_cannot_be_spent_again(self, approval) -> None:
        repo, record = approval
        assert await repo.consume(record.id, consumed_at=TS) is not None
        assert await repo.consume(record.id, consumed_at=LATER) is None

    async def test_consuming_a_missing_approval_returns_none(self, approval) -> None:
        """Distinguishable from losing the race — both are None, and both mean
        'you may not proceed', which is the answer that matters."""
        repo, _ = approval
        assert await repo.consume("approval_does_not_exist", consumed_at=TS) is None
