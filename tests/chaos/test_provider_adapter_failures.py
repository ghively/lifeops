"""Failure/chaos tests, part 2 (BUILD_SPEC section 86): provider adapters
that speak over a real transport. Everything here runs against fakes or a
mocked HTTP transport — no live network call, no live NornicDB — so it
belongs in ``make test-fast``.

Covers scenarios 11 (ElevenLabs timeout), 12 (ElevenLabs partial stream),
and 15 (SIP disconnect, read here as "the provider never picks up" — the
telephony Protocol has no lower-level connection state than that, section
68's ``dial``/``get_status`` pair).
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from lifeops.clock import FrozenClock
from lifeops.config.service import ConfigurationService
from lifeops.core import LifeOpsCore
from lifeops.domain.actions import ActionType
from lifeops.domain.people import Person
from lifeops.domain.service_request import ServiceRequestDraft
from lifeops.domain.tasks import TaskDraft
from lifeops.domain.voice import SynthesisOptions
from lifeops.domain.waiting import WaitingStatus
from lifeops.errors import ProviderError
from lifeops.policy.capabilities import HERMES
from lifeops.repositories.fakes import (
    FakeActionRepository,
    FakeApprovalRepository,
    FakeAuditRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeServiceRequestRepository,
    FakeTaskRepository,
    FakeWaitingRepository,
    FakeWorldRepository,
)
from lifeops.secrets.local_encrypted import InMemorySecretStore
from lifeops.telephony.fake import FakeTelephonyProvider
from lifeops.telephony.service import TelephonyProviderService
from lifeops.voice.elevenlabs import ElevenLabsTTSProvider

PRIMARY = "person_chaos_voice_user"
NOW = "2026-09-01T00:00:00Z"


def _mock_transport(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.elevenlabs.io"
    )


# --- scenario 11: ElevenLabs timeout -------------------------------------------


class TestElevenLabsTimeout:
    """``test_voice.py`` already covers a hard HTTP failure (500); a timeout
    is a distinct transport failure (no response at all, not a bad one) and
    had no coverage."""

    async def test_synthesize_raises_a_provider_error_not_a_bare_timeout(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("simulated timeout", request=request)

        client = _mock_transport(handler)
        provider = ElevenLabsTTSProvider(api_key="k", voice_id="v", client=client)
        with pytest.raises(ProviderError, match="ReadTimeout"):
            await provider.synthesize("hello", SynthesisOptions())
        await provider.aclose()


# --- scenario 12: ElevenLabs partial stream ------------------------------------


class TestElevenLabsPartialStream:
    """A stream that drops mid-transfer (a real network condition, not a
    clean error response) must not be mistaken for a complete answer —
    whatever chunks arrived stay exactly that: partial, and the failure
    still surfaces to the caller as a ``ProviderError``."""

    async def test_a_mid_stream_drop_raises_after_the_chunks_already_yielded(
        self,
    ) -> None:
        async def agen():
            yield b"partial-audio-chunk-1"
            yield b"partial-audio-chunk-2"
            raise httpx.ReadError("simulated mid-stream drop")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=agen())

        client = _mock_transport(handler)
        provider = ElevenLabsTTSProvider(api_key="k", voice_id="v", client=client)

        received: list[bytes] = []
        with pytest.raises(ProviderError, match="ReadError"):
            async for chunk in provider.stream("hello", SynthesisOptions()):
                received.append(chunk)
        await provider.aclose()

        # The chunks that arrived before the drop are exactly what a
        # streaming consumer saw — nothing fabricated, nothing silently
        # completed.
        assert received == [b"partial-audio-chunk-1", b"partial-audio-chunk-2"]


# --- scenario 15: SIP disconnect (the provider never picks up) ----------------


class TestTelephonyNeverConnects:
    """No lower transport (SIP, in BUILD_SPEC's own wording) is modelled
    anywhere in this codebase — the Protocol's connection state is exactly
    ``connected: bool`` on a ``CallResult`` (domain/telephony.py). A
    disconnect therefore *is* ``connected=False``, and section 101 step 8's
    answer to it is a WaitingItem. This is the fast-suite version of
    ``tests/e2e/test_electrician_scenario.py``'s equivalent flow — that one
    needs a live NornicDB and a real MCP subprocess; this proves the same
    orchestration logic (``core.py``'s ``_apply_call_result``) without
    either, so a regression here is caught in ``make test-fast``.
    """

    async def test_a_call_that_never_connects_opens_a_waiting_item(
        self, tmp_path: Path
    ) -> None:
        fake_telephony = FakeTelephonyProvider(connected=False)
        config = ConfigurationService(
            config_dir=tmp_path / "config",
            secret_store=InMemorySecretStore(),
            clock=FrozenClock(),
        )
        # account_sid/auth_token/from_number are required fields on the real
        # Twilio adapter's shape (telephony/twilio.py) — set here so
        # status.missing_required clears, even though this test injects the
        # fake through `factories=` and never reaches the real adapter.
        config.update_provider(
            "telephony",
            {
                "enabled": True,
                "account_sid": "AC" + "0" * 32,
                "auth_token": "test-auth-token",
                "from_number": "+15551234567",
            },
        )
        telephony_service = TelephonyProviderService(
            config=config,
            secret_store=InMemorySecretStore(),
            factories={"telephony": lambda settings, secrets: fake_telephony},
        )

        people = FakePersonRepository()
        await people.upsert(
            Person(
                id=PRIMARY,
                display_name="Chaos Voice User",
                is_primary=True,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        preferences = FakePreferenceRepository()
        world = FakeWorldRepository(preferences=preferences)
        waiting = FakeWaitingRepository()
        core = LifeOpsCore(
            people=people,
            preferences=preferences,
            tasks=FakeTaskRepository(),
            world=world,
            waiting=waiting,
            actions=FakeActionRepository(),
            approvals=FakeApprovalRepository(),
            audit=FakeAuditRepository(),
            service_requests=FakeServiceRequestRepository(),
            telephony=telephony_service,
            clock=FrozenClock(),
        )

        task = await core.create_task(HERMES, TaskDraft(title="Get furnace serviced"))
        request = await core.create_service_request(
            HERMES, ServiceRequestDraft(subject="Furnace tune-up", task_id=task.id)
        )
        action = await core.request_provider_call(
            HERMES,
            service_request_id=request.id,
            provider_entity_id="provider_chaos_hvac",
            objective="schedule_hvac",
            collect=["availability"],
        )
        assert action.type is ActionType.PLACE_PHONE_CALL

        result = await core.execute_action(HERMES, action_id=action.id)
        assert result.status.value == "executed"  # the call itself was placeable
        assert not fake_telephony.calls[0].authority.authorize_charge

        items = await waiting.list_by_status(statuses=[WaitingStatus.WAITING])
        assert len(items) == 1
        assert "furnace" in items[0].subject.lower() or "hear back" in items[0].subject.lower()
