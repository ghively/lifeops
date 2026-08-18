"""FakeTelephonyProvider — deterministic in-memory telephony for tests
(BUILD_SPEC sections 68, 69, 88).

Same role ``calendar/fake.py`` plays for CalDAV: development and CI use this
and nothing else. It is not offered as a selectable backend in the provider
registry (a user cannot configure their way into it); it exists so
``tests/e2e/test_electrician_scenario.py`` can drive a real phone-call action
through ``LifeOpsCore`` without a phone line, and so ``TelephonyProviderService``
has something to inject in tests.

Responses are canned rather than scripted: a real IVR/human conversation is
out of scope for a fake, and section 69 already treats the structured result
as the primary record, not the conversation that produced it.
"""

from __future__ import annotations

import itertools

from lifeops.domain.telephony import CallObjective, CallResult


class FakeTelephonyProvider:
    """Deterministic in-memory phone line.

    ``connected`` and ``follow_up_required`` are instance-level toggles so a
    test can simulate "the provider did not pick up" (section 101 step 8:
    create a waiting item when necessary) without a second fake class.
    """

    def __init__(
        self,
        *,
        connected: bool = True,
        follow_up_required: bool = False,
        availability: list[str] | None = None,
        diagnostic_fee: str | None = "$89",
    ) -> None:
        self.connected = connected
        self.follow_up_required = follow_up_required
        self.availability = availability if availability is not None else [
            "Thursday 1:00-3:00 PM"
        ]
        self.diagnostic_fee = diagnostic_fee
        self.healthy = True
        self._counter = itertools.count(1)
        #: Every call placed, for test assertions ("book exactly once" style
        #: checks apply to the outbox, but this is useful for the call layer
        #: itself).
        self.calls: list[CallObjective] = []
        self._results: dict[str, CallResult] = {}

    async def dial(self, objective: CallObjective) -> CallResult:
        self.calls.append(objective)
        external_reference = f"call-{next(self._counter)}"

        if not self.connected:
            result = CallResult(
                connected=False,
                objective_met=False,
                follow_up_required=True,
                external_reference=external_reference,
                transcript="(no answer)",
            )
            self._results[external_reference] = result
            return result

        availability = (
            list(self.availability) if "availability" in objective.collect else []
        )
        diagnostic_fee = (
            self.diagnostic_fee if "diagnostic_fee" in objective.collect else None
        )
        result = CallResult(
            connected=True,
            objective_met=not self.follow_up_required,
            availability=availability,
            diagnostic_fee=diagnostic_fee,
            follow_up_required=self.follow_up_required,
            external_reference=external_reference,
            transcript=f"(fake call for objective: {objective.objective})",
        )
        self._results[external_reference] = result
        return result

    async def hangup(self, external_reference: str) -> None:
        # Deliberately keeps the result record: the protocol promises
        # get_status is an independent confirmation of what a *past* call
        # did, and a fake that forgets the call on hangup diverges from any
        # real provider's call log.
        return None

    async def send_dtmf(self, external_reference: str, digits: str) -> None:
        return None

    async def get_status(self, external_reference: str) -> CallResult | None:
        return self._results.get(external_reference)

    async def health(self) -> tuple[bool, str]:
        return self.healthy, "fake telephony provider" if self.healthy else "forced unhealthy"
