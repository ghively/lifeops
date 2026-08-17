"""Voice domain rules, the ElevenLabs adapter's request shaping, and
VoiceService's provider selection (BUILD_SPEC sections 27-29, phase 5).

The adapter is tested against ``httpx.MockTransport`` — no dependency, no
network, no credential — rather than the live ElevenLabs API, per AGENTS.md's
"never ask for a runtime credential" and "development and CI use fakes".
"""

from __future__ import annotations

import json

import httpx
import pytest

from lifeops.clock import FrozenClock
from lifeops.config.service import ConfigurationService
from lifeops.domain.voice import (
    MAX_SYNTHESIS_TEXT_LENGTH,
    SynthesisOptions,
    VoiceMode,
    validate_synthesis_text,
)
from lifeops.errors import ProviderError, ProviderNotConfiguredError, ValidationError
from lifeops.secrets.local_encrypted import InMemorySecretStore
from lifeops.voice.elevenlabs import ElevenLabsTTSProvider
from lifeops.voice.fake import FAKE_MODELS, FAKE_VOICES, FakeTTSProvider
from lifeops.voice.service import VoiceService


class TestValidateSynthesisText:
    def test_strips_whitespace(self) -> None:
        assert validate_synthesis_text("  hello  ") == "hello"

    def test_empty_text_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_synthesis_text("   ")

    def test_text_over_the_limit_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_synthesis_text("x" * (MAX_SYNTHESIS_TEXT_LENGTH + 1))

    def test_text_at_the_limit_is_accepted(self) -> None:
        text = "x" * MAX_SYNTHESIS_TEXT_LENGTH
        assert validate_synthesis_text(text) == text


class TestFakeTTSProvider:
    async def test_synthesize_returns_deterministic_bytes(self) -> None:
        provider = FakeTTSProvider()
        audio = await provider.synthesize("hello", SynthesisOptions(voice_id="v1"))
        assert b"hello" in audio
        assert b"v1" in audio

    async def test_stream_yields_the_same_content_in_chunks(self) -> None:
        provider = FakeTTSProvider()
        options = SynthesisOptions(voice_id="v1")
        whole = await provider.synthesize("hello world", options)
        chunks = [chunk async for chunk in provider.stream("hello world", options)]
        assert b"".join(chunks) == whole
        assert len(chunks) > 1

    async def test_list_voices_and_models_are_fixed(self) -> None:
        provider = FakeTTSProvider()
        assert await provider.list_voices() == FAKE_VOICES
        assert await provider.list_models() == FAKE_MODELS

    async def test_health_reflects_the_configured_flag(self) -> None:
        assert (await FakeTTSProvider(healthy=True).health())[0] is True
        assert (await FakeTTSProvider(healthy=False).health())[0] is False


def _mock_transport(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.elevenlabs.io"
    )


