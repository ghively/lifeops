"""Voice domain — pure rules shared by the cloud and local voice paths
(BUILD_SPEC 27-30, 94-95).

No I/O, no Cypher, no HTTP. This module defines the shapes the voice pipeline
passes around and the one rule that belongs to every caller equally: bounding
the text a synthesis request may carry. Everything that actually reaches a
network or a local runtime — ElevenLabs, ``lifeops.voice.local``'s adapters —
lives in ``lifeops.voice``.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from lifeops.errors import ValidationError

# Sample/preview text is user-supplied and turns directly into a paid API
# call. Bounding it here means every caller — the Console's preview button,
# a future Voice Bridge phrase — gets the same ceiling without repeating it.
MAX_SYNTHESIS_TEXT_LENGTH = 2000


class VoiceMode(StrEnum):
    """BUILD_SPEC section 29 — which ASR/TTS pairing is active.

    A LifeOps configuration choice, not a Hermes one: switching modes changes
    which provider the Voice Bridge reaches for, without touching Hermes.
    """

    QUICK_CLOUD = "quick_cloud"
    HYBRID = "hybrid"
    LOCAL = "local"


class Voice(BaseModel):
    """One TTS voice, as an adapter reports it (BUILD_SPEC section 27)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    category: str | None = None
    preview_url: str | None = None


class TTSModel(BaseModel):
    """One TTS model a provider can synthesize with."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    supports_streaming: bool = True


class SynthesisOptions(BaseModel):
    """Per-call overrides layered over a provider's stored configuration.

    Every field is optional: the Console's preview button can try a
    different voice for one call without touching the saved default.
    """

    model_config = ConfigDict(extra="forbid")

    voice_id: str | None = None
    model_id: str | None = None
    output_format: str | None = None
    stability: float | None = Field(default=None, ge=0.0, le=1.0)
    similarity_boost: float | None = Field(default=None, ge=0.0, le=1.0)
    speed: float | None = Field(default=None, ge=0.5, le=2.0)


class TranscriptionResult(BaseModel):
    """What an ``ASRProvider`` hands back for a chunk of audio (section 28).

    ``is_final`` distinguishes a partial transcript a streaming ASR provider
    emits while the speaker is still talking from the settled text section 32
    calls the Voice Bridge to hand Hermes; a non-streaming ``transcribe`` call
    always returns exactly one final result.
    """

    model_config = ConfigDict(extra="forbid")

    text: str
    language: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    is_final: bool = True


class VoiceModeStatus(BaseModel):
    """What the Configuration screen's voice mode picker needs to render
    "active provider" and "fallback provider" (BUILD_SPEC section 95).

    Selection itself is ``VoiceService``'s job; this is only the readback —
    which provider id the current mode has chosen for each capability, and
    which enabled provider would be used next if that one stopped working.
    Nothing here performs a live health check; that stays behind the
    existing per-provider Test button so opening Configuration never fans
    out network calls on its own.
    """

    model_config = ConfigDict(extra="forbid")

    mode: VoiceMode
    tts_active: str | None = None
    tts_fallback: str | None = None
    asr_active: str | None = None
    asr_fallback: str | None = None


def validate_synthesis_text(text: str) -> str:
    """The one rule every synthesis path shares: non-empty, bounded length."""
    stripped = text.strip()
    if not stripped:
        raise ValidationError("text must not be empty", field="text")
    if len(stripped) > MAX_SYNTHESIS_TEXT_LENGTH:
        raise ValidationError(
            f"text must be at most {MAX_SYNTHESIS_TEXT_LENGTH} characters",
            field="text",
            max_length=MAX_SYNTHESIS_TEXT_LENGTH,
        )
    return stripped
