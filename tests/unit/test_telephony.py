"""Unit tests for the telephony call model (BUILD_SPEC sections 68, 69, 97).

Section 97's hard rule — "No phone-based payment authorization" — and section
101 step 9 — "never authorize repairs" — are the load-bearing assertions here:
``build_call_objective`` must be structurally unable to grant either, and
``validate_objective``/``objective_from_payload`` must refuse a payload that
somehow carries one anyway (e.g. read back from a tampered record).
"""

from __future__ import annotations

import asyncio

import pytest

from lifeops.domain.telephony import (
    CallAuthority,
    CallObjective,
    build_objective,
    call_payload,
    objective_from_payload,
    validate_objective,
)
from lifeops.errors import ValidationError
from lifeops.telephony.fake import FakeTelephonyProvider


class TestBuildObjective:
    def test_authority_never_grants_charge_or_repair(self) -> None:
        objective = build_objective(
            objective="schedule_electrician", collect=["availability", "diagnostic_fee"]
        )
        assert objective.authority.authorize_charge is False
        assert objective.authority.authorize_repairs is False

    def test_there_is_no_parameter_to_request_either(self) -> None:
        """The hard rule is enforced by the function's shape, not by a runtime
        check on a caller-supplied value — there is no argument to pass."""
        import inspect

        params = set(inspect.signature(build_objective).parameters)
        assert "authorize_charge" not in params
        assert "authorize_repairs" not in params

    def test_other_authority_flags_pass_through(self) -> None:
        objective = build_objective(
            objective="schedule_electrician",
            provide_service_address=True,
            reserve_slot=True,
        )
        assert objective.authority.provide_service_address is True
        assert objective.authority.reserve_slot is True


class TestValidateObjective:
    def test_a_clean_objective_passes(self) -> None:
        objective = build_objective(objective="schedule_electrician")
        validate_objective(objective)  # does not raise

    def test_a_tampered_charge_authority_is_refused(self) -> None:
        tampered = CallObjective(
            objective="schedule_electrician",
            authority=CallAuthority(authorize_charge=True),
        )
        with pytest.raises(ValidationError):
            validate_objective(tampered)

    def test_a_tampered_repair_authority_is_refused(self) -> None:
        tampered = CallObjective(
            objective="schedule_electrician",
            authority=CallAuthority(authorize_repairs=True),
        )
        with pytest.raises(ValidationError):
            validate_objective(tampered)


class TestPayloadRoundTrip:
    def test_call_payload_carries_the_service_request_id(self) -> None:
        objective = build_objective(objective="schedule_electrician", collect=["availability"])
        payload = call_payload(objective, service_request_id="servicerequest_01")
        assert payload["service_request_id"] == "servicerequest_01"
        assert payload["objective"] == "schedule_electrician"

    def test_objective_from_payload_round_trips(self) -> None:
        objective = build_objective(
            objective="schedule_electrician",
            provider_entity_id="provider_abc",
            collect=["availability", "diagnostic_fee"],
        )
        payload = call_payload(objective, service_request_id="servicerequest_01")
        restored = objective_from_payload(payload)
        assert restored.objective == objective.objective
        assert restored.collect == objective.collect
        assert restored.authority.authorize_charge is False

    def test_a_tampered_stored_payload_is_refused_on_read_back(self) -> None:
        payload = {
            "objective": "schedule_electrician",
            "collect": [],
            "authority": {
                "request_information": True,
                "provide_service_address": False,
                "reserve_slot": False,
                "authorize_charge": True,
                "authorize_repairs": False,
            },
        }
        with pytest.raises(ValidationError):
            objective_from_payload(payload)


class TestFakeTelephonyProvider:
    def test_a_connected_call_collects_the_requested_facts(self) -> None:
        provider = FakeTelephonyProvider(
            availability=["Thursday 1:00-3:00 PM"], diagnostic_fee="$89"
        )
        objective = build_objective(
            objective="schedule_electrician", collect=["availability", "diagnostic_fee"]
        )
        result = asyncio.run(provider.dial(objective))
        assert result.connected is True
        assert result.objective_met is True
        assert result.availability == ["Thursday 1:00-3:00 PM"]
        assert result.diagnostic_fee == "$89"
        assert result.external_reference is not None

    def test_it_only_returns_facts_that_were_asked_for(self) -> None:
        provider = FakeTelephonyProvider(diagnostic_fee="$89")
        objective = build_objective(objective="schedule_electrician", collect=["diagnostic_fee"])
        result = asyncio.run(provider.dial(objective))
        assert result.availability == []
        assert result.diagnostic_fee == "$89"

    def test_no_answer_requires_follow_up(self) -> None:
        """Section 101 step 8: create a waiting item when necessary."""
        provider = FakeTelephonyProvider(connected=False)
        objective = build_objective(objective="schedule_electrician", collect=["availability"])
        result = asyncio.run(provider.dial(objective))
        assert result.connected is False
        assert result.follow_up_required is True
        assert result.objective_met is False

    def test_get_status_returns_the_prior_result(self) -> None:
        provider = FakeTelephonyProvider()
        objective = build_objective(objective="schedule_electrician", collect=["availability"])
        result = asyncio.run(provider.dial(objective))
        replayed = asyncio.run(provider.get_status(result.external_reference))
        assert replayed == result

    def test_get_status_is_none_for_an_unknown_reference(self) -> None:
        provider = FakeTelephonyProvider()
        assert asyncio.run(provider.get_status("call-does-not-exist")) is None
