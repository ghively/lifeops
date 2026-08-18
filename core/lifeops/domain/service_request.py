"""ServiceRequest domain model (BUILD_SPEC sections 36, 67, 97, 101).

Section 67's provider workflow is a sequence:

    identify problem -> inspect asset/history -> find previous provider ->
    research alternatives -> check scheduling preference -> check calendar ->
    contact provider -> collect availability/fees -> WAITING_EXTERNAL if
    needed -> prepare booking -> approval if required -> book -> verify ->
    calendar event -> complete

A ``ServiceRequest`` is the durable record of one pass through that sequence —
the same role ``Appointment`` plays for section 63's booking flow, and built
the same way: a small status machine, projected into the world graph as
``WorldEntity`` facts rather than a bespoke repository (``facts`` are strings
because NornicDB property values cannot be maps).

The status machine intentionally does not include a "researching alternatives"
sub-state or a "checked calendar" flag — section 105's anti-overengineering
gate: those are steps a caller takes before opening or advancing a request,
not facts this record needs to persist to satisfy section 101's acceptance
scenario. What *is* modelled is exactly what section 101 checks for: contact
happened, a quote was or was not collected, a waiting item opened when the
provider did not answer immediately, a booking was requested, approved,
booked, and the request completed only once that booking was independently
verified (never merely because a call went well).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from lifeops.domain.world import WorldEntity, WorldEntityType
from lifeops.errors import ValidationError
from lifeops.ids import new_service_request_id


class ServiceRequestStatus(StrEnum):
    """Section 67's flow, collapsed to the states section 101 actually checks.

    ``AWAITING_PROVIDER`` is the WAITING_EXTERNAL state of section 55/67: a
    ``WaitingItem`` exists and nobody has answered yet. ``QUOTE_COLLECTED`` is
    reached either directly from ``CONTACTING_PROVIDER`` (the provider
    answered and gave a fee on the spot) or from ``AWAITING_PROVIDER`` (they
    called back).
    """

    RESEARCHING = "researching"
    CONTACTING_PROVIDER = "contacting_provider"
    AWAITING_PROVIDER = "awaiting_provider"
    QUOTE_COLLECTED = "quote_collected"
    BOOKING_REQUESTED = "booking_requested"
    BOOKED = "booked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


TERMINAL_SERVICE_REQUEST_STATUSES: frozenset[ServiceRequestStatus] = frozenset(
    {ServiceRequestStatus.COMPLETED, ServiceRequestStatus.CANCELLED}
)

# Exhaustive and explicit, the same discipline as domain/tasks.py's
# _TRANSITIONS: a lookup miss is a denial, not a default-allow.
_TRANSITIONS: dict[ServiceRequestStatus, frozenset[ServiceRequestStatus]] = {
    ServiceRequestStatus.RESEARCHING: frozenset(
        {ServiceRequestStatus.CONTACTING_PROVIDER, ServiceRequestStatus.CANCELLED}
    ),
    ServiceRequestStatus.CONTACTING_PROVIDER: frozenset(
        {
            ServiceRequestStatus.AWAITING_PROVIDER,
            ServiceRequestStatus.QUOTE_COLLECTED,
            ServiceRequestStatus.RESEARCHING,
            ServiceRequestStatus.CANCELLED,
        }
    ),
    ServiceRequestStatus.AWAITING_PROVIDER: frozenset(
        {
            ServiceRequestStatus.QUOTE_COLLECTED,
            ServiceRequestStatus.CONTACTING_PROVIDER,
            ServiceRequestStatus.CANCELLED,
        }
    ),
    ServiceRequestStatus.QUOTE_COLLECTED: frozenset(
        {
            ServiceRequestStatus.BOOKING_REQUESTED,
            ServiceRequestStatus.CONTACTING_PROVIDER,
            ServiceRequestStatus.CANCELLED,
        }
    ),
    ServiceRequestStatus.BOOKING_REQUESTED: frozenset(
        {ServiceRequestStatus.BOOKED, ServiceRequestStatus.CANCELLED}
    ),
    ServiceRequestStatus.BOOKED: frozenset(
        {ServiceRequestStatus.COMPLETED, ServiceRequestStatus.CANCELLED}
    ),
    ServiceRequestStatus.COMPLETED: frozenset(),
    ServiceRequestStatus.CANCELLED: frozenset(),
}


def can_transition(current: ServiceRequestStatus, target: ServiceRequestStatus) -> bool:
    return target in _TRANSITIONS[current]


class ServiceRequest(BaseModel):
    """One pass through the section 67 provider workflow."""

    model_config = ConfigDict(extra="forbid")

    id: str
    subject: str
    status: ServiceRequestStatus = ServiceRequestStatus.RESEARCHING

    task_id: str | None = None
    asset_entity_id: str | None = None
    provider_entity_id: str | None = None

    #: Section 69's structured call results, folded into the request as they
    #: arrive rather than requiring a caller to re-read every call Action.
    availability: list[str] = Field(default_factory=list)
    diagnostic_fee: str | None = None

    waiting_item_id: str | None = None
    #: The most recent PLACE_PHONE_CALL or REQUEST_QUOTE action.
    contact_action_id: str | None = None
    #: The BOOK_APPOINTMENT action, once one has been prepared.
    booking_action_id: str | None = None
    appointment_id: str | None = None

    notes: str = ""

    created_at: str
    updated_at: str
    created_by_client: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_SERVICE_REQUEST_STATUSES

    @staticmethod
    def make_id() -> str:
        return new_service_request_id()


class ServiceRequestDraft(BaseModel):
    """Input shape for opening a service request (section 101 step 1: identify
    the relevant asset first — ``asset_entity_id`` is how that shows up here)."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=300)
    task_id: str | None = None
    asset_entity_id: str | None = None
    provider_entity_id: str | None = None
    notes: str = Field(default="", max_length=2000)


