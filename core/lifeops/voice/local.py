"""LocalTTSProvider and LocalASRProvider (BUILD_SPEC sections 28, 30, 95).

Real adapters, not detection-only stubs: ``LocalASRProvider`` drives
``faster-whisper`` and ``LocalTTSProvider`` drives Kokoro (BUILD_SPEC section
30's "fallback/reference" TTS candidate) via the ``kokoro`` PyPI package's
``KPipeline``. Neither package is installed by default — they live in the
``voice-local`` optional dependency group (``pyproject.toml``), with a
written justification there per AGENTS.md, because a multi-gigabyte GPU
runtime is not something this repository installs speculatively (BUILD_SPEC
section 105). Every import of ``faster_whisper``/``kokoro``/``soundfile`` is
lazy, inside the method that needs it, so nothing here requires the extra to
even import this module.

``health()`` still detects whether a runtime is importable and reports the
honest result — "not installed" when it genuinely is not. Once it *is*
installed, the adapters do real work: ``transcribe``/``synthesize``/
``stream`` load real weights and call the real library, rather than raising
the placeholder message every previous version of this module used
unconditionally. This module cannot be exercised against a real GPU in CI or
in the sandbox that wrote it — ``tests/unit/test_voice.py`` covers the
"not installed" path directly (still true here) and the "installed" code
paths against ``sys.modules``-injected fakes standing in for the real
libraries, the same way ``ElevenLabsTTSProvider`` is tested against
``httpx.MockTransport`` instead of the live API.

Model/device/voice selection are Console fields (``config/provider_registry.py``);
this module never downloads anything except in response to an explicit
``load()`` call or the first real ``transcribe``/``synthesize`` — same
"disabled until a human configures and enables it" shape as every other
provider (AGENTS.md: never ask for a runtime credential).
"""

from __future__ import annotations

import asyncio
import io
import threading
from collections.abc import AsyncIterator
from typing import Any

from lifeops.domain.voice import SynthesisOptions, TranscriptionResult, TTSModel, Voice
from lifeops.errors import ProviderError
from lifeops.runtime import detect_runtime

# BUILD_SPEC section 30's ASR candidates. faster-whisper is a real, commonly
# installed package (module name faster_whisper) so detecting it is useful;
# the NVIDIA streaming candidate has no fixed package name to check for.
ASR_RUNTIME_CANDIDATES: tuple[str, ...] = ("faster_whisper",)

# Kokoro (module name ``kokoro``) is the one BUILD_SPEC section 30 TTS
# candidate with a real adapter below. Qwen3-TTS and Chatterbox Turbo stay
# unlisted rather than guessed at — BUILD_SPEC section 30 says "keep
# candidates configurable, don't gate completion on picking a winner", not
# "wire up every candidate before shipping one."
TTS_RUNTIME_CANDIDATES: tuple[str, ...] = ("kokoro",)

_DEFAULT_KOKORO_VOICE = "af_heart"
_KOKORO_SAMPLE_RATE_HZ = 24000
# A curated subset of Kokoro's voice packs, not the full catalog — see
# config/provider_registry.py's LOCAL_TTS.voice field for the same list
# surfaced to the Console.
_KNOWN_KOKORO_VOICES: tuple[str, ...] = ("af_heart", "af_bella", "am_michael", "bf_emma")

# In-process caches so VoiceService's per-call "build fresh from stored
# settings" (voice/service.py) does not reload multi-gigabyte weights on
# every single transcribe/synthesize call — a new LocalASRProvider/
# LocalTTSProvider instance is constructed per request, but the underlying
# model/pipeline these methods build is expensive and stays resident here.
# An explicit load()/unload() (BUILD_SPEC section 95's Console buttons)
# populates/evicts these directly; transcribe/synthesize populate them
# lazily on first use otherwise.
_ASR_MODEL_CACHE: dict[tuple[str, str], Any] = {}
_ASR_CACHE_LOCK = threading.Lock()
_TTS_PIPELINE_CACHE: dict[tuple[str, str | None], Any] = {}
_TTS_CACHE_LOCK = threading.Lock()


def _to_numpy_audio(audio: Any) -> Any:
    """Kokoro's yielded audio is a torch.Tensor on some versions and a
    numpy.ndarray on others; soundfile needs an array-like, so bridge the
    torch case without a hard top-level torch import (torch is only ever
    present because kokoro pulled it in)."""
    cpu = getattr(audio, "cpu", None)
    if callable(cpu):
        audio = cpu()
    to_numpy = getattr(audio, "numpy", None)
    if callable(to_numpy):
        audio = to_numpy()
    return audio


def _encode_wav(audio: Any, sample_rate: int) -> bytes:
    import soundfile as sf

    buffer = io.BytesIO()
    sf.write(buffer, _to_numpy_audio(audio), sample_rate, format="WAV")
    return buffer.getvalue()


