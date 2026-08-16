"""Time handling.

Everything LifeOps persists is temporal (BUILD_SPEC section 40), so time is
injected rather than read ad hoc from ``datetime.now()``. That keeps
supersession and validity-window tests deterministic instead of racing the
wall clock.

All timestamps are stored as RFC 3339 strings in UTC. NornicDB round-trips
them as opaque properties, and string comparison on that format is also
chronological comparison, so range filters work without a temporal type.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """Test clock. Advances only when told to."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 1, 1, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> datetime:
        from datetime import timedelta

        self._now = self._now + timedelta(seconds=seconds)
        return self._now


def to_iso(moment: datetime) -> str:
    """Serialise to a UTC RFC 3339 string with a trailing Z."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def now_iso(clock: Clock | None = None) -> str:
    return to_iso((clock or SystemClock()).now())
