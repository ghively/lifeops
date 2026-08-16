"""EventBus and the change events LifeOpsCore publishes after mutations."""

from __future__ import annotations

import asyncio

from lifeops.clock import FrozenClock
from lifeops.core import LifeOpsCore
from lifeops.domain.preferences import PreferenceDraft
from lifeops.domain.tasks import TaskDraft
from lifeops.events import (
    _QUEUE_SIZE,
    PERSON_CHANGED,
    PREFERENCE_CHANGED,
    TASK_CHANGED,
    EventBus,
)
from lifeops.policy.capabilities import CONSOLE


class TestEventBus:
    async def test_subscriber_receives_published_events(self) -> None:
        bus = EventBus()
        queue = bus.subscribe()
        bus.publish({"type": TASK_CHANGED, "task_id": "task_1"})
        assert queue.get_nowait() == {"type": TASK_CHANGED, "task_id": "task_1"}

    async def test_unsubscribed_queue_stops_receiving(self) -> None:
        bus = EventBus()
        queue = bus.subscribe()
        bus.unsubscribe(queue)
        bus.publish({"type": TASK_CHANGED})
        assert queue.empty()

    async def test_a_full_queue_drops_instead_of_blocking(self) -> None:
        bus = EventBus()
        queue = bus.subscribe()
        for _ in range(_QUEUE_SIZE * 2):
            bus.publish({"type": TASK_CHANGED})
        assert queue.qsize() == _QUEUE_SIZE

    async def test_publish_with_no_subscribers_is_a_no_op(self) -> None:
        EventBus().publish({"type": TASK_CHANGED})


async def _core_with_bus(
    core: LifeOpsCore, clock: FrozenClock
) -> tuple[LifeOpsCore, EventBus, asyncio.Queue]:
    bus = EventBus()
    wired = LifeOpsCore(
        people=core._people,  # noqa: SLF001 — wiring the same fakes with a bus
        preferences=core._preferences,  # noqa: SLF001
        tasks=core._tasks,  # noqa: SLF001
        clock=clock,
        events=bus,
    )
    return wired, bus, bus.subscribe()


class TestCorePublishes:
    async def test_task_create_and_update_publish(self, core, clock: FrozenClock) -> None:
        wired, _, queue = await _core_with_bus(core, clock)

        task = await wired.create_task(CONSOLE, TaskDraft(title="Call dentist"))
        assert queue.get_nowait() == {"type": TASK_CHANGED, "task_id": task.id}

        await wired.update_task(CONSOLE, task_id=task.id, update=_ready())
        assert queue.get_nowait()["type"] == TASK_CHANGED

    async def test_preference_save_and_invalidate_publish(
        self, core, clock: FrozenClock
    ) -> None:
        wired, _, queue = await _core_with_bus(core, clock)

        pref = await wired.save_preference(
            CONSOLE, PreferenceDraft(key="scheduling.earliest", value="after 10")
        )
        assert queue.get_nowait()["type"] == PREFERENCE_CHANGED

        await wired.invalidate_preference(CONSOLE, preference_id=pref.id)
        assert queue.get_nowait()["type"] == PREFERENCE_CHANGED

    async def test_noop_restatement_does_not_publish(
        self, core, clock: FrozenClock
    ) -> None:
        wired, _, queue = await _core_with_bus(core, clock)
        draft = PreferenceDraft(key="scheduling.earliest", value="after 10")

        await wired.save_preference(CONSOLE, draft)
        queue.get_nowait()
        await wired.save_preference(CONSOLE, draft)  # identical value: no-op
        assert queue.empty()

    async def test_person_create_publishes(self, core, clock: FrozenClock) -> None:
        from lifeops.domain.people import PersonDraft

        wired, _, queue = await _core_with_bus(core, clock)
        person = await wired.create_person(CONSOLE, PersonDraft(display_name="Tori"))
        assert queue.get_nowait() == {"type": PERSON_CHANGED, "person_id": person.id}

    async def test_core_without_a_bus_still_works(self, core) -> None:
        task = await core.create_task(CONSOLE, TaskDraft(title="quiet"))
        assert task.id


def _ready():  # small helper to keep the test bodies readable
    from lifeops.domain.tasks import TaskState, TaskUpdate

    return TaskUpdate(state=TaskState.READY)
