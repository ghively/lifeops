"""Voice domain — pure rules for the ElevenLabs quick path (BUILD_SPEC 27-29, 94).

No I/O, no Cypher, no HTTP. This module defines the shapes the voice pipeline
passes around and the one rule that belongs to every caller equally: bounding
the text a synthesis request may carry. Everything that actually reaches a
network — ElevenLabs, a future local model — lives in ``lifeops.voice``.
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
