"""Voice domain rules, the ElevenLabs adapter's request shaping, the local
adapters' honest runtime detection, and VoiceService's mode-aware provider
selection (BUILD_SPEC sections 27-30, 95).

The ElevenLabs adapter is tested against ``httpx.MockTransport`` — no
dependency, no network, no credential — rather than the live ElevenLabs API,
per AGENTS.md's "never ask for a runtime credential" and "development and CI
use fakes". The local adapters need no such transport: nothing in this
environment installs faster-whisper or a local TTS runtime (BUILD_SPEC
section 105), so their real behaviour *is* "runtime not installed" — the
tests below assert on that honest report directly.
"""

from __future__ import annotations

import importlib.machinery
import json
import sys
import types
from typing import Any

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
from lifeops.voice.fake import (
    FAKE_MODELS,
    FAKE_VOICES,
    FakeASRProvider,
    FakeLocalTTSProvider,
    FakeTTSProvider,
)
from lifeops.voice.local import LocalASRProvider, LocalTTSProvider
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


class TestFakeASRProvider:
    async def test_transcribe_decodes_utf8_input_deterministically(self) -> None:
        provider = FakeASRProvider()
        result = await provider.transcribe(b"hello world")
        assert result.text == "hello world"
        assert result.language == "en"

    async def test_transcribe_falls_back_to_a_byte_count_for_non_utf8(self) -> None:
        provider = FakeASRProvider()
        result = await provider.transcribe(b"\xff\xfe\x00")
        assert "3 bytes" in result.text

    async def test_stream_yields_one_result_per_chunk(self) -> None:
        provider = FakeASRProvider()

        async def chunks():
            yield b"one"
            yield b"two"

        results = [r async for r in provider.stream(chunks())]
        assert [r.text for r in results] == ["one", "two"]

    async def test_health_reflects_the_configured_flag(self) -> None:
        assert (await FakeASRProvider(healthy=True).health())[0] is True
        assert (await FakeASRProvider(healthy=False).health())[0] is False

    async def test_load_and_unload_track_the_healthy_flag(self) -> None:
        healthy = FakeASRProvider(healthy=True)
        assert (await healthy.load())[0] is True
        assert healthy.loaded is True
        assert (await healthy.unload())[0] is True
        assert healthy.loaded is False

        unhealthy = FakeASRProvider(healthy=False)
        assert (await unhealthy.load())[0] is False
        assert unhealthy.loaded is False


class TestFakeLocalTTSProvider:
    async def test_synthesize_and_stream_round_trip(self) -> None:
        provider = FakeLocalTTSProvider()
        options = SynthesisOptions(voice_id="v1")
        whole = await provider.synthesize("hi", options)
        chunks = [c async for c in provider.stream("hi", options)]
        assert b"".join(chunks) == whole
        assert b"hi" in whole

    async def test_list_voices_and_models_are_fixed(self) -> None:
        provider = FakeLocalTTSProvider()
        voices = await provider.list_voices()
        models = await provider.list_models()
        assert voices and models

    async def test_load_and_unload_track_the_healthy_flag(self) -> None:
        provider = FakeLocalTTSProvider(healthy=True)
        assert (await provider.load())[0] is True
        assert provider.loaded is True
        assert (await provider.unload())[0] is True
        assert provider.loaded is False


class TestLocalASRProvider:
    """No local ASR runtime is installed in this environment (BUILD_SPEC
    section 105), so these assert the real, honest "not installed" path —
    not a mock standing in for one."""

    async def test_health_reports_the_runtime_is_missing(self) -> None:
        healthy, message = await LocalASRProvider().health()
        assert healthy is False
        assert "faster_whisper" in message

    async def test_transcribe_raises_rather_than_fabricating_a_transcript(self) -> None:
        with pytest.raises(ProviderError):
            await LocalASRProvider().transcribe(b"audio-bytes")

    async def test_stream_raises_on_first_iteration_not_on_construction(self) -> None:
        provider = LocalASRProvider()

        async def chunks():
            yield b"audio"

        gen = provider.stream(chunks())  # not awaited — must not raise yet
        with pytest.raises(ProviderError):
            await gen.__anext__()

    async def test_load_reports_unhealthy_and_leaves_it_unloaded(self) -> None:
        provider = LocalASRProvider()
        loaded, _message = await provider.load()
        assert loaded is False
        assert provider.is_loaded is False

    async def test_unload_always_succeeds(self) -> None:
        provider = LocalASRProvider()
        ok, message = await provider.unload()
        assert ok is True
        assert provider.is_loaded is False


