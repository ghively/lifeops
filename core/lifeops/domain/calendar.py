"""Calendar domain model (BUILD_SPEC sections 36, 63, 96).

Section 63's ordering is the reason this module is shaped the way it is:

    1. read calendar
    2. free/busy
    3. create temporary hold
    4. create event
    5. update
    6. cancel

And its warning is the reason ``Appointment`` carries a status machine rather
than a single boolean: *never claim a booking succeeded merely because a
calendar hold exists.* A hold (``AppointmentStatus.HELD``) and a real booking
(``AppointmentStatus.BOOKED``) are different facts, and the only function that
can move one to the other is ``confirm_booking`` — which requires the evidence
a verified Action outbox entry carries, not merely a hold reference.

``CalendarEvent`` is the read-only projection of what section 63 step 1 finds
on the calendar. It is a different type from ``Appointment`` on purpose: an
Appointment is a LifeOps-initiated commitment with a lifecycle LifeOps drives,
while a CalendarEvent is whatever the calendar already contains, LifeOps or
not.

Both convert to and from ``WorldEntity`` so "Calendar records should relate to
LifeOps entities" (section 63) is not just a sentence — a booked appointment
and a read calendar entry are graph nodes the World screen can show, exactly
the way Person keeps its own richer model while projecting into the graph
(domain/world.py).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from lifeops.domain.world import WorldEntity, WorldEntityType
from lifeops.errors import ValidationError
from lifeops.ids import new_appointment_id, slug_id

#: Default length of a temporary hold before it must be confirmed or is
#: considered stale. Long enough for a human to approve a booking in the
#: Console, short enough that a forgotten hold does not squat on a calendar
#: slot indefinitely.
DEFAULT_HOLD_MINUTES = 30


class AppointmentStatus(StrEnum):
    """Section 63's booking lifecycle, made explicit as states rather than a
    flag so ``confirm_booking`` has something to check *from*."""

    HELD = "held"
    BOOKED = "booked"
    CANCELLED = "cancelled"


#: Terminal states. A cancelled appointment does not un-cancel; a new hold is
#: placed instead, which is a new Appointment record.
TERMINAL_APPOINTMENT_STATUSES: frozenset[AppointmentStatus] = frozenset(
    {AppointmentStatus.CANCELLED}
)


class Appointment(BaseModel):
    """One calendar commitment LifeOps is driving (section 63, 96)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    subject: str
    status: AppointmentStatus = AppointmentStatus.HELD

    provider_entity_id: str | None = None
    task_id: str | None = None

    start_at: str
    end_at: str
    location: str = ""
    notes: str = ""

    calendar_provider_id: str = "calendar"
    #: The hold reference the provider returned for step 3. Kept even after
    #: booking, as the record of how this appointment got its slot.
    hold_reference: str | None = None
    hold_expires_at: str | None = None
    #: Only set once ``confirm_booking`` has run against verified evidence.
    external_event_id: str | None = None
    #: The Action outbox entry that produced ``external_event_id`` — the
    #: traceable answer to "why did LifeOps say this was booked".
    booking_action_id: str | None = None

    created_at: str
    updated_at: str
    created_by_client: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_APPOINTMENT_STATUSES

    @staticmethod
    def make_id() -> str:
        return new_appointment_id()


class AppointmentHoldDraft(BaseModel):
    """Input shape for section 63 step 3: create a temporary hold."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=300)
    start_at: str
    end_at: str
    provider_entity_id: str | None = None
    task_id: str | None = None
    location: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=2000)
    hold_minutes: int = Field(default=DEFAULT_HOLD_MINUTES, ge=1, le=24 * 60)


class FreeBusySlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_at: str
    end_at: str
    busy: bool


class FreeBusyResult(BaseModel):
    """Section 63 step 2's answer over a requested window."""

    model_config = ConfigDict(extra="forbid")

    start_at: str
    end_at: str
    slots: list[FreeBusySlot] = Field(default_factory=list)


