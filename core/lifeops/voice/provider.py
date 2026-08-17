"""TTSProvider and ASRProvider abstractions (BUILD_SPEC section 28).

Do not hardwire Hermes, LifeOps Core, or the Console directly to ElevenLabs or
to any one local runtime. Everything that turns text into audio implements
``TTSProvider``; everything that turns audio into text implements
``ASRProvider``. Swapping ElevenLabs for a local RTX model (phase 6), or
adding a cloud ASR provider later (section 28's "optional future"), means
writing a new implementation, not touching a caller.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from lifeops.domain.voice import SynthesisOptions, TranscriptionResult, TTSModel, Voice


@runtime_checkable
class TTSProvider(Protocol):
    """Section 27's five capabilities, adapter-shaped."""

    async def synthesize(self, text: str, options: SynthesisOptions) -> bytes:
        """The complete audio for ``text`` in one response."""
        ...

    def stream(self, text: str, options: SynthesisOptions) -> AsyncIterator[bytes]:
        """Audio chunks for ``text`` as they become available.

        Not a coroutine: implementations are async generators, so calling
        this returns an iterator immediately without awaiting the whole
        synthesis first.
        """
        ...

    async def list_voices(self) -> list[Voice]: ...

    async def list_models(self) -> list[TTSModel]: ...

    async def health(self) -> tuple[bool, str]:
        """(healthy, message) — never raises for an ordinary connection failure."""
        ...


@runtime_checkable
class ASRProvider(Protocol):
    """Section 28's speech-recognition counterpart to ``TTSProvider``.

    Signature shape mirrors ``TTSProvider`` deliberately: a complete-response
    call (``transcribe``), a streaming call that is not itself a coroutine
    (``stream``), and an honest ``health`` that never raises for an ordinary
    unavailability.
    """

    async def transcribe(self, audio: bytes) -> TranscriptionResult:
        """The complete transcript for one finished utterance."""
        ...

    def stream(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[TranscriptionResult]:
        """Transcripts as audio arrives, partial results included.

        Not a coroutine, for the same reason as ``TTSProvider.stream``:
        implementations are async generators, so calling this starts
        yielding without first buffering the whole utterance.
        """
        ...

    async def health(self) -> tuple[bool, str]:
        """(healthy, message) — never raises for an ordinary connection failure."""
        ...
