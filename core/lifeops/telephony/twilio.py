"""TwilioTelephonyProvider — the real adapter (BUILD_SPEC sections 68, 69,
88, 97).

Speaks Twilio's REST API directly over ``httpx`` — already a project
dependency — rather than the ``twilio`` SDK package. The same choice
``calendar/caldav.py`` already made for CalDAV and ``email/imap_smtp.py``
made (via the standard library) for IMAP/SMTP: a well-documented REST
surface needs no vendor client library of its own (AGENTS.md: no new
dependency without written justification).

Twilio is a deliberate, named vendor choice — unlike the browser adapter,
telephony to the real phone network is inherently a paid third-party
service, and the config registry's fields (``account_sid``/``auth_token``/
``from_number``) commit to Twilio's shape specifically rather than staying
generic. Nothing in this codebase has ever spoken to a live Twilio account;
the request/response handling below is verified against Twilio's documented
API shape with a mocked transport (``tests/unit/test_telephony_twilio.py``),
not against a live account — unlike the browser adapter, which could be
exercised against a real, pre-installed Chromium.

One gap this module is honest about rather than papering over: **no
conversation capability.** ``dial()``'s whole point is to conduct a
constrained conversation and report what it learned (section 68's
objective, section 69's structured result) — that needs the Voice Bridge
(ASR + TTS + an LLM loop over live audio), which does not exist and, per
CLAUDE.md's Known gaps, belongs in the Hermes runtime rather than this
repository. A real, connected call therefore still cannot report
``objective_met=True``: it states its purpose via a static ``<Say>`` and
holds, and reports that nothing was asked or answered through
``transcript`` rather than fabricating an answer.

What is no longer a gap: **the destination number.** ``CallObjective`` now
carries a required ``to_number`` (``domain/telephony.py``), resolved in
``core.py``'s ``_prepare_provider_contact`` from the provider's own world-
entity ``'phone'`` fact before an objective is ever built — the deeper,
pre-existing plumbing gap this module used to document (nothing anywhere
resolved a phone number to actually call) is closed, so ``dial()`` places a
real outbound call rather than always refusing.

``hangup``, ``send_dtmf``, and ``get_status`` operate on a call SID Twilio
already issued, so they need no destination number and were already real.
"""

from __future__ import annotations

from urllib.parse import quote
from xml.sax.saxutils import escape

import httpx

from lifeops.domain.telephony import CallObjective, CallResult
from lifeops.errors import ProviderError

_BASE_URL = "https://api.twilio.com"
_API_VERSION = "2010-04-01"
_TIMEOUT_S = 30.0

#: Twilio call statuses that mean the call actually connected (to a human or
#: voicemail), as opposed to never connecting at all.
_CONNECTED_STATUSES = frozenset({"in-progress", "completed"})

_NO_CONVERSATION_TRANSCRIPT = (
    "LifeOps placed this call for real, but cannot yet hold a phone "
    "conversation (no Voice Bridge) — nothing was asked or answered."
)

#: DTMF tones Twilio's <Play digits="..."> verb accepts.
_VALID_DTMF_CHARS = frozenset("0123456789#*w")