class TestLocalTTSProvider:
    async def test_health_reports_no_runtime_wired_up(self) -> None:
        healthy, message = await LocalTTSProvider().health()
        assert healthy is False
        assert "runtime" in message

    async def test_synthesize_raises_rather_than_fabricating_audio(self) -> None:
        with pytest.raises(ProviderError):
            await LocalTTSProvider().synthesize("hi", SynthesisOptions())

    async def test_stream_raises_on_first_iteration_not_on_construction(self) -> None:
        provider = LocalTTSProvider()
        gen = provider.stream("hi", SynthesisOptions())  # not awaited — must not raise yet
        with pytest.raises(ProviderError):
            await gen.__anext__()

    async def test_list_voices_and_models_are_empty_not_fabricated(self) -> None:
        provider = LocalTTSProvider()
        assert await provider.list_voices() == []
        assert await provider.list_models() == []


def _fake_module(name: str) -> types.ModuleType:
    """A ``sys.modules``-ready fake with a real ``__spec__`` set — without
    one, ``importlib.util.find_spec`` raises ``ValueError`` on a bare
    ``types.ModuleType`` and ``detect_runtime`` would (correctly, but not
    for the reason these tests want) report it as not installed."""
    module = types.ModuleType(name)
    module.__spec__ = importlib.machinery.ModuleSpec(name, loader=None)
    return module


def _install_fake_faster_whisper(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, str | None]]:
    """Fakes the faster_whisper package via sys.modules so
    LocalASRProvider's real code path — not just its "not installed"
    honesty check — gets exercised without the actual multi-gigabyte
    package or a GPU. Returns the (audio, language) args each fake
    ``transcribe`` call was made with."""
    calls: list[tuple[Any, str | None]] = []

    class _FakeSegment:
        def __init__(self, text: str) -> None:
            self.text = text

    class _FakeInfo:
        def __init__(self, language: str) -> None:
            self.language = language

    class _FakeWhisperModel:
        def __init__(self, model_size_or_path: str, device: str = "auto", **_: Any) -> None:
            self.model_size_or_path = model_size_or_path
            self.device = device

        def transcribe(self, audio: Any, language: str | None = None, **_: Any) -> Any:
            calls.append((audio, language))
            return [_FakeSegment("hello "), _FakeSegment("world")], _FakeInfo(language or "en")

    fake_module = _fake_module("faster_whisper")
    fake_module.WhisperModel = _FakeWhisperModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)

    import lifeops.voice.local as local_module

    local_module._ASR_MODEL_CACHE.clear()
    return calls


class _FakeKokoroPipeline:
    """Records each call's (text, voice, speed) and yields two short,
    deterministic "audio" chunks (plain lists, not real numpy arrays — the
    fake numpy/soundfile modules below only need to handle what this
    produces)."""

    instances: list[_FakeKokoroPipeline] = []

    def __init__(self, lang_code: str, device: str | None = None, **_: Any) -> None:
        self.lang_code = lang_code
        self.device = device
        self.calls: list[tuple[str, str | None, float]] = []
        _FakeKokoroPipeline.instances.append(self)

    def __call__(self, text: str, voice: str | None = None, speed: float = 1.0) -> Any:
        self.calls.append((text, voice, speed))
        yield ("gs1", "ps1", [0.0, 0.0, 0.0, 0.0])
        yield ("gs2", "ps2", [1.0, 1.0, 1.0, 1.0])


def _install_fake_kokoro(monkeypatch: pytest.MonkeyPatch) -> list[_FakeKokoroPipeline]:
    """Fakes kokoro (``KPipeline``) plus its numpy/soundfile dependencies via
    sys.modules, for the same reason as ``_install_fake_faster_whisper``.
    Returns the list of constructed fake pipelines so a test can inspect
    what they were called with."""
    _FakeKokoroPipeline.instances = []

    fake_kokoro = _fake_module("kokoro")
    fake_kokoro.KPipeline = _FakeKokoroPipeline  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "kokoro", fake_kokoro)

    fake_numpy = _fake_module("numpy")
    fake_numpy.concatenate = lambda arrays: [v for arr in arrays for v in arr]  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "numpy", fake_numpy)

    def _fake_write(buffer: Any, data: Any, samplerate: int, format: str = "WAV") -> None:
        buffer.write(f"WAV:{len(data)}:{samplerate}".encode())

    fake_soundfile = _fake_module("soundfile")
    fake_soundfile.write = _fake_write  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "soundfile", fake_soundfile)

    import lifeops.voice.local as local_module

    local_module._TTS_PIPELINE_CACHE.clear()
    return _FakeKokoroPipeline.instances