class LocalASRProvider:
    """BUILD_SPEC section 28 — local RTX-accelerated speech recognition,
    backed by faster-whisper.

    Constructed fresh from stored Console settings, like
    ``ElevenLabsTTSProvider``, so a changed model/device selection takes
    effect on the next call without a process restart — the module-level
    cache above is what keeps that cheap instead of reloading weights every
    call.
    """

    _RUNTIME_CANDIDATES = ASR_RUNTIME_CANDIDATES

    def __init__(
        self, *, model: str | None = None, device: str = "cuda:0", language: str = "en"
    ) -> None:
        self._model = model
        self._device = device
        self._language = language
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def _runtime_missing_message(self) -> str:
        return (
            "no local ASR runtime installed (expected one of: "
            f"{', '.join(self._RUNTIME_CANDIDATES)}) — BUILD_SPEC section 30. "
            "Install the 'voice-local' extra to use it."
        )

    async def health(self) -> tuple[bool, str]:
        runtime = detect_runtime(self._RUNTIME_CANDIDATES)
        if runtime is None:
            return False, self._runtime_missing_message()
        if not self._model:
            return False, f"{runtime} is installed but no model is selected"
        return True, (
            f"{runtime} is installed and {self._model!r} is selected — "
            "weights load on first use or Load"
        )

    async def load(self) -> tuple[bool, str]:
        """Load the configured model for lower first-utterance latency.

        Returns ``(loaded, message)`` like ``health()`` rather than raising,
        so the Console's Load button can show why nothing happened. This
        genuinely constructs a ``WhisperModel`` — the first call for a given
        (model, device) downloads weights from Hugging Face and can take a
        while. Cannot be exercised against real hardware in this sandbox;
        only the "not installed" path is covered here.
        """
        healthy, message = await self.health()
        if not healthy:
            self._loaded = False
            return False, message
        try:
            await asyncio.to_thread(self._load_model_sync)
        except Exception as exc:
            self._loaded = False
            return False, f"failed to load {self._model!r}: {exc}"
        self._loaded = True
        return True, f"{self._model} loaded on {self._device}"

    async def unload(self) -> tuple[bool, str]:
        if self._model:
            with _ASR_CACHE_LOCK:
                _ASR_MODEL_CACHE.pop((self._model, self._device), None)
        self._loaded = False
        return True, "unloaded"

    def _load_model_sync(self) -> Any:
        if not self._model:
            raise ProviderError("no local ASR model selected", provider="local_asr")
        key = (self._model, self._device)
        with _ASR_CACHE_LOCK:
            cached = _ASR_MODEL_CACHE.get(key)
        if cached is not None:
            return cached
        from faster_whisper import WhisperModel

        model = WhisperModel(self._model, device=self._device)
        with _ASR_CACHE_LOCK:
            _ASR_MODEL_CACHE[key] = model
        return model

    def _transcribe_sync(self, audio: bytes) -> TranscriptionResult:
        model = self._load_model_sync()
        segments, info = model.transcribe(io.BytesIO(audio), language=self._language or None)
        text = "".join(segment.text for segment in segments).strip()
        return TranscriptionResult(text=text, language=info.language, is_final=True)

    async def transcribe(self, audio: bytes) -> TranscriptionResult:
        healthy, message = await self.health()
        if not healthy:
            raise ProviderError(message, provider="local_asr")
        try:
            return await asyncio.to_thread(self._transcribe_sync, audio)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"local ASR transcription failed: {exc}", provider="local_asr"
            ) from exc

    async def stream(
        self, audio_stream: AsyncIterator[bytes]
    ) -> AsyncIterator[TranscriptionResult]:
        """Not incremental: faster-whisper has no partial-hypothesis API this
        codebase drives, so this collects the full utterance and yields one
        final result rather than fabricating interim partials. True
        streaming needs voice-activity-detection-driven chunking on the
        Voice Bridge side — out of LifeOps Core's scope per BUILD_SPEC
        section 32 (the Voice Bridge sits in the Hermes runtime, not here)
        and not built anywhere in this codebase yet; see CLAUDE.md's Known
        gaps.
        """
        healthy, message = await self.health()
        if not healthy:
            raise ProviderError(message, provider="local_asr")
            yield TranscriptionResult(text="")  # pragma: no cover - unreachable
        chunks = [chunk async for chunk in audio_stream]
        try:
            result = await asyncio.to_thread(self._transcribe_sync, b"".join(chunks))
        except Exception as exc:
            raise ProviderError(
                f"local ASR transcription failed: {exc}", provider="local_asr"
            ) from exc
        yield result


