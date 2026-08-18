"""LocalTTSProvider and LocalASRProvider (BUILD_SPEC sections 28, 30, 95).

These exist so the ``TTSProvider``/``ASRProvider`` abstraction has a second
real implementation and so hybrid/local voice mode has something concrete to
select — not to ship a working local speech stack. AGENTS.md requires a
written justification for any new dependency, and a multi-gigabyte GPU
runtime (torch, faster-whisper, piper, ...) is not something this repository
installs speculatively (BUILD_SPEC section 105's anti-overengineering gate).

Instead each adapter *detects* whether a runtime it could call is importable
and reports the honest result through ``health()`` — "not installed" when it
genuinely is not, or "installed but no adapter is wired to it yet" on the rare
box that happens to have one already, since being importable is not the same
as this codebase knowing how to drive it. ``transcribe``/``synthesize``/
``stream`` never fabricate output: they raise with that same message, exactly
as ``api/http.py``'s ``test_provider`` already does for every provider that
has no adapter (BUILD_SPEC section 88 — never fake success).

No model is ever downloaded here. Model/device selection are Console fields
(``config/provider_registry.py``); this module only decides whether it could
possibly use whatever the user picks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from lifeops.domain.voice import SynthesisOptions, TranscriptionResult, TTSModel, Voice
from lifeops.errors import ProviderError
from lifeops.runtime import detect_runtime

# BUILD_SPEC section 30's ASR candidates. faster-whisper is a real, commonly
# installed package (module name faster_whisper) so detecting it is useful;
# the NVIDIA streaming candidate has no fixed package name to check for.
ASR_RUNTIME_CANDIDATES: tuple[str, ...] = ("faster_whisper",)

# BUILD_SPEC section 30's TTS candidates (Qwen3-TTS, Chatterbox Turbo, Kokoro)
# are product names, not confirmed importable package names — guessing one
# and reporting "installed" incorrectly would be worse than reporting
# "unknown". Left empty until a real adapter targets one specifically.
TTS_RUNTIME_CANDIDATES: tuple[str, ...] = ()



class LocalASRProvider:
    """BUILD_SPEC section 28 — local RTX-accelerated speech recognition.

    Constructed fresh from stored Console settings, like
    ``ElevenLabsTTSProvider``, so a changed model/device selection takes
    effect on the next call without a process restart.
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
            f"{', '.join(self._RUNTIME_CANDIDATES)}) — BUILD_SPEC section 30"
        )

    async def health(self) -> tuple[bool, str]:
        runtime = detect_runtime(self._RUNTIME_CANDIDATES)
        if runtime is None:
            return False, self._runtime_missing_message()
        if not self._model:
            return False, f"{runtime} is installed but no model is selected"
        return False, (
            f"{runtime} is installed but LifeOps has no adapter wired to its API "
            "yet — being importable is not the same as being integrated"
        )

    async def load(self) -> tuple[bool, str]:
        """Load the configured model for lower first-utterance latency.

        Returns ``(loaded, message)`` like ``health()`` rather than raising,
        so the Console's Load button can show why nothing happened.
        """
        healthy, message = await self.health()
        self._loaded = healthy
        return healthy, message

    async def unload(self) -> tuple[bool, str]:
        self._loaded = False
        return True, "unloaded"

    async def transcribe(self, audio: bytes) -> TranscriptionResult:
        _, message = await self.health()
        raise ProviderError(message, provider="local_asr")

    async def stream(
        self, audio_stream: AsyncIterator[bytes]
    ) -> AsyncIterator[TranscriptionResult]:
        _, message = await self.health()
        raise ProviderError(message, provider="local_asr")
        yield TranscriptionResult(text="")  # pragma: no cover - unreachable; see docstring


class LocalTTSProvider:
    """BUILD_SPEC section 28 — local RTX-accelerated speech synthesis."""

    _RUNTIME_CANDIDATES = TTS_RUNTIME_CANDIDATES

    def __init__(
        self, *, model: str | None = None, device: str = "cuda:0", speed: float = 1.0
    ) -> None:
        self._model = model
        self._device = device
        self._speed = speed
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    async def health(self) -> tuple[bool, str]:
        runtime = detect_runtime(self._RUNTIME_CANDIDATES)
        if runtime is None:
            return False, (
                "no local TTS runtime is wired up yet — BUILD_SPEC section 30 lists "
                "Qwen3-TTS, Chatterbox Turbo, and Kokoro as candidates; none has an "
                "adapter in this codebase"
            )
        if not self._model:
            return False, f"{runtime} is installed but no model is selected"
        return False, (
            f"{runtime} is installed but LifeOps has no adapter wired to its API "
            "yet — being importable is not the same as being integrated"
        )

    async def load(self) -> tuple[bool, str]:
        healthy, message = await self.health()
        self._loaded = healthy
        return healthy, message

    async def unload(self) -> tuple[bool, str]:
        self._loaded = False
        return True, "unloaded"

    async def synthesize(self, text: str, options: SynthesisOptions) -> bytes:
        _, message = await self.health()
        raise ProviderError(message, provider="local_tts")

    async def stream(self, text: str, options: SynthesisOptions) -> AsyncIterator[bytes]:
        _, message = await self.health()
        raise ProviderError(message, provider="local_tts")
        yield b""  # pragma: no cover - unreachable; see docstring

    async def list_voices(self) -> list[Voice]:
        return []

    async def list_models(self) -> list[TTSModel]:
        return []