class TestLocalASRProviderWithRuntimeInstalled:
    """The other TestLocalASRProvider class covers this sandbox's real,
    honest "faster-whisper is not installed" path. These simulate it being
    installed, so the real transcribe/load/health code exists and is
    actually exercised, not just written and trusted."""

    async def test_health_reports_ready_once_a_model_is_selected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake_faster_whisper(monkeypatch)
        healthy, message = await LocalASRProvider(model="large-v3-turbo").health()
        assert healthy is True
        assert "large-v3-turbo" in message

    async def test_health_still_flags_a_missing_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake_faster_whisper(monkeypatch)
        healthy, message = await LocalASRProvider().health()
        assert healthy is False
        assert "no model is selected" in message

    async def test_transcribe_calls_the_model_and_maps_segments_to_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = _install_fake_faster_whisper(monkeypatch)
        provider = LocalASRProvider(model="large-v3-turbo", language="en")
        result = await provider.transcribe(b"raw-audio-bytes")
        assert result.text == "hello world"
        assert result.language == "en"
        assert calls[0][1] == "en"

    async def test_load_populates_the_cache_and_unload_clears_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake_faster_whisper(monkeypatch)
        import lifeops.voice.local as local_module

        provider = LocalASRProvider(model="large-v3-turbo", device="cuda:0")
        loaded, _ = await provider.load()
        assert loaded is True
        assert provider.is_loaded is True
        assert ("large-v3-turbo", "cuda:0") in local_module._ASR_MODEL_CACHE

        unloaded, _ = await provider.unload()
        assert unloaded is True
        assert provider.is_loaded is False
        assert ("large-v3-turbo", "cuda:0") not in local_module._ASR_MODEL_CACHE

    async def test_repeated_construction_reuses_the_cached_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake_faster_whisper(monkeypatch)
        import lifeops.voice.local as local_module

        await LocalASRProvider(model="large-v3-turbo", device="cuda:0").transcribe(b"a")
        cached = local_module._ASR_MODEL_CACHE[("large-v3-turbo", "cuda:0")]
        await LocalASRProvider(model="large-v3-turbo", device="cuda:0").transcribe(b"b")
        assert local_module._ASR_MODEL_CACHE[("large-v3-turbo", "cuda:0")] is cached

    async def test_stream_collects_the_whole_utterance_into_one_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake_faster_whisper(monkeypatch)
        provider = LocalASRProvider(model="large-v3-turbo")

        async def chunks() -> Any:
            yield b"chunk-one-"
            yield b"chunk-two"

        results = [r async for r in provider.stream(chunks())]
        assert len(results) == 1
        assert results[0].text == "hello world"


