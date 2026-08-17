"""The due-work worker (BUILD_SPEC sections 55, 93).

Runs entirely against fakes — no NornicDB. ``FakeWaitingRepository`` stands in
for NornicDB here, including in ``TestSurvivesRestart``: sharing one fake
repository instance between two independently-constructed ``LifeOpsCore``s and
two independently-constructed workers is exactly what "the worker holds no
state of its own" needs to prove.
"""

from __future__ import annotations

import asyncio

import pytest

from lifeops.clock import FrozenClock
from lifeops.core import LifeOpsCore
from lifeops.domain.waiting import WaitingItem, WaitingStatus
from lifeops.policy.capabilities import HERMES
from lifeops.repositories.fakes import (
    FakeAuditRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
    FakeWaitingRepository,
)
from lifeops.worker.due_work import DueWorkWorker

NOW = "2026-08-17T12:00:00Z"


def _make_core(
    waiting: FakeWaitingRepository, clock: FrozenClock, *, audit: FakeAuditRepository | None = None
) -> LifeOpsCore:
    return LifeOpsCore(
        people=FakePersonRepository(),
        preferences=FakePreferenceRepository(),
        tasks=FakeTaskRepository(),
        waiting=waiting,
        audit=audit or FakeAuditRepository(),
        clock=clock,
    )


def _due_item(item_id: str = "waiting_01", **overrides: object) -> WaitingItem:
    base: dict[str, object] = dict(
        id=item_id,
        task_id="task_01",
        subject="Availability from ABC Electric",
        waiting_since=NOW,
        next_action_at=NOW,
    )
    base.update(overrides)
    return WaitingItem(**base)


def _clock_at(iso: str = NOW) -> FrozenClock:
    from datetime import UTC, datetime

    return FrozenClock(datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(UTC))


@pytest.fixture
def clock() -> FrozenClock:
    return _clock_at(NOW)


@pytest.fixture
def waiting() -> FakeWaitingRepository:
    return FakeWaitingRepository()


@pytest.fixture
def core(waiting: FakeWaitingRepository, clock: FrozenClock) -> LifeOpsCore:
    return _make_core(waiting, clock)