class TestElevenLabsTTSProvider:
    async def test_synthesize_posts_text_and_voice_settings(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["headers"] = request.headers
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, content=b"AUDIO-BYTES")

        client = _mock_transport(handler)
        provider = ElevenLabsTTSProvider(
            api_key="secret-key", voice_id="voice-1", model_id="model-1", client=client
        )
        audio = await provider.synthesize("hello", SynthesisOptions())

        assert audio == b"AUDIO-BYTES"
        assert "/v1/text-to-speech/voice-1" in captured["url"]
        assert captured["headers"]["xi-api-key"] == "secret-key"
        assert captured["body"]["text"] == "hello"
        assert captured["body"]["model_id"] == "model-1"
        assert captured["body"]["voice_settings"]["stability"] == 0.5
        await provider.aclose()

    async def test_options_override_the_stored_defaults(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            captured["params"] = dict(request.url.params)
            return httpx.Response(200, content=b"AUDIO")

        client = _mock_transport(handler)
        provider = ElevenLabsTTSProvider(
            api_key="k", voice_id="default-voice", stability=0.5, client=client
        )
        await provider.synthesize(
            "hi",
            SynthesisOptions(
                voice_id="override-voice", stability=0.9, output_format="pcm_16000"
            ),
        )

        assert captured["body"]["voice_settings"]["stability"] == 0.9
        assert captured["params"]["output_format"] == "pcm_16000"
        await provider.aclose()

    async def test_synthesize_without_any_voice_raises_provider_error(self) -> None:
        client = _mock_transport(lambda request: httpx.Response(200, content=b""))
        provider = ElevenLabsTTSProvider(api_key="k", client=client)
        with pytest.raises(ProviderError):
            await provider.synthesize("hi", SynthesisOptions())
        await provider.aclose()

    async def test_stream_yields_chunks_from_the_response_body(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"chunk-one-chunk-two")

        client = _mock_transport(handler)
        provider = ElevenLabsTTSProvider(api_key="k", voice_id="v1", client=client)
        chunks = [chunk async for chunk in provider.stream("hi", SynthesisOptions())]
        assert b"".join(chunks) == b"chunk-one-chunk-two"
        await provider.aclose()

    async def test_list_voices_parses_the_provider_response(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/voices"
            return httpx.Response(
                200,
                json={
                    "voices": [
                        {"voice_id": "v1", "name": "Aria", "category": "premade"},
                        {"voice_id": "v2", "name": "Bram"},
                    ]
                },
            )

        client = _mock_transport(handler)
        provider = ElevenLabsTTSProvider(api_key="k", client=client)
        voices = await provider.list_voices()
        assert [v.id for v in voices] == ["v1", "v2"]
        assert voices[0].category == "premade"
        await provider.aclose()

    async def test_list_models_parses_the_provider_response(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/models"
            return httpx.Response(
                200,
                json=[
                    {
                        "model_id": "m1",
                        "name": "Flash",
                        "can_do_text_to_speech_streaming": True,
                    },
                    {"model_id": "m2", "name": "Not TTS", "can_do_text_to_speech": False},
                ],
            )

        client = _mock_transport(handler)
        provider = ElevenLabsTTSProvider(api_key="k", client=client)
        models = await provider.list_models()
        assert [m.id for m in models] == ["m1"]
        await provider.aclose()

    async def test_health_reports_ok_on_200(self) -> None:
        client = _mock_transport(lambda request: httpx.Response(200, json={"ok": True}))
        provider = ElevenLabsTTSProvider(api_key="k", client=client)
        healthy, message = await provider.health()
        assert healthy is True
        await provider.aclose()

    async def test_health_reports_bad_key_on_401(self) -> None:
        client = _mock_transport(lambda request: httpx.Response(401))
        provider = ElevenLabsTTSProvider(api_key="wrong", client=client)
        healthy, message = await provider.health()
        assert healthy is False
        assert "API key" in message
        await provider.aclose()

    async def test_failed_request_raises_provider_error(self) -> None:
        client = _mock_transport(lambda request: httpx.Response(500))
        provider = ElevenLabsTTSProvider(api_key="k", voice_id="v1", client=client)
        with pytest.raises(ProviderError):
            await provider.synthesize("hi", SynthesisOptions())
        await provider.aclose()


class TestVoiceService:
    def _service(self, *, config: ConfigurationService | None = None) -> VoiceService:
        secrets = InMemorySecretStore()
        config = config or ConfigurationService(
            config_dir=self._tmp, secret_store=secrets, clock=FrozenClock()
        )
        return VoiceService(
            config=config,
            secret_store=secrets,
            factories={"elevenlabs": lambda _s, _sec: FakeTTSProvider()},
        )

    @pytest.fixture(autouse=True)
    def _tmp_dir(self, tmp_path) -> None:
        self._tmp = tmp_path / "config"

    def _configured_service(self) -> VoiceService:
        secrets = InMemorySecretStore()
        config = ConfigurationService(
            config_dir=self._tmp, secret_store=secrets, clock=FrozenClock()
        )
        config.update_provider(
            "elevenlabs", {"api_key": "key", "voice_id": "v1", "enabled": True}
        )
        return VoiceService(
            config=config,
            secret_store=secrets,
            factories={"elevenlabs": lambda _s, _sec: FakeTTSProvider()},
        )

    async def test_nothing_configured_raises_not_configured(self) -> None:
        service = self._service()
        with pytest.raises(ProviderNotConfiguredError):
            await service.health()
        with pytest.raises(ProviderNotConfiguredError):
            await service.list_voices()
        with pytest.raises(ProviderNotConfiguredError):
            await service.synthesize("hi")

    async def test_configured_but_disabled_still_raises_not_configured(self) -> None:
        secrets = InMemorySecretStore()
        config = ConfigurationService(
            config_dir=self._tmp, secret_store=secrets, clock=FrozenClock()
        )
        # Complete but never turned on.
        config.update_provider("elevenlabs", {"api_key": "key", "voice_id": "v1"})
        service = VoiceService(
            config=config,
            secret_store=secrets,
            factories={"elevenlabs": lambda _s, _sec: FakeTTSProvider()},
        )
        with pytest.raises(ProviderNotConfiguredError):
            await service.health()

    async def test_health_records_a_health_report_once_enabled(self) -> None:
        service = self._configured_service()
        provider_id, report = await service.health()
        assert provider_id == "elevenlabs"
        assert report.healthy is True

    async def test_list_voices_and_models_delegate_to_the_provider(self) -> None:
        service = self._configured_service()
        assert await service.list_voices() == FAKE_VOICES
        assert await service.list_models() == FAKE_MODELS

    async def test_synthesize_validates_text_before_building_a_provider(self) -> None:
        service = self._service()  # nothing configured
        with pytest.raises(ValidationError):
            await service.synthesize("   ")

    async def test_synthesize_returns_provider_audio(self) -> None:
        service = self._configured_service()
        audio = await service.synthesize("hello")
        assert b"hello" in audio

    async def test_stream_raises_synchronously_when_not_configured(self) -> None:
        service = self._service()
        with pytest.raises(ProviderNotConfiguredError):
            service.stream("hello")

    async def test_stream_yields_audio_once_configured(self) -> None:
        service = self._configured_service()
        chunks = [chunk async for chunk in service.stream("hello")]
        assert b"".join(chunks)


class TestVoiceModeSetting:
    def test_defaults_to_quick_cloud(self, config_service: ConfigurationService) -> None:
        assert config_service.get_system().voice_mode is VoiceMode.QUICK_CLOUD

    def test_accepts_a_valid_mode(self, config_service: ConfigurationService) -> None:
        updated = config_service.update_system({"voice_mode": "hybrid"})
        assert updated.voice_mode is VoiceMode.HYBRID

    def test_rejects_an_invalid_mode(self, config_service: ConfigurationService) -> None:
        with pytest.raises(ValidationError):
            config_service.update_system({"voice_mode": "telepathic"})
