"""CalendarProvider abstraction (BUILD_SPEC section 63).

Every backend that can read or write a calendar implements this Protocol.
Section 63's ordering — read, free/busy, hold, create, update, cancel — is
reflected directly in the method list so an implementation cannot offer
``create_event`` without ``create_hold`` existing first in the file, the same
discipline ``voice/provider.py`` uses for its five capabilities.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lifeops.domain.calendar import CalendarEvent, FreeBusySlot


@runtime_checkable
class CalendarProvider(Protocol):
    async def list_events(self, *, start_at: str, end_at: str) -> list[CalendarEvent]:
        """Section 63 step 1: read the calendar over a window."""
        ...

    async def free_busy(self, *, start_at: str, end_at: str) -> list[FreeBusySlot]:
        """Section 63 step 2."""
        ...

    async def create_hold(
        self, *, subject: str, start_at: str, end_at: str, notes: str = ""
    ) -> str:
        """Section 63 step 3. Returns the provider's reference for the hold —
        never a LifeOps-generated value, so a caller can always tell the
        provider actually reserved something."""
        ...

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
        """Section 63 step 4. Returns the external event id."""
        ...

    async def get_event(self, external_event_id: str) -> CalendarEvent | None:
        """Independent confirmation that an event exists — the mechanism
        behind section 63's warning that a hold, or even a provider's
        "created" response, is not itself proof of a booking."""
        ...

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
        """Section 63 step 5."""
        ...

    async def cancel_event(self, external_event_id: str) -> None:
        """Section 63 step 6."""
        ...

    async def health(self) -> tuple[bool, str]:
        """(healthy, message) — never raises for an ordinary connection
        failure."""
        ...
