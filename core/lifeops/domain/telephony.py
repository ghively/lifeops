"""Telephony call model (BUILD_SPEC sections 68, 69, 97).

Section 68's warning is the reason this module exists: *a phone conversation
cannot enlarge its own authority.* A call is placed with a constrained
``CallObjective`` — what to ask for, what facts to collect, and exactly what
the call is and is not allowed to agree to — and the answer comes back as a
structured ``CallResult`` rather than a transcript a model has to interpret
after the fact (section 69: "do not rely only on transcript").

Section 97's hard rule lives here as code, not as a comment: ``authorize_charge``
must always be ``False``. ``build_objective`` refuses to construct an objective
that sets it, so no caller — Hermes included — can talk a call into paying for
anything, no matter what it argues for over the phone. ``authorize_repairs``
is refused the same way, which is section 101 step 9 ("never authorize
repairs") enforced at construction rather than trusted to a prompt.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from lifeops.errors import ValidationError


class CallAuthority(BaseModel):
    """What a call may agree to on the user's behalf (section 68's example).

    ``authorize_charge`` and ``authorize_repairs`` are typed fields rather
    than free-form flags precisely so a reviewer — human or test — can see
    both are hard-pinned to ``False`` at the type level's only constructor,
    ``build_objective``, rather than merely defaulted.
    """

    model_config = ConfigDict(extra="forbid")

    request_information: bool = True
    provide_service_address: bool = False
    reserve_slot: bool = False
    #: Section 97: "No phone-based payment authorization." Never settable to
    #: True by ``build_objective``.
    authorize_charge: bool = False
    #: Section 101 step 9: "never authorize repairs."
    authorize_repairs: bool = False


class CallObjective(BaseModel):
    """The constrained brief a call is placed with (section 68).

    ``to_number`` is the destination — required, because a call with nowhere
    to dial cannot happen. Nothing in this module resolves it: this is a
    pure domain type, and looking up a provider's phone number is a
    repository read that belongs in ``core.py``'s orchestration layer, not
    here. ``build_objective`` requires the caller to already have it.
    """

    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1, max_length=200)
    to_number: str = Field(min_length=1, max_length=32)
    provider_entity_id: str | None = None
    collect: list[str] = Field(default_factory=list)
    authority: CallAuthority = Field(default_factory=CallAuthority)


class CallResult(BaseModel):
    """What a call actually produced (section 69).

    ``transcript`` is kept as supplemental evidence, not the primary record —
    section 69 is explicit that the structured fields above it are what
    LifeOps and Hermes reason from.
    """

    model_config = ConfigDict(extra="forbid")

    connected: bool
    objective_met: bool
    availability: list[str] = Field(default_factory=list)
    diagnostic_fee: str | None = None
    commitments_made: list[str] = Field(default_factory=list)
    follow_up_required: bool = False
    external_reference: str | None = None
    transcript: str | None = None


def build_objective(
    *,
    objective: str,
    to_number: str,
    provider_entity_id: str | None = None,
    collect: list[str] | None = None,
    request_information: bool = True,
    provide_service_address: bool = False,
    reserve_slot: bool = False,
) -> CallObjective:
    """The only constructor for ``CallObjective``.

    ``to_number`` is required and positioned right after ``objective`` on
    purpose — a call cannot be built without somewhere to dial, the same way
    it cannot be built with charge or repair authority (below).
    ``authorize_charge`` and ``authorize_repairs`` are not parameters: a
    caller cannot request them, so there is no argument to accidentally set
    to ``True``. This is section 97's hard rule and section 101 step 9 made
    structurally impossible to violate through this module, rather than
    merely validated after the fact.
    """
    return CallObjective(
        objective=objective.strip(),
        to_number=to_number.strip(),
        provider_entity_id=provider_entity_id,
        collect=list(collect or []),
        authority=CallAuthority(
            request_information=request_information,
            provide_service_address=provide_service_address,
            reserve_slot=reserve_slot,
            authorize_charge=False,
            authorize_repairs=False,
        ),
    )


def validate_objective(objective: CallObjective) -> None:
    """Defence in depth for objectives built any other way (e.g. loaded back
    from a persisted Action payload). Raises rather than silently clearing
    the field, so a tampered payload is a loud failure, not a quiet downgrade.
    """
    if not objective.to_number.strip():
        raise ValidationError(
            "a phone call must have a destination number", field="to_number"
        )
    if objective.authority.authorize_charge:
        raise ValidationError(
            "a phone call may never carry authorize_charge=True "
            "(BUILD_SPEC section 97: no phone-based payment authorization)",
            field="authority.authorize_charge",
        )
    if objective.authority.authorize_repairs:
        raise ValidationError(
            "a phone call may never carry authorize_repairs=True "
            "(BUILD_SPEC section 101 step 9: never authorize repairs)",
            field="authority.authorize_repairs",
        )


def call_payload(objective: CallObjective, *, service_request_id: str | None = None) -> dict:
    """The exact Action payload a phone-call/quote-request action carries.

    Validated on the way in so an Action can never be prepared with a payload
    the objective rules would reject.
    """
    validate_objective(objective)
    payload = objective.model_dump(mode="json")
    if service_request_id is not None:
        payload["service_request_id"] = service_request_id
    return payload


def objective_from_payload(payload: dict) -> CallObjective:
    """The inverse of ``call_payload``, ignoring bookkeeping keys it added."""
    fields = {k: v for k, v in payload.items() if k in CallObjective.model_fields}
    objective = CallObjective(**fields)
    validate_objective(objective)
    return objective
