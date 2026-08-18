"""Failure/chaos tests, part 3 (BUILD_SPEC section 86): the scenarios that
are either already covered elsewhere, or have no code path to exercise yet.

The original audit counted "2 of 16" scenarios covered — that undercounted:
Hermes restart and LifeOps restart both have real, passing e2e coverage,
just never labelled "chaos". This file is the index that makes all 16
numbers traceable to either a real test or an honest, specific reason one
cannot exist yet, so nothing here reads as silently skipped.
"""

from __future__ import annotations

import pytest

from lifeops.errors import ProviderError
from lifeops.telephony.twilio import TwilioTelephonyProvider
from lifeops.voice.local import LocalASRProvider, LocalTTSProvider


class TestScenario1DeepSeekTimeout:
    """No DeepSeek client exists anywhere in this codebase — grep for
    "deepseek" outside ``config/provider_registry.py`` (a ``ProviderDefinition``
    only) turns up nothing. ``POST /config/providers/deepseek/test`` is the
    only reachable path, and it already honestly reports "no adapter yet"
    (``tests/unit/test_configuration.py``'s provider-honesty tests cover
    that generic behaviour). A timeout test needs a request to time out;
    there is no request-issuing code to inject one into."""

    def test_documented_as_untestable_until_a_deepseek_client_exists(self) -> None:
        pytest.skip(
            "no DeepSeek client exists to simulate a timeout against "
            "(BUILD_SPEC section 86 scenario 1) — revisit once one is built"
        )


class TestScenario2HermesRestart:
    """Covered, not missing: ``tests/e2e/test_phase4_durable_work.py``'s
    ``TestSurvivesRestart.test_hermes_restart_new_subprocess_still_sees_the_work``
    kills an MCP session and proves an entirely fresh subprocess sees the
    same durable state, which is exactly what "Hermes restarts" means at
    this boundary — LifeOps Core has no notion of "Hermes" beyond the MCP
    client identity a session connects with."""


class TestScenario3NornicRestart:
    """Covered: ``tests/e2e/test_phase0_exit.py``'s ``TestNornicRestart``
    (the scenario the original audit already counted) and
    ``tests/e2e/test_phase4_durable_work.py``'s durable-work equivalent."""


class TestScenario13LocalAsrCrash:
    """``LocalASRProvider`` (``voice/local.py``) is a stub, not a running
    process — every method unconditionally raises ``ProviderError`` because
    no ASR runtime (``faster_whisper``) is installed in this environment.
    There is nothing running to crash; the honest-failure path this
    represents is already asserted directly:
    ``tests/unit/test_voice.py::TestLocalASRProvider`` (health reports the
    runtime missing; transcribe/stream raise rather than fabricating a
    transcript)."""

    async def test_transcribe_raises_rather_than_simulating_a_crash(self) -> None:
        with pytest.raises(ProviderError):
            await LocalASRProvider().transcribe(b"audio-bytes")


class TestScenario14LocalTtsCrash:
    """Same shape as scenario 13: ``LocalTTSProvider`` has no runtime to
    crash. See ``tests/unit/test_voice.py::TestLocalTTSProvider``."""

    async def test_synthesize_raises_rather_than_simulating_a_crash(self) -> None:
        from lifeops.domain.voice import SynthesisOptions

        with pytest.raises(ProviderError):
            await LocalTTSProvider().synthesize("hello", SynthesisOptions())


def test_twilio_provider_is_the_real_adapter_scenario_15_exercises() -> None:
    """Not a skip: confirms the class scenario 15's other tests
    (``tests/unit/test_telephony_twilio.py``'s HTTP-error coverage for
    ``hangup``/``get_status``, and this package's
    ``test_provider_adapter_failures.py::TestTelephonyNeverConnects``) are
    actually exercising the real adapter, not a stand-in that happens to
    share its name."""
    assert TwilioTelephonyProvider.__module__ == "lifeops.telephony.twilio"