class CalendarEvent(BaseModel):
    """A read-only projection of one entry on the calendar (section 63 step 1).

    Distinct from ``Appointment``: this is whatever the provider already has,
    LifeOps-originated or not, and carries no booking lifecycle.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    external_event_id: str
    calendar_provider_id: str = "calendar"
    title: str
    start_at: str
    end_at: str
    location: str = ""

    @staticmethod
    def make_id(calendar_provider_id: str, external_event_id: str) -> str:
        # Deterministic, not a fresh ULID: reading the same calendar window
        # twice must upsert the same node rather than duplicating it.
        return slug_id("event", f"{calendar_provider_id}_{external_event_id}")


# --- pure rules ---------------------------------------------------------------


def _add_minutes(instant: str, minutes: int) -> str:
    moment = datetime.fromisoformat(instant.replace("Z", "+00:00"))
    return (moment + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def place_hold(
    draft: AppointmentHoldDraft,
    *,
    now: str,
    client_id: str,
    hold_reference: str | None,
) -> Appointment:
    """Build the local record of a hold LifeOps already placed externally
    (section 63 step 3). Never called before the provider call succeeds —
    the hold reference is required so an Appointment never claims a hold that
    was never actually taken."""
    if draft.end_at <= draft.start_at:
        raise ValidationError(
            "an appointment cannot end before it starts",
            start_at=draft.start_at,
            end_at=draft.end_at,
        )
    return Appointment(
        id=Appointment.make_id(),
        subject=draft.subject.strip(),
        status=AppointmentStatus.HELD,
        provider_entity_id=draft.provider_entity_id,
        task_id=draft.task_id,
        start_at=draft.start_at,
        end_at=draft.end_at,
        location=draft.location.strip(),
        notes=draft.notes.strip(),
        hold_reference=hold_reference,
        hold_expires_at=_add_minutes(now, draft.hold_minutes),
        created_at=now,
        updated_at=now,
        created_by_client=client_id,
    )


def hold_is_expired(appointment: Appointment, *, now: str) -> bool:
    if appointment.hold_expires_at is None:
        return False
    return now > appointment.hold_expires_at


def confirm_booking(
    appointment: Appointment,
    *,
    external_event_id: str,
    action_id: str,
    now: str,
) -> Appointment:
    """Move HELD -> BOOKED. The only function that may (section 63's warning).

    Raises rather than silently booking over a stale or wrong-state hold: an
    already-booked or cancelled appointment cannot be re-confirmed, and an
    expired hold must go through a fresh hold rather than be booked on a slot
    the provider may have already released.
    """
    if appointment.status is not AppointmentStatus.HELD:
        raise ValidationError(
            f"appointment {appointment.id} is {appointment.status}, not held; "
            "a booking may only be confirmed from a live hold",
            appointment_id=appointment.id,
            status=str(appointment.status),
        )
    if hold_is_expired(appointment, now=now):
        raise ValidationError(
            f"the hold for appointment {appointment.id} expired at "
            f"{appointment.hold_expires_at}; place a new hold before booking",
            appointment_id=appointment.id,
            hold_expires_at=appointment.hold_expires_at,
        )
    updated = appointment.model_copy(deep=True)
    updated.status = AppointmentStatus.BOOKED
    updated.external_event_id = external_event_id
    updated.booking_action_id = action_id
    updated.updated_at = now
    return updated


def cancel_appointment(appointment: Appointment, *, action_id: str, now: str) -> Appointment:
    """HELD or BOOKED -> CANCELLED."""
    if appointment.is_terminal:
        raise ValidationError(
            f"appointment {appointment.id} is already {appointment.status}",
            appointment_id=appointment.id,
            status=str(appointment.status),
        )
    updated = appointment.model_copy(deep=True)
    updated.status = AppointmentStatus.CANCELLED
    updated.booking_action_id = action_id
    updated.updated_at = now
    return updated


_APPOINTMENT_FACT_FIELDS: tuple[str, ...] = (
    "status",
    "provider_entity_id",
    "task_id",
    "start_at",
    "end_at",
    "location",
    "notes",
    "calendar_provider_id",
    "hold_reference",
    "hold_expires_at",
    "external_event_id",
    "booking_action_id",
)


def appointment_to_entity(appointment: Appointment) -> WorldEntity:
    """Project an Appointment into the world graph (section 63: "Calendar
    records should relate to LifeOps entities"). Facts are stored as strings
    (NornicDB property values cannot be maps), with ``None`` omitted rather
    than written as the literal string "None"."""
    facts = {
        field: str(getattr(appointment, field))
        for field in _APPOINTMENT_FACT_FIELDS
        if getattr(appointment, field) is not None
    }
    return WorldEntity(
        id=appointment.id,
        entity_type=WorldEntityType.APPOINTMENT,
        display_name=appointment.subject,
        facts=facts,
        created_at=appointment.created_at,
        updated_at=appointment.updated_at,
        created_by_client=appointment.created_by_client,
    )


def entity_to_appointment(entity: WorldEntity) -> Appointment:
    """The inverse of ``appointment_to_entity``. Raises on a malformed entity
    rather than guessing at defaults for required scheduling fields."""
    if entity.entity_type is not WorldEntityType.APPOINTMENT:
        raise ValidationError(
            f"{entity.id} is not an appointment", entity_id=entity.id
        )
    facts = entity.facts
    try:
        return Appointment(
            id=entity.id,
            subject=entity.display_name,
            status=AppointmentStatus(facts.get("status", AppointmentStatus.HELD)),
            provider_entity_id=facts.get("provider_entity_id"),
            task_id=facts.get("task_id"),
            start_at=facts["start_at"],
            end_at=facts["end_at"],
            location=facts.get("location", ""),
            notes=facts.get("notes", ""),
            calendar_provider_id=facts.get("calendar_provider_id", "calendar"),
            hold_reference=facts.get("hold_reference"),
            hold_expires_at=facts.get("hold_expires_at"),
            external_event_id=facts.get("external_event_id"),
            booking_action_id=facts.get("booking_action_id"),
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            created_by_client=entity.created_by_client,
        )
    except KeyError as exc:
        raise ValidationError(
            f"appointment {entity.id} is missing required fact {exc}",
            entity_id=entity.id,
        ) from None


def calendar_event_to_entity(event: CalendarEvent, *, now: str) -> WorldEntity:
    """Project a read calendar entry into the world graph.

    ``now`` stands in for both timestamps: a read projection has no creation
    history of its own on the LifeOps side, only "last seen".
    """
    return WorldEntity(
        id=event.id,
        entity_type=WorldEntityType.EVENT,
        display_name=event.title,
        facts={
            "external_event_id": event.external_event_id,
            "calendar_provider_id": event.calendar_provider_id,
            "start_at": event.start_at,
            "end_at": event.end_at,
            "location": event.location,
        },
        created_at=now,
        updated_at=now,
        created_by_client=None,
    )


def entity_to_calendar_event(entity: WorldEntity) -> CalendarEvent:
    if entity.entity_type is not WorldEntityType.EVENT:
        raise ValidationError(f"{entity.id} is not a calendar event", entity_id=entity.id)
    facts = entity.facts
    return CalendarEvent(
        id=entity.id,
        external_event_id=facts.get("external_event_id", ""),
        calendar_provider_id=facts.get("calendar_provider_id", "calendar"),
        title=entity.display_name,
        start_at=facts.get("start_at", ""),
        end_at=facts.get("end_at", ""),
        location=facts.get("location", ""),
    )
