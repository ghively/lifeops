"""Calendar domain rules (BUILD_SPEC sections 36, 63, 96).

Pure functions only. Section 63's warning is the reason ``confirm_booking``
exists as a separate, narrow function rather than a bare status assignment:
"never claim a booking succeeded merely because a calendar hold exists."
"""

from __future__ import annotations

import pytest

from lifeops.domain.calendar import (
    Appointment,
    AppointmentHoldDraft,
    AppointmentStatus,
    CalendarEvent,
    appointment_to_entity,
    calendar_event_to_entity,
    cancel_appointment,
    confirm_booking,
    entity_to_appointment,
    entity_to_calendar_event,
    hold_is_expired,
    place_hold,
)
from lifeops.domain.world import WorldEntityType
from lifeops.errors import ValidationError

NOW = "2026-08-17T12:00:00Z"
LATER = "2026-08-17T13:00:00Z"
PAST = "2026-08-17T11:00:00Z"


def _draft(**overrides: object) -> AppointmentHoldDraft:
    base = dict(
        subject="Furnace tune-up",
        start_at="2026-09-01T14:00:00Z",
        end_at="2026-09-01T15:00:00Z",
    )
    return AppointmentHoldDraft(**{**base, **overrides})


def _held(**overrides: object) -> Appointment:
    base = dict(
        id="appointment_01",
        subject="Furnace tune-up",
        status=AppointmentStatus.HELD,
        start_at="2026-09-01T14:00:00Z",
        end_at="2026-09-01T15:00:00Z",
        hold_expires_at=LATER,
        created_at=NOW,
        updated_at=NOW,
    )
    return Appointment(**{**base, **overrides})


class TestHoldDraftValidation:
    def test_an_appointment_may_not_end_before_it_starts(self) -> None:
        with pytest.raises(ValidationError):
            place_hold(
                _draft(start_at="2026-09-01T15:00:00Z", end_at="2026-09-01T14:00:00Z"),
                now=NOW,
                client_id="hermes-personal",
                hold_reference="hold-1",
            )

    def test_a_hold_is_never_placed_without_a_provider_reference(self) -> None:
        """The reference comes from the provider call that already happened
        (core.py's ``AppointmentService.hold``); this function never invents
        one, so an Appointment can never claim a hold the provider did not
        actually grant."""
        appointment = place_hold(
            _draft(), now=NOW, client_id="hermes-personal", hold_reference="hold-1"
        )
        assert appointment.hold_reference == "hold-1"
        assert appointment.status is AppointmentStatus.HELD

    def test_hold_expiry_is_bounded_by_hold_minutes(self) -> None:
        short = place_hold(
            _draft(hold_minutes=5), now=NOW, client_id="c", hold_reference="h"
        )
        long = place_hold(
            _draft(hold_minutes=60), now=NOW, client_id="c", hold_reference="h"
        )
        assert short.hold_expires_at is not None
        assert long.hold_expires_at is not None
        assert short.hold_expires_at < long.hold_expires_at


class TestHoldExpiry:
    def test_a_hold_past_its_expiry_is_expired(self) -> None:
        assert hold_is_expired(_held(hold_expires_at=PAST), now=NOW) is True

    def test_a_hold_before_its_expiry_is_not(self) -> None:
        assert hold_is_expired(_held(hold_expires_at=LATER), now=NOW) is False

    def test_no_expiry_never_expires(self) -> None:
        assert hold_is_expired(_held(hold_expires_at=None), now=LATER) is False


class TestBookingConfirmation:
    def test_confirming_a_live_hold_moves_it_to_booked(self) -> None:
        booked = confirm_booking(
            _held(), external_event_id="ext-1", action_id="action_01", now=NOW
        )
        assert booked.status is AppointmentStatus.BOOKED
        assert booked.external_event_id == "ext-1"
        assert booked.booking_action_id == "action_01"

    def test_a_booking_may_not_be_confirmed_twice(self) -> None:
        """Section 63's warning enforced as a state check: BOOKED is not a
        state ``confirm_booking`` accepts as its starting point."""
        already_booked = _held(status=AppointmentStatus.BOOKED)
        with pytest.raises(ValidationError):
            confirm_booking(
                already_booked, external_event_id="ext-2", action_id="a2", now=NOW
            )

    def test_confirmation_does_not_recheck_hold_expiry(self) -> None:
        """Expiry gates *execution* (execute_booking refuses before calling
        the provider). By confirmation time, verification has proved the
        event exists — an action executed at T+25m and verified at T+35m
        used to raise here and strand the appointment HELD forever while a
        real event sat on the calendar."""
        expired = _held(hold_expires_at=PAST)
        booked = confirm_booking(
            expired, external_event_id="ext-1", action_id="a1", now=NOW
        )
        assert booked.status is AppointmentStatus.BOOKED

    def test_a_cancelled_appointment_may_not_be_booked(self) -> None:
        cancelled = _held(status=AppointmentStatus.CANCELLED)
        with pytest.raises(ValidationError):
            confirm_booking(cancelled, external_event_id="ext-1", action_id="a1", now=NOW)


class TestCancellation:
    def test_a_held_appointment_may_be_cancelled(self) -> None:
        cancelled = cancel_appointment(_held(), action_id="a1", now=NOW)
        assert cancelled.status is AppointmentStatus.CANCELLED

    def test_a_booked_appointment_may_be_cancelled(self) -> None:
        booked = _held(status=AppointmentStatus.BOOKED, external_event_id="ext-1")
        cancelled = cancel_appointment(booked, action_id="a1", now=NOW)
        assert cancelled.status is AppointmentStatus.CANCELLED

    def test_a_cancelled_appointment_may_not_be_cancelled_again(self) -> None:
        cancelled = _held(status=AppointmentStatus.CANCELLED)
        with pytest.raises(ValidationError):
            cancel_appointment(cancelled, action_id="a2", now=NOW)


class TestWorldProjection:
    def test_an_appointment_round_trips_through_world_entity_facts(self) -> None:
        appointment = _held(
            provider_entity_id="provider_abc_hvac",
            task_id="task_01",
            location="Home",
            notes="Gate code 1234",
        )
        entity = appointment_to_entity(appointment)
        assert entity.entity_type is WorldEntityType.APPOINTMENT
        assert entity.display_name == appointment.subject
        # NornicDB rejects map-valued properties; every fact must be a string.
        assert all(isinstance(v, str) for v in entity.facts.values())

        restored = entity_to_appointment(entity)
        assert restored.status is appointment.status
        assert restored.provider_entity_id == appointment.provider_entity_id
        assert restored.location == appointment.location

    def test_a_calendar_event_round_trips_through_world_entity_facts(self) -> None:
        event = CalendarEvent(
            id=CalendarEvent.make_id("fake", "ext-1"),
            external_event_id="ext-1",
            calendar_provider_id="fake",
            title="Dentist",
            start_at="2026-09-01T10:00:00Z",
            end_at="2026-09-01T10:30:00Z",
        )
        entity = calendar_event_to_entity(event, now=NOW)
        assert entity.entity_type is WorldEntityType.EVENT
        restored = entity_to_calendar_event(entity)
        assert restored.external_event_id == "ext-1"
        assert restored.title == "Dentist"

    def test_reading_the_same_calendar_window_twice_yields_the_same_id(self) -> None:
        """Section 63: reading the calendar caches into the world graph, and
        it must upsert, not duplicate — the id has to be deterministic."""
        first = CalendarEvent.make_id("fake", "ext-1")
        second = CalendarEvent.make_id("fake", "ext-1")
        assert first == second
