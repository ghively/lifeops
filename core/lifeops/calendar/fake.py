"""FakeCalendarProvider — deterministic in-memory calendar for tests
(BUILD_SPEC sections 63, 88).

Development and CI use this and nothing else (AGENTS.md, section 88): no test
ever reaches a real calendar server. It is not offered as a selectable
``backend`` in the provider registry — a user cannot "configure" their way
into using it — it exists purely for test wiring, the same role
``voice/fake.py`` plays for TTS.
"""

from __future__ import annotations

import itertools

from lifeops.domain.calendar import CalendarEvent, FreeBusySlot
from lifeops.errors import ProviderError


class FakeCalendarProvider:
    """In-memory calendar. Holds and events share one id sequence so a test
    can tell them apart from their prefix (``hold-1``, ``event-1``)."""

    def __init__(self) -> None:
        self._events: dict[str, CalendarEvent] = {}
        self._counter = itertools.count(1)
        self.healthy = True

    async def list_events(self, *, start_at: str, end_at: str) -> list[CalendarEvent]:
        return sorted(
            (
                event
                for event in self._events.values()
                if event.start_at < end_at and event.end_at > start_at
            ),
            key=lambda e: e.start_at,
        )

    async def free_busy(self, *, start_at: str, end_at: str) -> list[FreeBusySlot]:
        events = await self.list_events(start_at=start_at, end_at=end_at)
        return [
            FreeBusySlot(start_at=event.start_at, end_at=event.end_at, busy=True)
            for event in events
        ]

    async def create_hold(
        self, *, subject: str, start_at: str, end_at: str, notes: str = ""
    ) -> str:
        # The real adapter PUTs a genuine VEVENT for a hold, so the slot
        # reads busy in free_busy and the hold is fetchable by uid. Storing
        # nothing here let "a hold blocks double-booking" tests pass against
        # semantics production does not have (2026-08-18 audit).
        external_id = f"hold-{next(self._counter)}"
        self._events[external_id] = CalendarEvent(
            id=CalendarEvent.make_id("fake", external_id),
            external_event_id=external_id,
            calendar_provider_id="fake",
            title=f"[LifeOps hold] {subject}",
            start_at=start_at,
            end_at=end_at,
        )
        return external_id

    async def create_event(
        self,
        *,
        subject: str,
        start_at: str,
        end_at: str,
        location: str = "",
        notes: str = "",
        hold_reference: str | None = None,
    ) -> str:
        # Like the real adapter: confirming a hold reuses the hold's uid, so
        # the hold upgrades in place instead of coexisting with the booking.
        external_id = hold_reference or f"event-{next(self._counter)}"
        self._events[external_id] = CalendarEvent(
            id=CalendarEvent.make_id("fake", external_id),
            external_event_id=external_id,
            calendar_provider_id="fake",
            title=subject,
            start_at=start_at,
            end_at=end_at,
            location=location,
        )
        return external_id

    async def get_event(self, external_event_id: str) -> CalendarEvent | None:
        return self._events.get(external_event_id)

    async def update_event(
        self,
        external_event_id: str,
        *,
        subject: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
        location: str | None = None,
        notes: str | None = None,
    ) -> None:
        existing = self._events.get(external_event_id)
        if existing is None:
            # Same error type as the real adapter (caldav.py raises
            # ProviderError here) — tests asserting the exception must see
            # production's type.
            raise ProviderError(
                f"no such calendar event: {external_event_id}", provider="fake"
            )
        updated = existing.model_copy(
            update={
                k: v
                for k, v in {
                    "title": subject,
                    "start_at": start_at,
                    "end_at": end_at,
                    "location": location,
                }.items()
                if v is not None
            }
        )
        self._events[external_event_id] = updated

    async def cancel_event(self, external_event_id: str) -> None:
        self._events.pop(external_event_id, None)

    async def health(self) -> tuple[bool, str]:
        return self.healthy, "fake calendar provider" if self.healthy else "forced unhealthy"