class TestLocalTTSProviderWithRuntimeInstalled:
    """Kokoro-installed counterpart to TestLocalTTSProvider, same rationale
    as TestLocalASRProviderWithRuntimeInstalled above."""

    async def test_health_reports_ready_once_a_model_is_selected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake_kokoro(monkeypatch)
        healthy, _ = await LocalTTSProvider(model="kokoro").health()
        assert healthy is True

    async def test_synthesize_concatenates_segments_into_one_wav(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake_kokoro(monkeypatch)
        provider = LocalTTSProvider(model="kokoro", voice="af_heart")
        audio = await provider.synthesize("hello there", SynthesisOptions())
        assert audio == b"WAV:8:24000"  # two 4-sample fake chunks, concatenated

    async def test_synthesize_prefers_the_per_call_voice_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        instances = _install_fake_kokoro(monkeypatch)
        provider = LocalTTSProvider(model="kokoro", voice="af_heart")
        await provider.synthesize("hi", SynthesisOptions(voice_id="am_michael"))
        assert instances[0].calls[-1] == ("hi", "am_michael", 1.0)

    async def test_stream_yields_one_chunk_per_kokoro_segment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake_kokoro(monkeypatch)
        provider = LocalTTSProvider(model="kokoro")
        chunks = [c async for c in provider.stream("hello there", SynthesisOptions())]
        assert chunks == [b"WAV:4:24000", b"WAV:4:24000"]

    async def test_load_populates_the_cache_and_unload_clears_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake_kokoro(monkeypatch)
        import lifeops.voice.local as local_module

        provider = LocalTTSProvider(model="kokoro", device="cuda:0")
        loaded, _ = await provider.load()
        assert loaded is True
        assert ("a", "cuda") in local_module._TTS_PIPELINE_CACHE

        unloaded, _ = await provider.unload()
        assert unloaded is True
        assert ("a", "cuda") not in local_module._TTS_PIPELINE_CACHE

    async def test_list_voices_and_models_report_real_entries_once_installed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake_kokoro(monkeypatch)
        provider = LocalTTSProvider(model="kokoro")
        voices = await provider.list_voices()
        models = await provider.list_models()
        assert any(v.id == "af_heart" for v in voices)
        assert len(models) == 1
        assert models[0].id == "kokoro"
        assert models[0].supports_streaming is True


class TestVoiceServiceModeSelection:
    """BUILD_SPEC section 29: which ASR/TTS provider each voice mode
    selects, and that switching modes is a LifeOps setting no caller has to
    know about."""

    @pytest.fixture(autouse=True)
    def _tmp_dir(self, tmp_path) -> None:
        self._tmp = tmp_path / "config"

    def _service(self, *, mode: str | None = None) -> tuple[ConfigurationService, VoiceService]:
        secrets = InMemorySecretStore()
        config = ConfigurationService(
            config_dir=self._tmp, secret_store=secrets, clock=FrozenClock()
        )
        if mode is not None:
            config.update_system({"voice_mode": mode})
        config.update_provider(
            "elevenlabs", {"api_key": "key", "voice_id": "v1", "enabled": True}
        )
        config.update_provider("local_asr", {"model": "distil-large-v3", "enabled": True})
        config.update_provider("local_tts", {"model": "kokoro", "enabled": True})
        service = VoiceService(
            config=config,
            secret_store=secrets,
            factories={
                "elevenlabs": lambda _s, _sec: FakeTTSProvider(),
                "local_tts": lambda _s, _sec: FakeLocalTTSProvider(),
            },
            asr_factories={"local_asr": lambda _s, _sec: FakeASRProvider()},
        )
        return config, service

    async def test_quick_cloud_uses_elevenlabs_for_tts(self) -> None:
        _, service = self._service(mode="quick_cloud")
        provider_id, _ = await service.health()
        assert provider_id == "elevenlabs"

    async def test_quick_cloud_asr_is_configurable_and_picks_local_asr(self) -> None:
        # Only local_asr exists today, so "configurable" resolves to it —
        # the point is that nothing pins it, unlike hybrid/local below.
        _, service = self._service(mode="quick_cloud")
        text = await service.transcribe(b"hi")
        assert text.text == "hi"

    async def test_hybrid_pins_tts_to_elevenlabs_and_asr_to_local(self) -> None:
        _, service = self._service(mode="hybrid")
        tts_id, _ = await service.health()
        assert tts_id == "elevenlabs"
        result = await service.transcribe(b"hybrid")
        assert result.text == "hybrid"

    async def test_local_mode_pins_both_tts_and_asr_to_local(self) -> None:
        _, service = self._service(mode="local")
        audio = await service.synthesize("hi")
        assert b"FAKE-LOCAL-AUDIO" in audio
        result = await service.transcribe(b"local")
        assert result.text == "local"

    async def test_local_mode_raises_when_local_tts_is_not_ready(self) -> None:
        secrets = InMemorySecretStore()
        config = ConfigurationService(
            config_dir=self._tmp, secret_store=secrets, clock=FrozenClock()
        )
        config.update_system({"voice_mode": "local"})
        # local_tts left disabled — Local mode may not silently fall back to
        # ElevenLabs; that would defeat the point of choosing Local mode.
        service = VoiceService(
            config=config,
            secret_store=secrets,
            factories={
                "elevenlabs": lambda _s, _sec: FakeTTSProvider(),
                "local_tts": lambda _s, _sec: FakeLocalTTSProvider(),
            },
        )
        with pytest.raises(ProviderNotConfiguredError):
            await service.synthesize("hi")

    async def test_switching_modes_changes_selection_without_new_factories(self) -> None:
        config, service = self._service(mode="quick_cloud")
        first, _ = await service.health()
        config.update_system({"voice_mode": "local"})
        second, _ = await service.health()
        assert first == "elevenlabs"
        assert second == "local_tts"


class TestVoiceServiceHealthForBypassesMode:
    @pytest.fixture(autouse=True)
    def _tmp_dir(self, tmp_path) -> None:
        self._tmp = tmp_path / "config"

    async def test_testing_local_tts_card_tests_local_tts_even_in_quick_cloud_mode(
        self,
    ) -> None:
        secrets = InMemorySecretStore()
        config = ConfigurationService(
            config_dir=self._tmp, secret_store=secrets, clock=FrozenClock()
        )
        # Default mode is quick_cloud, which pins TTS to elevenlabs.
        config.update_provider("local_tts", {"model": "kokoro", "enabled": True})
        service = VoiceService(
            config=config,
            secret_store=secrets,
            factories={"local_tts": lambda _s, _sec: FakeLocalTTSProvider()},
        )
        provider_id, report = await service.health_for("local_tts")
        assert provider_id == "local_tts"
        assert report.healthy is True
        assert "latency_ms" in report.details

    async def test_testing_an_unconfigured_provider_raises(self) -> None:
        secrets = InMemorySecretStore()
        config = ConfigurationService(
            config_dir=self._tmp, secret_store=secrets, clock=FrozenClock()
        )
        service = VoiceService(
            config=config,
            secret_store=secrets,
            factories={"local_tts": lambda _s, _sec: FakeLocalTTSProvider()},
        )
        with pytest.raises(ProviderNotConfiguredError):
            await service.health_for("local_tts")


class TestVoiceServiceModeStatus:
    @pytest.fixture(autouse=True)
    def _tmp_dir(self, tmp_path) -> None:
        self._tmp = tmp_path / "config"

    def _service(self) -> tuple[ConfigurationService, VoiceService]:
        secrets = InMemorySecretStore()
        config = ConfigurationService(
            config_dir=self._tmp, secret_store=secrets, clock=FrozenClock()
        )
        config.update_provider(
            "elevenlabs", {"api_key": "key", "voice_id": "v1", "enabled": True}
        )
        config.update_provider("local_tts", {"model": "kokoro", "enabled": True})
        config.update_provider("local_asr", {"model": "distil-large-v3", "enabled": True})
        service = VoiceService(
            config=config,
            secret_store=secrets,
            factories={
                "elevenlabs": lambda _s, _sec: FakeTTSProvider(),
                "local_tts": lambda _s, _sec: FakeLocalTTSProvider(),
            },
            asr_factories={"local_asr": lambda _s, _sec: FakeASRProvider()},
        )
        return config, service

    def test_quick_cloud_status(self) -> None:
        config, service = self._service()
        status = service.mode_status()
        assert status.mode is VoiceMode.QUICK_CLOUD
        assert status.tts_active == "elevenlabs"
        assert status.tts_fallback == "local_tts"
        assert status.asr_active == "local_asr"
        assert status.asr_fallback is None

    def test_local_status(self) -> None:
        config, service = self._service()
        config.update_system({"voice_mode": "local"})
        status = service.mode_status()
        assert status.mode is VoiceMode.LOCAL
        assert status.tts_active == "local_tts"
        assert status.tts_fallback == "elevenlabs"
        assert status.asr_active == "local_asr"


class TestVoiceServiceLoadUnload:
    @pytest.fixture(autouse=True)
    def _tmp_dir(self, tmp_path) -> None:
        self._tmp = tmp_path / "config"

    def _service(self) -> VoiceService:
        secrets = InMemorySecretStore()
        config = ConfigurationService(
            config_dir=self._tmp, secret_store=secrets, clock=FrozenClock()
        )
        config.update_provider("local_tts", {"model": "kokoro", "enabled": True})
        return VoiceService(
            config=config,
            secret_store=secrets,
            factories={"local_tts": lambda _s, _sec: FakeLocalTTSProvider()},
        )

    async def test_load_then_unload_a_local_provider(self) -> None:
        service = self._service()
        loaded, _ = await service.load("local_tts")
        assert loaded is True
        unloaded, _ = await service.unload("local_tts")
        assert unloaded is True

    async def test_load_an_unready_provider_raises(self) -> None:
        secrets = InMemorySecretStore()
        config = ConfigurationService(
            config_dir=self._tmp, secret_store=secrets, clock=FrozenClock()
        )
        service = VoiceService(
            config=config,
            secret_store=secrets,
            factories={"local_tts": lambda _s, _sec: FakeLocalTTSProvider()},
        )
        with pytest.raises(ProviderNotConfiguredError):
            await service.load("local_tts")

    async def test_load_a_provider_without_a_lifecycle_raises(self) -> None:
        secrets = InMemorySecretStore()
        config = ConfigurationService(
            config_dir=self._tmp, secret_store=secrets, clock=FrozenClock()
        )
        config.update_provider(
            "elevenlabs", {"api_key": "key", "voice_id": "v1", "enabled": True}
        )
        service = VoiceService(
            config=config,
            secret_store=secrets,
            factories={"elevenlabs": lambda _s, _sec: FakeTTSProvider()},
        )
        with pytest.raises(ProviderNotConfiguredError):
            await service.load("elevenlabs")
