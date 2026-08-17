"""The due-work worker — BUILD_SPEC section 55's continuation loop.

Section 55 is explicit: *"Do not introduce Temporal initially."* Durable
continuation state (``next_action_at``, ``attempt_count``, ``lease_owner``,
``lease_until``) already lives in NornicDB behind ``WaitingItem``
(domain/waiting.py) and the waiting operations on ``LifeOpsCore``. This module
is only the loop the section describes:

    query due items -> claim lease -> perform continuation -> persist result

The worker itself is deliberately stateless. It holds a reference to
``LifeOpsCore`` and an owner id to put on leases; nothing about which items
are due, which are leased, or what happened on the last tick survives in this
object. Kill the process and start a new one against the same NornicDB and it
picks up exactly where the durable state says to — that is what BUILD_SPEC
section 93 means by "work survives ... LifeOps restart", and it is true here
because there is nothing else to lose.

Running as a single asyncio task inside the LifeOps process is what section 55
calls "a small LifeOps worker" — not a process supervisor, not a queue, not a
scheduler dependency. Two of these (e.g. one per LifeOps process) are safe to
run at once: ``claim_waiting_item`` is an atomic lease, so a second worker
racing for the same item simply loses and moves on.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Awaitable, Callable

from lifeops.core import LifeOpsCore
from lifeops.domain.waiting import WaitingItem
from lifeops.policy.capabilities import DUE_WORK_WORKER, ClientIdentity

logger = logging.getLogger(__name__)

#: What "perform deterministic continuation" (section 55) means today: apply
#: the follow-up rule, which itself reschedules ``next_action_at`` or
#: escalates once the budget is spent (domain/waiting.py record_followup via
#: LifeOpsCore.record_followup). There is no external send path yet (that
#: arrives with email/telephony in later phases) for the worker to invoke
#: instead — "wake Hermes" is section 55's other branch, and this hook is
#: where a future phase plugs that in, without reshaping the loop itself.
Continuation = Callable[[LifeOpsCore, ClientIdentity, WaitingItem], Awaitable[WaitingItem]]


async def _default_continuation(
    core: LifeOpsCore, client: ClientIdentity, item: WaitingItem
) -> WaitingItem:
    return await core.record_followup(client, waiting_id=item.id)


class DueWorkWorker:
    """Runs one asyncio task that ticks over due ``WaitingItem``\\ s.

    Started and stopped by ``Container.startup()``/``shutdown()``.
    """

    def __init__(
        self,
        core: LifeOpsCore,
        *,
        client: ClientIdentity = DUE_WORK_WORKER,
        owner: str | None = None,
        poll_interval_s: float = 60.0,
        batch_limit: int = 50,
        continuation: Continuation = _default_continuation,
    ) -> None:
        self._core = core
        self._client = client
        self._owner = owner or f"due-work-{uuid.uuid4().hex[:12]}"
        self._poll_interval_s = poll_interval_s
        self._batch_limit = batch_limit
        self._continuation = continuation
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    @property
    def owner(self) -> str:
        """The lease owner this worker claims items under."""
        return self._owner

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Start the background tick loop. Idempotent."""
        if self.running:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="lifeops-due-work-worker")

    async def stop(self) -> None:
        """Signal the loop to stop and wait for the in-flight tick to finish.

        A tick already in progress is allowed to finish rather than being
        cancelled mid-item, so a claim is never abandoned between
        ``claim_waiting_item`` and the continuation that releases it. Even if
        it were cancelled there, the lease is bounded (WaitingService.claim's
        window) and would simply expire and become reclaimable — this just
        avoids relying on that for an ordinary shutdown.
        """
        self._stop_event.set()
        task, self._task = self._task, None
        if task is None:
            return
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.tick()
            except Exception:
                # One bad tick (e.g. a transient NornicDB error while listing
                # due items) must not end the worker; the next tick retries.
                logger.exception(
                    "due-work worker tick failed", extra={"owner": self._owner}
                )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._poll_interval_s
                )

    async def tick(self) -> int:
        """Claim and act on whatever is due right now.

        Returns the number of items acted on. One tick = claim what is due,
        act, release — "release" happens inside the continuation, since
        ``record_followup``/``resolve_waiting_item`` both clear the lease as
        part of the same durable update.
        """
        items = await self._core.due_waiting_items(self._client, limit=self._batch_limit)
        acted = 0
        for item in items:
            try:
                if await self._process(item):
                    acted += 1
            except Exception:
                # One bad item must not stop the rest of the batch, and must
                # not kill the worker. Its lease naturally expires and it
                # becomes due again on a later tick.
                logger.exception(
                    "due-work worker failed on waiting item",
                    extra={"waiting_id": item.id, "owner": self._owner},
                )
        return acted

    async def _process(self, item: WaitingItem) -> bool:
        claimed = await self._core.claim_waiting_item(
            self._client, waiting_id=item.id, owner=self._owner
        )
        if claimed is None:
            # Another worker's lease is live on this item. Not an error —
            # exactly the case section 55's lease exists to make safe.
            return False
        await self._continuation(self._core, self._client, claimed)
        return True