# --- pure rules ---------------------------------------------------------------


def open_request(draft: ServiceRequestDraft, *, now: str, client_id: str) -> ServiceRequest:
    return ServiceRequest(
        id=ServiceRequest.make_id(),
        subject=draft.subject.strip(),
        task_id=draft.task_id,
        asset_entity_id=draft.asset_entity_id,
        provider_entity_id=draft.provider_entity_id,
        notes=draft.notes.strip(),
        created_at=now,
        updated_at=now,
        created_by_client=client_id,
    )


def advance(
    request: ServiceRequest,
    target: ServiceRequestStatus,
    *,
    now: str,
) -> ServiceRequest:
    """Move to ``target``, or raise if that transition is not in the table."""
    if request.is_terminal:
        raise ValidationError(
            f"service request {request.id} is {request.status} and cannot change status",
            service_request_id=request.id,
            status=str(request.status),
        )
    if request.status != target and not can_transition(request.status, target):
        raise ValidationError(
            f"cannot move service request from {request.status} to {target}",
            service_request_id=request.id,
            status=str(request.status),
            target=str(target),
            allowed=sorted(str(s) for s in _TRANSITIONS[request.status]),
        )
    updated = request.model_copy(deep=True)
    updated.status = target
    updated.updated_at = now
    return updated


def record_contact(
    request: ServiceRequest,
    *,
    action_id: str,
    provider_entity_id: str | None,
    now: str,
) -> ServiceRequest:
    """A call or quote request went out (section 67: "contact provider")."""
    updated = advance(request, ServiceRequestStatus.CONTACTING_PROVIDER, now=now)
    updated.contact_action_id = action_id
    if provider_entity_id is not None:
        updated.provider_entity_id = provider_entity_id
    return updated


def record_waiting(request: ServiceRequest, *, waiting_item_id: str, now: str) -> ServiceRequest:
    """The provider did not answer with a quote — waiting is required (section
    67's WAITING_EXTERNAL, section 101 step 8)."""
    updated = advance(request, ServiceRequestStatus.AWAITING_PROVIDER, now=now)
    updated.waiting_item_id = waiting_item_id
    return updated