class TwilioTelephonyProvider:
    """One Twilio account. Constructed fresh per call from stored Console
    settings, like ``ElevenLabsTTSProvider``, so a changed credential takes
    effect on the next call without a process restart."""

    def __init__(
        self,
        *,
        account_sid: str,
        auth_token: str,
        from_number: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number
        self._client = client or httpx.AsyncClient(
            base_url=_BASE_URL, timeout=_TIMEOUT_S, auth=(account_sid, auth_token)
        )
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _account_path(self, suffix: str = "") -> str:
        return f"/{_API_VERSION}/Accounts/{self._account_sid}{suffix}"

    def _call_path(self, external_reference: str) -> str:
        return self._account_path(f"/Calls/{quote(external_reference, safe='')}.json")

    async def health(self) -> tuple[bool, str]:
        try:
            response = await self._client.get(self._account_path(".json"))
        except httpx.HTTPError as exc:
            return False, f"could not reach Twilio: {exc}"
        if response.status_code == 200:
            status = response.json().get("status")
            if status == "active":
                return True, "connected to Twilio"
            return False, f"Twilio account is not active (status: {status})"
        if response.status_code == 401:
            return False, "Twilio rejected the account SID/auth token"
        return False, f"Twilio returned HTTP {response.status_code}"

    def _hold_twiml(self, objective: CallObjective) -> str:
        """No Voice Bridge exists to hold a live conversation (module
        docstring's gap), so the call states its purpose and holds — a human
        who answers hears why LifeOps called, even though nothing yet
        listens for a reply. Escaped since ``objective.objective`` is text a
        caller controls, not a trusted literal."""
        message = escape(f"This is an automated call regarding: {objective.objective}")
        return f'<Response><Say>{message}</Say><Pause length="20"/></Response>'

    async def dial(self, objective: CallObjective) -> CallResult:
        try:
            response = await self._client.post(
                self._account_path("/Calls.json"),
                data={
                    "To": objective.to_number,
                    "From": self._from_number,
                    "Twiml": self._hold_twiml(objective),
                },
            )
        except httpx.HTTPError as exc:
            raise _transport_error(exc) from exc
        _raise_for_status(response)
        data = response.json()
        # A brand-new call's status is 'queued' or 'ringing' here — Twilio
        # has not connected it yet at the time this response returns, so
        # connected is honestly False; get_status(), polled later against
        # the sid below, is where a real connection is learned.
        status = data.get("status")
        return CallResult(
            connected=status in _CONNECTED_STATUSES,
            # No conversation capability exists yet (module docstring), so
            # this can never truthfully claim the objective was met.
            objective_met=False,
            follow_up_required=True,
            external_reference=data.get("sid"),
            transcript=_NO_CONVERSATION_TRANSCRIPT,
        )

    async def hangup(self, external_reference: str) -> None:
        try:
            response = await self._client.post(
                self._call_path(external_reference), data={"Status": "completed"}
            )
        except httpx.HTTPError as exc:
            raise _transport_error(exc) from exc
        _raise_for_status(response)

    async def send_dtmf(self, external_reference: str, digits: str) -> None:
        """Twilio has no dedicated "inject DTMF into a live call" verb; the
        documented approach is to redirect the call to new TwiML that plays
        the digits — the same mechanism any live-call redirect uses."""
        invalid = set(digits) - _VALID_DTMF_CHARS
        if invalid:
            raise ProviderError(
                f"not valid DTMF digits: {''.join(sorted(invalid))!r}", provider="telephony"
            )
        twiml = f'<Response><Play digits="{digits}"/></Response>'
        try:
            response = await self._client.post(
                self._call_path(external_reference), data={"Twiml": twiml}
            )
        except httpx.HTTPError as exc:
            raise _transport_error(exc) from exc
        _raise_for_status(response)

    async def get_status(self, external_reference: str) -> CallResult | None:
        try:
            response = await self._client.get(self._call_path(external_reference))
        except httpx.HTTPError as exc:
            raise _transport_error(exc) from exc
        if response.status_code == 404:
            return None
        _raise_for_status(response)
        data = response.json()
        status = data.get("status")
        connected = status in _CONNECTED_STATUSES
        return CallResult(
            connected=connected,
            # Gap #1 (module docstring): no conversation capability exists,
            # so a real, connected call still cannot have met an
            # information-gathering objective.
            objective_met=False,
            follow_up_required=True,
            external_reference=external_reference,
            transcript=_NO_CONVERSATION_TRANSCRIPT if connected else f"call status: {status}",
        )


def _transport_error(exc: httpx.HTTPError) -> ProviderError:
    """Wrap a connect/timeout failure so the API layer's LifeOpsError
    handling turns it into a structured error, not an unhandled 500 — the
    same treatment ``voice/elevenlabs.py`` gives a transport failure. The
    message never includes the auth token, so it cannot leak through it."""
    return ProviderError(
        f"Twilio request failed: {exc.__class__.__name__}: {exc}", provider="telephony"
    )


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code >= 400:
        raise ProviderError(
            f"Twilio request failed with HTTP {response.status_code}",
            provider="telephony",
            status_code=response.status_code,
        )
