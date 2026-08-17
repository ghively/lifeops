"""Unit tests for the ServiceRequest domain model (BUILD_SPEC sections 36, 67,
97, 101). Pure rules only — no NornicDB, no Cypher."""

from __future__ import annotations

import pytest

from lifeops.domain.service_request import (
    ServiceRequest,
    ServiceRequestDraft,
    ServiceRequestStatus,
    advance,
    cancel,
    complete,
    entity_to_service_request,
    open_request,
    record_booked,
    record_booking_requested,
    record_contact,
    record_quote,
    record_waiting,
    service_request_to_entity,
)
from lifeops.errors import ValidationError

NOW = "2026-08-17T10:00:00Z"
LATER = "2026-08-17T11:00:00Z"


def _draft(**overrides: object) -> ServiceRequestDraft:
    base: dict[str, object] = {"subject": "Living Room Outlet repair"}
    return ServiceRequestDraft(**{**base, **overrides})


def _opened(**overrides: object) -> ServiceRequest:
    request = open_request(
        _draft(task_id="task_01", asset_entity_id="asset_outlet"),
        now=NOW,
        client_id="hermes-personal",
    )
    if overrides:
        request = request.model_copy(update=overrides)
    return request


class TestOpen:
    def test_opening_starts_in_researching(self) -> None:
        request = _opened()
        assert request.status is ServiceRequestStatus.RESEARCHING
        assert request.task_id == "task_01"
        assert request.asset_entity_id == "asset_outlet"

    def test_id_has_the_service_request_prefix(self) -> None:
        request = _opened()
        assert request.id.startswith("servicerequest_")


class TestTransitions:
    def test_researching_moves_to_contacting_provider(self) -> None:
        request = advance(
            _opened(), ServiceRequestStatus.CONTACTING_PROVIDER, now=LATER
        )
        assert request.status is ServiceRequestStatus.CONTACTING_PROVIDER
        assert request.updated_at == LATER

    def test_researching_cannot_jump_to_booked(self) -> None:
        with pytest.raises(ValidationError):
            advance(_opened(), ServiceRequestStatus.BOOKED, now=LATER)

    def test_a_terminal_request_accepts_no_further_transition(self) -> None:
        cancelled = cancel(_opened(), now=LATER)
        with pytest.raises(ValidationError):
            advance(cancelled, ServiceRequestStatus.RESEARCHING, now=LATER)

    def test_full_happy_path_to_completion(self) -> None:
        request = _opened()
        request = record_contact(
            request, action_id="action_1", provider_entity_id="provider_abc", now=NOW
        )
        assert request.status is ServiceRequestStatus.CONTACTING_PROVIDER
        assert request.contact_action_id == "action_1"
        assert request.provider_entity_id == "provider_abc"

        request = record_quote(
            request,
            availability=["Thursday 1:00-3:00 PM"],
            diagnostic_fee="$89",
            now=NOW,
        )
        assert request.status is ServiceRequestStatus.QUOTE_COLLECTED
        assert request.availability == ["Thursday 1:00-3:00 PM"]
        assert request.diagnostic_fee == "$89"

        request = record_booking_requested(request, action_id="action_2", now=NOW)
        assert request.status is ServiceRequestStatus.BOOKING_REQUESTED
        assert request.booking_action_id == "action_2"

        # Never authorised by a mere booking request — only a verified booking
        # moves this forward (section 101 step 13).
        request = record_booked(request, appointment_id="appointment_1", now=NOW)
        assert request.status is ServiceRequestStatus.BOOKED
        assert request.appointment_id == "appointment_1"

        request = complete(request, now=NOW)
        assert request.status is ServiceRequestStatus.COMPLETED
        assert request.is_terminal

    def test_no_answer_routes_through_waiting(self) -> None:
        """Section 101 step 8: create a waiting item when necessary."""
        request = _opened()
        request = record_contact(
            request, action_id="action_1", provider_entity_id="provider_abc", now=NOW
        )
        request = record_waiting(request, waiting_item_id="waiting_1", now=NOW)
        assert request.status is ServiceRequestStatus.AWAITING_PROVIDER
        assert request.waiting_item_id == "waiting_1"

        # The provider calls back with a quote.
        request = record_quote(request, diagnostic_fee="$89", now=LATER)
        assert request.status is ServiceRequestStatus.QUOTE_COLLECTED


class TestWorldEntityProjection:
    def test_round_trips_through_a_world_entity(self) -> None:
        request = record_quote(
            record_contact(
                _opened(),
                action_id="action_1",
                provider_entity_id="provider_abc",
                now=NOW,
            ),
            availability=["Thursday 1:00-3:00 PM", "Friday 9:00-11:00 AM"],
            diagnostic_fee="$89",
            now=NOW,
        )
        entity = service_request_to_entity(request)
        restored = entity_to_service_request(entity)

        assert restored == request

    def test_a_missing_availability_fact_round_trips_to_an_empty_list(self) -> None:
        request = _opened()
        entity = service_request_to_entity(request)
        restored = entity_to_service_request(entity)
        assert restored.availability == []