def record_quote(
    request: ServiceRequest,
    *,
    availability: list[str] | None = None,
    diagnostic_fee: str | None = None,
    now: str,
) -> ServiceRequest:
    """Availability and/or a fee arrived (section 67: "collect availability/
    fees"; section 101 steps 6-7)."""
    updated = advance(request, ServiceRequestStatus.QUOTE_COLLECTED, now=now)
    if availability is not None:
        updated.availability = list(availability)
    if diagnostic_fee is not None:
        updated.diagnostic_fee = diagnostic_fee
    return updated


def record_booking_requested(
    request: ServiceRequest, *, action_id: str, now: str
) -> ServiceRequest:
    """A BOOK_APPOINTMENT action was prepared (section 101 step 10)."""
    updated = advance(request, ServiceRequestStatus.BOOKING_REQUESTED, now=now)
    updated.booking_action_id = action_id
    return updated


def record_booked(
    request: ServiceRequest, *, appointment_id: str, now: str
) -> ServiceRequest:
    """The booking was independently verified (section 101 step 13) — never
    called merely because the booking action executed."""
    updated = advance(request, ServiceRequestStatus.BOOKED, now=now)
    updated.appointment_id = appointment_id
    return updated


def complete(request: ServiceRequest, *, now: str) -> ServiceRequest:
    """Section 101 step 16: complete only after the booking is verified."""
    return advance(request, ServiceRequestStatus.COMPLETED, now=now)


def cancel(request: ServiceRequest, *, now: str) -> ServiceRequest:
    return advance(request, ServiceRequestStatus.CANCELLED, now=now)


_FACT_FIELDS: tuple[str, ...] = (
    "status",
    "task_id",
    "asset_entity_id",
    "provider_entity_id",
    "diagnostic_fee",
    "waiting_item_id",
    "contact_action_id",
    "booking_action_id",
    "appointment_id",
    "notes",
)


def service_request_to_entity(request: ServiceRequest) -> WorldEntity:
    """Project into the world graph for display (section 15).

    Read-only: ``NornicServiceRequestRepository`` owns the record, and stores
    ``availability`` as a native string array. This projection flattens it for
    the graph's facts bag, which is ``dict[str, str]`` — the flattening is a
    display concern here rather than the storage decision it used to be.
    """
    facts = {
        field: str(getattr(request, field))
        for field in _FACT_FIELDS
        if getattr(request, field) is not None
    }
    if request.availability:
        facts["availability"] = ";".join(request.availability)
    return WorldEntity(
        id=request.id,
        entity_type=WorldEntityType.SERVICE_REQUEST,
        display_name=request.subject,
        facts=facts,
        created_at=request.created_at,
        updated_at=request.updated_at,
        created_by_client=request.created_by_client,
    )


def entity_to_service_request(entity: WorldEntity) -> ServiceRequest:
    if entity.entity_type is not WorldEntityType.SERVICE_REQUEST:
        raise ValidationError(
            f"{entity.id} is not a service request", entity_id=entity.id
        )
    facts = entity.facts
    availability_raw = facts.get("availability", "")
    return ServiceRequest(
        id=entity.id,
        subject=entity.display_name,
        status=ServiceRequestStatus(facts.get("status", ServiceRequestStatus.RESEARCHING)),
        task_id=facts.get("task_id"),
        asset_entity_id=facts.get("asset_entity_id"),
        provider_entity_id=facts.get("provider_entity_id"),
        availability=availability_raw.split(";") if availability_raw else [],
        diagnostic_fee=facts.get("diagnostic_fee"),
        waiting_item_id=facts.get("waiting_item_id"),
        contact_action_id=facts.get("contact_action_id"),
        booking_action_id=facts.get("booking_action_id"),
        appointment_id=facts.get("appointment_id"),
        notes=facts.get("notes", ""),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        created_by_client=entity.created_by_client,
    )
