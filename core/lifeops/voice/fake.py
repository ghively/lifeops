"""Fake voice providers — the test doubles AGENTS.md requires for every
provider.

Development and CI never hold a real ElevenLabs API key and never install a
GPU speech runtime (AGENTS.md: never ask for a runtime credential; no ML
dependency without written justification — BUILD_SPEC section 105), so
nothing in this codebase exercises ``ElevenLabsTTSProvider`` or the local
adapters against the real thing. These fakes are what let ``VoiceService`` be
tested end to end anyway: deterministic voices, models, and transcripts, and
audio/text derived from the input so a test can assert on content without
recognising real synthesized speech or transcription.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from lifeops.domain.voice import SynthesisOptions, TranscriptionResult, TTSModel, Voice

FAKE_VOICES = [
    Voice(id="voice-fake-1", name="Fake Narrator", category="premade"),
    Voice(id="voice-fake-2", name="Fake Assistant", category="premade"),
]

FAKE_MODELS = [
    TTSModel(id="model-fake-flash", name="Fake Flash (low latency)"),
    TTSModel(id="model-fake-multilingual", name="Fake Multilingual"),
]

FAKE_LOCAL_VOICES = [
    Voice(id="voice-fake-local-1", name="Fake Local Narrator", category="local"),
]

FAKE_LOCAL_MODELS = [
    TTSModel(id="model-fake-local", name="Fake Local Model"),
]


class FakeTTSProvider:
    """In-memory ``TTSProvider``. No network, no filesystem."""

    def __init__(self, *, healthy: bool = True) -> None:
        self._healthy = healthy
        self.calls: list[str] = []

    async def synthesize(self, text: str, options: SynthesisOptions) -> bytes:
        self.calls.append(text)
        return f"FAKE-AUDIO:{options.voice_id or 'default'}:{text}".encode()

    async def stream(self, text: str, options: SynthesisOptions) -> AsyncIterator[bytes]:
        payload = await self.synthesize(text, options)
        chunk_size = max(1, len(payload) // 4)
        for start in range(0, len(payload), chunk_size):
            yield payload[start : start + chunk_size]

    async def list_voices(self) -> list[Voice]:
        return list(FAKE_VOICES)

    async def list_models(self) -> list[TTSModel]:
        return list(FAKE_MODELS)

    async def health(self) -> tuple[bool, str]:
        if self._healthy:
            return True, "fake provider"
        return False, "fake provider reports unhealthy"


class FakeLocalTTSProvider:
    """In-memory ``TTSProvider`` standing in for ``LocalTTSProvider`` in
    tests, so hybrid/local voice mode can be exercised without a GPU."""

    def __init__(self, *, healthy: bool = True) -> None:
        self._healthy = healthy
        self.calls: list[str] = []
        self.loaded = False

    async def synthesize(self, text: str, options: SynthesisOptions) -> bytes:
        self.calls.append(text)
        return f"FAKE-LOCAL-AUDIO:{options.voice_id or 'default'}:{text}".encode()

    async def stream(self, text: str, options: SynthesisOptions) -> AsyncIterator[bytes]:
        payload = await self.synthesize(text, options)
        chunk_size = max(1, len(payload) // 4)
        for start in range(0, len(payload), chunk_size):
            yield payload[start : start + chunk_size]

    async def list_voices(self) -> list[Voice]:
        return list(FAKE_LOCAL_VOICES)

    async def list_models(self) -> list[TTSModel]:
        return list(FAKE_LOCAL_MODELS)

    async def health(self) -> tuple[bool, str]:
        if self._healthy:
            return True, "fake local provider"
        return False, "fake local provider reports unhealthy"

    async def load(self) -> tuple[bool, str]:
        healthy, message = await self.health()
        self.loaded = healthy
        return healthy, message

    async def unload(self) -> tuple[bool, str]:
        self.loaded = False
        return True, "unloaded"


class FakeASRProvider:
    """In-memory ``ASRProvider``. No network, no filesystem, no GPU.

    ``transcribe`` derives deterministic text from the input bytes — decoding
    them as UTF-8 when that succeeds (tests can feed in plain text standing
    for "audio") and falling back to a byte-count placeholder otherwise, so
    the fake works whether a test hands it real WAV bytes or a text stand-in.
    """

    def __init__(self, *, healthy: bool = True) -> None:
        self._healthy = healthy
        self.loaded = False
        self.calls: list[bytes] = []

    def _transcript_for(self, audio: bytes) -> str:
        try:
            return audio.decode("utf-8")
        except UnicodeDecodeError:
            return f"[{len(audio)} bytes of fake audio]"

    async def transcribe(self, audio: bytes) -> TranscriptionResult:
        self.calls.append(audio)
        return TranscriptionResult(text=self._transcript_for(audio), language="en")

    async def stream(
        self, audio_stream: AsyncIterator[bytes]
    ) -> AsyncIterator[TranscriptionResult]:
        async for chunk in audio_stream:
            yield await self.transcribe(chunk)

    async def health(self) -> tuple[bool, str]:
        if self._healthy:
            return True, "fake provider"
        return False, "fake provider reports unhealthy"

    async def load(self) -> tuple[bool, str]:
        healthy, message = await self.health()
        self.loaded = healthy
        return healthy, message

    async def unload(self) -> tuple[bool, str]:
        self.loaded = False
        return True, "unloaded"
