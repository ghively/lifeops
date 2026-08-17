"""FakeTTSProvider — the test double AGENTS.md requires for every provider.

Development and CI never hold a real ElevenLabs API key (AGENTS.md: never
ask the user for a runtime credential), so nothing in this codebase exercises
``ElevenLabsTTSProvider`` against the live network. This fake is what lets
``VoiceService`` be tested end to end anyway: deterministic voices and
models, and audio bytes derived from the input text so a test can assert on
content without recognising real synthesized speech.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from lifeops.domain.voice import SynthesisOptions, TTSModel, Voice

FAKE_VOICES = [
    Voice(id="voice-fake-1", name="Fake Narrator", category="premade"),
    Voice(id="voice-fake-2", name="Fake Assistant", category="premade"),
]

FAKE_MODELS = [
    TTSModel(id="model-fake-flash", name="Fake Flash (low latency)"),
    TTSModel(id="model-fake-multilingual", name="Fake Multilingual"),
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