class LocalTTSProvider:
    """BUILD_SPEC section 28 — local RTX-accelerated speech synthesis,
    backed by Kokoro via the ``kokoro`` package's ``KPipeline``.

    Same "real once installed, honest gap otherwise" shape as
    ``LocalASRProvider`` — see that class's docstring for the caching
    rationale. ``stream()`` here is genuinely incremental: Kokoro splits
    text into segments and yields audio per segment, so this bridges that
    blocking generator onto the running event loop from a worker thread
    rather than collecting all audio before the first chunk is available.
    """

    _RUNTIME_CANDIDATES = TTS_RUNTIME_CANDIDATES

    def __init__(
        self,
        *,
        model: str | None = None,
        device: str = "cuda:0",
        speed: float = 1.0,
        voice: str | None = None,
        lang_code: str = "a",
    ) -> None:
        self._model = model
        self._device = device
        self._speed = speed
        self._voice = voice
        # No Console field for this yet — BUILD_SPEC's SynthesisOptions has
        # no language concept, and nobody has asked for non-English local
        # synthesis. 'a' (American English) is Kokoro's own default accent;
        # change this constructor argument directly if that's ever needed,
        # rather than adding a field for a case nobody has hit.
        self._lang_code = lang_code
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def _kokoro_device(self) -> str | None:
        normalized = (self._device or "").split(":", 1)[0]
        return normalized if normalized in ("cuda", "mps", "cpu") else None

    async def health(self) -> tuple[bool, str]:
        runtime = detect_runtime(self._RUNTIME_CANDIDATES)
        if runtime is None:
            return False, (
                "no local TTS runtime is installed (expected one of: "
                f"{', '.join(self._RUNTIME_CANDIDATES)}) — BUILD_SPEC section 30 also "
                "lists Qwen3-TTS and Chatterbox Turbo as candidates; neither has an "
                "adapter in this codebase yet. Install the 'voice-local' extra to use "
                "Kokoro."
            )
        if not self._model:
            return False, f"{runtime} is installed but no model is selected"
        return True, f"{runtime} is installed and ready — weights load on first use or Load"

    async def load(self) -> tuple[bool, str]:
        healthy, message = await self.health()
        if not healthy:
            self._loaded = False
            return False, message
        try:
            await asyncio.to_thread(self._load_pipeline_sync)
        except Exception as exc:
            self._loaded = False
            return False, f"failed to load kokoro: {exc}"
        self._loaded = True
        return True, f"kokoro loaded on {self._device}"

    async def unload(self) -> tuple[bool, str]:
        with _TTS_CACHE_LOCK:
            _TTS_PIPELINE_CACHE.pop((self._lang_code, self._kokoro_device()), None)
        self._loaded = False
        return True, "unloaded"

    def _load_pipeline_sync(self) -> Any:
        key = (self._lang_code, self._kokoro_device())
        with _TTS_CACHE_LOCK:
            cached = _TTS_PIPELINE_CACHE.get(key)
        if cached is not None:
            return cached
        from kokoro import KPipeline

        pipeline = KPipeline(lang_code=self._lang_code, device=self._kokoro_device())
        with _TTS_CACHE_LOCK:
            _TTS_PIPELINE_CACHE[key] = pipeline
        return pipeline

    def _synthesize_sync(self, text: str, options: SynthesisOptions) -> bytes:
        pipeline = self._load_pipeline_sync()
        voice = options.voice_id or self._voice or _DEFAULT_KOKORO_VOICE
        speed = options.speed if options.speed is not None else self._speed
        chunks = [
            _to_numpy_audio(audio)
            for _graphemes, _phonemes, audio in pipeline(text, voice=voice, speed=speed)
        ]
        if not chunks:
            raise ProviderError("kokoro produced no audio for this text", provider="local_tts")
        import numpy as np

        combined = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
        return _encode_wav(combined, _KOKORO_SAMPLE_RATE_HZ)

    async def synthesize(self, text: str, options: SynthesisOptions) -> bytes:
        healthy, message = await self.health()
        if not healthy:
            raise ProviderError(message, provider="local_tts")
        try:
            return await asyncio.to_thread(self._synthesize_sync, text, options)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"local TTS synthesis failed: {exc}", provider="local_tts"
            ) from exc

    async def stream(self, text: str, options: SynthesisOptions) -> AsyncIterator[bytes]:
        healthy, message = await self.health()
        if not healthy:
            raise ProviderError(message, provider="local_tts")
            yield b""  # pragma: no cover - unreachable
        voice = options.voice_id or self._voice or _DEFAULT_KOKORO_VOICE
        speed = options.speed if options.speed is not None else self._speed
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Any] = asyncio.Queue()
        sentinel = object()

        def _produce() -> None:
            try:
                pipeline = self._load_pipeline_sync()
                for _graphemes, _phonemes, audio in pipeline(text, voice=voice, speed=speed):
                    wav_bytes = _encode_wav(_to_numpy_audio(audio), _KOKORO_SAMPLE_RATE_HZ)
                    loop.call_soon_threadsafe(queue.put_nowait, wav_bytes)
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, sentinel)

        thread = threading.Thread(target=_produce, daemon=True)
        thread.start()
        while True:
            item = await queue.get()
            if item is sentinel:
                break
            if isinstance(item, Exception):
                raise ProviderError(
                    f"local TTS streaming failed: {item}", provider="local_tts"
                ) from item
            yield item

    async def list_voices(self) -> list[Voice]:
        healthy, _ = await self.health()
        if not healthy:
            return []
        return [
            Voice(id=voice_id, name=voice_id, category="kokoro")
            for voice_id in _KNOWN_KOKORO_VOICES
        ]

    async def list_models(self) -> list[TTSModel]:
        healthy, _ = await self.health()
        if not healthy:
            return []
        return [TTSModel(id="kokoro", name="Kokoro (82M)", supports_streaming=True)]