class TestTick:
    async def test_a_due_item_is_claimed_and_followed_up(
        self, core: LifeOpsCore, waiting: FakeWaitingRepository
    ) -> None:
        await waiting.create(_due_item())
        worker = DueWorkWorker(core, owner="worker-a")

        acted = await worker.tick()

        assert acted == 1
        saved = await waiting.get("waiting_01")
        assert saved.followup_count == 1
        assert saved.next_action_at is not None
        assert saved.next_action_at > NOW

    def test_the_lease_is_released_by_the_continuation(self) -> None:
        """record_followup clears lease_owner/lease_until as part of the same
        update — 'release' is not a separate step the worker performs."""
        # Exercised end-to-end in the async test above; asserted here as a
        # standing fact about the rule the worker relies on.
        from lifeops.domain.waiting import record_followup

        updated = record_followup(_due_item(), now=NOW)
        assert updated.lease_owner is None
        assert updated.lease_until is None

    async def test_an_item_not_yet_due_is_left_alone(
        self, core: LifeOpsCore, waiting: FakeWaitingRepository
    ) -> None:
        await waiting.create(_due_item(next_action_at="2026-08-18T12:00:00Z"))
        worker = DueWorkWorker(core, owner="worker-a")

        acted = await worker.tick()

        assert acted == 0
        saved = await waiting.get("waiting_01")
        assert saved.followup_count == 0

    async def test_resolved_items_are_never_woken(
        self, core: LifeOpsCore, waiting: FakeWaitingRepository
    ) -> None:
        await waiting.create(_due_item(status=WaitingStatus.RESOLVED))
        worker = DueWorkWorker(core, owner="worker-a")

        assert await worker.tick() == 0

    async def test_a_claim_lost_to_another_worker_is_skipped_without_error(
        self, core: LifeOpsCore, waiting: FakeWaitingRepository, clock: FrozenClock
    ) -> None:
        await waiting.create(_due_item())
        # A second worker already claimed and holds a live lease.
        held = await waiting.claim(
            "waiting_01", owner="worker-b", until="2026-08-17T12:30:00Z", now=NOW
        )
        assert held is not None

        worker = DueWorkWorker(core, owner="worker-a")
        acted = await worker.tick()

        assert acted == 0
        saved = await waiting.get("waiting_01")
        assert saved.lease_owner == "worker-b"
        assert saved.followup_count == 0

    async def test_claim_racing_with_another_worker_returns_none_and_is_skipped(
        self, core: LifeOpsCore, waiting: FakeWaitingRepository
    ) -> None:
        """The race section 55's lease exists for: two workers list the same
        due item before either claims it. The loser's ``claim_waiting_item``
        call returns ``None`` (BUILD_SPEC section 55; core.py docstring: "or
        None if another holds it") and must be skipped, not raised on."""
        item = await waiting.create(_due_item())
        # Simulate the winner: claim it first, through the real core method,
        # exactly as worker-b's own tick() would.
        won = await core.claim_waiting_item(HERMES, waiting_id=item.id, owner="worker-b")
        assert won is not None

        worker = DueWorkWorker(core, owner="worker-a")
        # White-box: exercises exactly the branch tick() would take for this
        # item once it is in a due() batch (`_process`) without depending on
        # asyncio's scheduling to force the race at the due()/claim() boundary.
        acted = await worker._process(item)  # noqa: SLF001

        assert acted is False
        saved = await waiting.get(item.id)
        assert saved.lease_owner == "worker-b"

    async def test_one_bad_item_does_not_stop_the_batch_or_raise(
        self, core: LifeOpsCore, waiting: FakeWaitingRepository
    ) -> None:
        await waiting.create(_due_item(id="waiting_bad"))
        await waiting.create(_due_item(id="waiting_good"))

        async def flaky_continuation(core_, client, item):
            if item.id == "waiting_bad":
                raise RuntimeError("provider API exploded")
            return await core_.record_followup(client, waiting_id=item.id)

        worker = DueWorkWorker(core, owner="worker-a", continuation=flaky_continuation)

        acted = await worker.tick()  # must not raise

        assert acted == 1
        good = await waiting.get("waiting_good")
        bad = await waiting.get("waiting_bad")
        assert good.followup_count == 1
        # The bad item was claimed but its continuation failed: still leased,
        # not stuck forever (the lease expires and it becomes due again).
        assert bad.followup_count == 0
        assert bad.lease_owner == "worker-a"

    async def test_followups_exhausted_escalates_instead_of_looping_forever(
        self, core: LifeOpsCore, waiting: FakeWaitingRepository
    ) -> None:
        await waiting.create(_due_item(followup_count=2, max_followups=3))
        worker = DueWorkWorker(core, owner="worker-a")

        await worker.tick()

        saved = await waiting.get("waiting_01")
        assert saved.status == WaitingStatus.ESCALATED
        assert saved.next_action_at is None

        # An escalated, wake-less item is not due again.
        assert await worker.tick() == 0


class TestOwnerIdentity:
    def test_an_owner_is_generated_when_none_is_given(self, core: LifeOpsCore) -> None:
        worker = DueWorkWorker(core)
        assert worker.owner

    def test_two_workers_generate_different_owners(self, core: LifeOpsCore) -> None:
        assert DueWorkWorker(core).owner != DueWorkWorker(core).owner

    async def test_the_owner_is_stable_across_ticks(
        self, core: LifeOpsCore, waiting: FakeWaitingRepository
    ) -> None:
        worker = DueWorkWorker(core, owner="worker-a")
        await waiting.create(_due_item())
        await worker.tick()
        assert worker.owner == "worker-a"


