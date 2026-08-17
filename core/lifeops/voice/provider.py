"""TTSProvider abstraction (BUILD_SPEC section 28).

Do not hardwire Hermes, LifeOps Core, or the Console directly to ElevenLabs.
Everything that turns text into audio implements this Protocol; swapping
ElevenLabs for a local RTX model later (phase 6) means writing a new
implementation, not touching a caller.

An ``ASRProvider`` counterpart belongs here too, but phase 5 ships no speech
recognition — local ASR arrives in phase 6 — so it is not declared until a
caller needs it (AGENTS.md: no infrastructure for hypothetical problems).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from lifeops.domain.voice import SynthesisOptions, TTSModel, Voice


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
