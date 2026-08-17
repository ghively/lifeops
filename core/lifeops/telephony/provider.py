"""TelephonyProvider abstraction (BUILD_SPEC section 68).

Mirrors ``calendar/provider.py``: every backend that can place and manage a
call implements this Protocol. ``dial`` takes a ``CallObjective`` rather than
a phone number and a script — the constrained-objective shape is section 68's
whole point, and a Protocol that accepted anything looser would let an
implementation reintroduce the authority it forbids.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lifeops.domain.telephony import CallObjective, CallResult


@runtime_checkable
class TelephonyProvider(Protocol):
    async def dial(self, objective: CallObjective) -> CallResult:
        """Place the call and return its structured result (section 69).

        Returns rather than raises on a call that connected but did not meet
        its objective — that is data (``objective_met=False``), not a
        transport failure. Raising is reserved for the call not being
        placeable at all (``ProviderError``).
        """
        ...

    async def hangup(self, external_reference: str) -> None:
        """End a call still in progress."""
        ...

    async def send_dtmf(self, external_reference: str, digits: str) -> None:
        """Send touch-tone digits during a live call (e.g. an extension)."""
        ...

    async def get_status(self, external_reference: str) -> CallResult | None:
        """Independent confirmation of what a past call actually did — the
        mechanism behind treating ``dial``'s return value as a claim rather
        than proof, the same discipline section 63 applies to a calendar
        hold. ``None`` if the reference is unknown to the provider."""
        ...

    async def health(self) -> tuple[bool, str]:
        """(healthy, message) — never raises for an ordinary connection
        failure."""
        ...