class TestRunLoop:
    async def test_start_stop_is_clean_and_does_not_hang(self, core: LifeOpsCore) -> None:
        worker = DueWorkWorker(core, owner="worker-a", poll_interval_s=30.0)
        worker.start()
        assert worker.running

        await asyncio.wait_for(worker.stop(), timeout=1.0)

        assert not worker.running

    async def test_stop_before_start_is_a_no_op(self, core: LifeOpsCore) -> None:
        worker = DueWorkWorker(core, owner="worker-a")
        await asyncio.wait_for(worker.stop(), timeout=1.0)
        assert not worker.running

    async def test_starting_twice_does_not_spawn_a_second_task(
        self, core: LifeOpsCore
    ) -> None:
        worker = DueWorkWorker(core, owner="worker-a", poll_interval_s=30.0)
        worker.start()
        first_task = worker._task  # noqa: SLF001 - white-box check of the guard
        worker.start()
        assert worker._task is first_task  # noqa: SLF001
        await asyncio.wait_for(worker.stop(), timeout=1.0)

    async def test_the_loop_ticks_at_least_once_and_stops_promptly(
        self, core: LifeOpsCore, waiting: FakeWaitingRepository
    ) -> None:
        """A long poll interval must not make shutdown slow: stop() should not
        block for anywhere near ``poll_interval_s``."""
        await waiting.create(_due_item())
        worker = DueWorkWorker(core, owner="worker-a", poll_interval_s=120.0)

        worker.start()
        for _ in range(200):
            if (await waiting.get("waiting_01")).followup_count == 1:
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail("worker never ticked")

        await asyncio.wait_for(worker.stop(), timeout=1.0)


class TestSurvivesRestart:
    """BUILD_SPEC section 93: work survives a LifeOps restart.

    The worker is stateless by construction: everything it acts on comes back
    from a fresh ``due_waiting_items`` read. Simulated here by sharing one
    ``FakeWaitingRepository`` (standing in for NornicDB, which does not
    restart when LifeOps does) across two independently constructed
    ``LifeOpsCore``s and two independently constructed workers — nothing
    Python-level is shared between "process 1" and "process 2" except that
    repository.
    """

    async def test_a_second_worker_against_the_same_store_continues_the_item(
        self,
    ) -> None:
        shared_waiting = FakeWaitingRepository()
        await shared_waiting.create(_due_item())

        # "Process 1": claims and follows up once, then the process dies —
        # nothing about worker_1 or core_1 is reused below.
        clock_1 = _clock_at(NOW)
        core_1 = _make_core(shared_waiting, clock_1)
        worker_1 = DueWorkWorker(core_1, owner="lifeops-pid-111")
        assert await worker_1.tick() == 1

        after_first = await shared_waiting.get("waiting_01")
        assert after_first.followup_count == 1
        assert after_first.lease_owner is None  # released, not stranded

        # "LifeOps restart": brand-new Core, brand-new worker, brand-new
        # process-local owner id. Only the store persisted.
        clock_2 = FrozenClock(clock_1.now())
        clock_2.advance(48 * 3600)  # past the next backoff window
        core_2 = _make_core(shared_waiting, clock_2)
        worker_2 = DueWorkWorker(core_2, owner="lifeops-pid-222")

        assert await worker_2.tick() == 1
        after_restart = await shared_waiting.get("waiting_01")
        assert after_restart.followup_count == 2

    async def test_an_item_claimed_when_the_process_died_is_reclaimable(
        self,
    ) -> None:
        """A worker that dies mid-item must not strand it forever (domain
        rule already pinned in test_durable_work.py; this is the worker-level
        consequence): a fresh worker against the same store can still claim
        it once the lease's natural expiry has passed."""
        shared_waiting = FakeWaitingRepository()
        await shared_waiting.create(_due_item())
        await shared_waiting.claim(
            "waiting_01", owner="lifeops-pid-dead", until=NOW, now="2026-08-17T11:00:00Z"
        )

        # now == NOW == the dead worker's lease `until`: expired, reclaimable.
        core_2 = _make_core(shared_waiting, _clock_at(NOW))
        worker_2 = DueWorkWorker(core_2, owner="lifeops-pid-alive")

        assert await worker_2.tick() == 1
        saved = await shared_waiting.get("waiting_01")
        assert saved.followup_count == 1
