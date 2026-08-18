"""VoiceService — selects and calls the enabled TTS/ASR providers
(BUILD_SPEC sections 27-30, 95).

Lives next to ``ConfigurationService`` rather than in ``LifeOpsCore``: it
composes provider configuration and the SecretStore into calls against an
external speech API or a local runtime, and it never reads or writes a
person, task, or preference — LifeOpsCore's world model is untouched.

Which provider answers a call is governed by two things layered together:

  * BUILD_SPEC section 29's voice mode (``SystemConfig.voice_mode``) pins
    which provider id a category *should* use — Hybrid and Local both pin
    ASR to ``local_asr``; Quick Cloud and Hybrid both pin TTS to
    ``elevenlabs``; Quick Cloud leaves ASR "configurable", i.e. unpinned.
  * whether that pinned provider (or, when unpinned, any provider in the
    category) is actually enabled and fully configured.

Switching modes is a LifeOps setting a user changes in Configuration; it
never touches the Hermes profile (section 29).
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from lifeops.config.provider_registry import ProviderCategory, providers_in_category
from lifeops.config.service import ConfigurationService, HealthReport
from lifeops.domain.voice import (
    SynthesisOptions,
    TranscriptionResult,
    TTSModel,
    Voice,
    VoiceMode,
    VoiceModeStatus,
    validate_synthesis_text,
)
from lifeops.errors import ProviderNotConfiguredError
from lifeops.secrets.interface import SecretStore, secret_ref
from lifeops.voice.elevenlabs import ElevenLabsTTSProvider
from lifeops.voice.local import LocalASRProvider, LocalTTSProvider
from lifeops.voice.provider import ASRProvider, TTSProvider

TTSProviderFactory = Callable[[dict[str, Any], SecretStore], TTSProvider]
ASRProviderFactory = Callable[[dict[str, Any], SecretStore], ASRProvider]

# Backward-compatible alias: phase 5 tests construct VoiceService with
# ``factories={...}`` meaning TTS factories specifically.
ProviderFactory = TTSProviderFactory


def _number(value: Any, *, default: float) -> float:
    """A numeric setting, defaulting only when it is truly unset.

    ``float(settings.get(x) or default)`` silently turned a stored,
    schema-valid 0 back into the default.
    """
    return default if value is None else float(value)



async def _close_provider(provider: object) -> None:
    """Close a per-call provider's transport, when it has one.

    Providers are built fresh per call from current configuration; the
    ElevenLabs adapter owns an httpx.AsyncClient, and before this nothing
    ever called its aclose — every synthesize/health/list call leaked a
    connection pool.
    """
    closer = getattr(provider, "aclose", None)
    if closer is not None:
        await closer()


def _build_elevenlabs(settings: dict[str, Any], secrets: SecretStore) -> TTSProvider:
    api_key = secrets.get(secret_ref("elevenlabs", "api_key"))
    if not api_key:
        raise ProviderNotConfiguredError(
            "ElevenLabs has no API key configured", provider="elevenlabs"
        )
    return ElevenLabsTTSProvider(
        api_key=api_key,
        voice_id=settings.get("voice_id"),
        model_id=settings.get("model_id"),
        output_format=settings.get("output_format") or "mp3_44100_128",
        # 'or' would turn a stored, schema-valid 0 back into the default.
        stability=_number(settings.get("stability"), default=0.5),
        similarity_boost=_number(settings.get("similarity_boost"), default=0.75),
        speed=_number(settings.get("speed"), default=1.0),
    )


def _build_local_tts(settings: dict[str, Any], secrets: SecretStore) -> TTSProvider:
    return LocalTTSProvider(
        model=settings.get("model"),
        device=settings.get("device") or "cuda:0",
        speed=_number(settings.get("speed"), default=1.0),
        voice=settings.get("voice"),
    )


def _build_local_asr(settings: dict[str, Any], secrets: SecretStore) -> ASRProvider:
    return LocalASRProvider(
        model=settings.get("model"),
        device=settings.get("device") or "cuda:0",
        language=settings.get("language") or "en",
    )


_DEFAULT_TTS_FACTORIES: dict[str, TTSProviderFactory] = {
    "elevenlabs": _build_elevenlabs,
    "local_tts": _build_local_tts,
}
_DEFAULT_ASR_FACTORIES: dict[str, ASRProviderFactory] = {
    "local_asr": _build_local_asr,
}

#: BUILD_SPEC section 29 — which provider id each mode pins a category to.
#: ``None`` means "configurable": pick whatever enabled provider comes first,
#: same as pre-mode phase 5 behaviour.
_TTS_PINNED_BY_MODE: dict[VoiceMode, str] = {
    VoiceMode.QUICK_CLOUD: "elevenlabs",
    VoiceMode.HYBRID: "elevenlabs",
    VoiceMode.LOCAL: "local_tts",
}
_ASR_PINNED_BY_MODE: dict[VoiceMode, str | None] = {
    VoiceMode.QUICK_CLOUD: None,
    VoiceMode.HYBRID: "local_asr",
    VoiceMode.LOCAL: "local_asr",
}


class VoiceService:
    def __init__(
        self,
        *,
        config: ConfigurationService,
        secret_store: SecretStore,
        factories: dict[str, TTSProviderFactory] | None = None,
        asr_factories: dict[str, ASRProviderFactory] | None = None,
    ) -> None:
        self._config = config
        self._secrets = secret_store
        self._tts_factories = factories if factories is not None else _DEFAULT_TTS_FACTORIES
        self._asr_factories = (
            asr_factories if asr_factories is not None else _DEFAULT_ASR_FACTORIES
        )

    # --- readiness / selection -----------------------------------------------

    def _is_ready(self, provider_id: str) -> bool:
        """"Enabled" and not merely "configured": a provider a user filled in
        but left off must not silently start speaking or listening."""
        status = self._config.get_status(provider_id)
        return status.enabled and not status.missing_required

    def _ready_candidates(self, category: ProviderCategory) -> list[str]:
        factories = self._tts_factories if category is ProviderCategory.VOICE_TTS else (
            self._asr_factories
        )
        return [
            definition.id
            for definition in providers_in_category(category)
            if definition.id in factories and self._is_ready(definition.id)
        ]

    def _active_provider_id(
        self, category: ProviderCategory, factories: dict[str, Any], pinned: str | None
    ) -> str | None:
        """The provider id ``category`` resolves to right now.

        A pin naming a provider this VoiceService was not built with (e.g. a
        test's narrowed factories dict) falls back to "configurable" rather
        than raising, so a test that only wires one fake still works.
        """
        if pinned is not None and pinned in factories:
            return pinned if self._is_ready(pinned) else None
        candidates = self._ready_candidates(category)
        return candidates[0] if candidates else None

    def _active_tts_provider_id(self) -> str | None:
        pinned = _TTS_PINNED_BY_MODE[self._config.get_system().voice_mode]
        return self._active_provider_id(ProviderCategory.VOICE_TTS, self._tts_factories, pinned)

    def _active_asr_provider_id(self) -> str | None:
        pinned = _ASR_PINNED_BY_MODE[self._config.get_system().voice_mode]
        return self._active_provider_id(ProviderCategory.VOICE_ASR, self._asr_factories, pinned)

    def _tts_unavailable_message(self) -> str:
        mode = self._config.get_system().voice_mode
        pinned = _TTS_PINNED_BY_MODE[mode]
        return (
            f"voice mode {mode.value!r} requires the {pinned!r} text-to-speech "
            "provider to be enabled and fully configured"
        )

    def _asr_unavailable_message(self) -> str:
        mode = self._config.get_system().voice_mode
        pinned = _ASR_PINNED_BY_MODE[mode]
        if pinned is None:
            return "no speech-to-text provider is enabled and fully configured yet"
        return (
            f"voice mode {mode.value!r} requires the {pinned!r} speech-to-text "
            "provider to be enabled and fully configured"
        )

    def _build_tts(self) -> tuple[str, TTSProvider]:
        provider_id = self._active_tts_provider_id()
        if provider_id is None:
            raise ProviderNotConfiguredError(self._tts_unavailable_message())
        status = self._config.get_status(provider_id)
        provider = self._tts_factories[provider_id](status.settings, self._secrets)
        return provider_id, provider

    def _build_asr(self) -> tuple[str, ASRProvider]:
        provider_id = self._active_asr_provider_id()
        if provider_id is None:
            raise ProviderNotConfiguredError(self._asr_unavailable_message())
        status = self._config.get_status(provider_id)
        provider = self._asr_factories[provider_id](status.settings, self._secrets)
        return provider_id, provider

    def _build_specific(self, provider_id: str) -> TTSProvider | ASRProvider:
        """Build exactly ``provider_id``, bypassing voice-mode selection.

        The Console's Test/Load/Unload buttons act on the card the user
        clicked, not on whatever the current mode would pick — testing the
        local_tts card must test local_tts even while Quick Cloud mode has
        TTS pinned to elevenlabs.
        """
        if provider_id in self._tts_factories:
            factories: dict[str, Any] = self._tts_factories
        elif provider_id in self._asr_factories:
            factories = self._asr_factories
        else:
            raise ProviderNotConfiguredError(f"{provider_id!r} has no voice adapter registered")
        if not self._is_ready(provider_id):
            raise ProviderNotConfiguredError(
                f"{provider_id!r} is not enabled and fully configured"
            )
        status = self._config.get_status(provider_id)
        return factories[provider_id](status.settings, self._secrets)

    def mode_status(self) -> VoiceModeStatus:
        """A pure readback of what the current mode has selected, for the
        Configuration screen's "active provider" / "fallback provider"."""
        mode = self._config.get_system().voice_mode
        tts_active = self._active_tts_provider_id()
        tts_ready = self._ready_candidates(ProviderCategory.VOICE_TTS)
        tts_fallback = next((p for p in tts_ready if p != tts_active), None)
        asr_active = self._active_asr_provider_id()
        asr_ready = self._ready_candidates(ProviderCategory.VOICE_ASR)
        asr_fallback = next((p for p in asr_ready if p != asr_active), None)
        return VoiceModeStatus(
            mode=mode,
            tts_active=tts_active,
            tts_fallback=tts_fallback,
            asr_active=asr_active,
            asr_fallback=asr_fallback,
        )

    # --- text-to-speech --------------------------------------------------------

    async def health(self) -> tuple[str, HealthReport]:
        """The mode's active TTS provider. Raises ``ProviderNotConfiguredError``
        rather than recording a health entry against a provider nobody has
        chosen yet."""
        provider_id, provider = self._build_tts()
        try:
            return provider_id, await self._checked_health(provider_id, provider)
        finally:
            await _close_provider(provider)

    async def health_for(self, provider_id: str) -> tuple[str, HealthReport]:
        """Health-check one specific provider, ignoring voice mode — what the
        Console's per-card Test button calls."""
        provider = self._build_specific(provider_id)
        try:
            return provider_id, await self._checked_health(provider_id, provider)
        finally:
            await _close_provider(provider)

    async def _checked_health(
        self, provider_id: str, provider: TTSProvider | ASRProvider
    ) -> HealthReport:
        """Times the call so the Console can show a latency indicator
        (BUILD_SPEC section 95) without every caller measuring it by hand."""
        started = time.monotonic()
        healthy, message = await provider.health()
        latency_ms = round((time.monotonic() - started) * 1000, 1)
        return self._config.record_health(
            provider_id, healthy=healthy, message=message, latency_ms=latency_ms
        )

    async def list_voices(self) -> list[Voice]:
        _, provider = self._build_tts()
        try:
            return await provider.list_voices()
        finally:
            await _close_provider(provider)

    async def list_models(self) -> list[TTSModel]:
        _, provider = self._build_tts()
        try:
            return await provider.list_models()
        finally:
            await _close_provider(provider)

    async def synthesize(self, text: str, options: SynthesisOptions | None = None) -> bytes:
        clean = validate_synthesis_text(text)
        _, provider = self._build_tts()
        try:
            return await provider.synthesize(clean, options or SynthesisOptions())
        finally:
            await _close_provider(provider)

    def stream(
        self, text: str, options: SynthesisOptions | None = None
    ) -> AsyncIterator[bytes]:
        """Not a coroutine, so a missing provider or bad text raises here and
        now — before a caller has committed to a streaming HTTP response."""
        clean = validate_synthesis_text(text)
        _, provider = self._build_tts()
        inner = provider.stream(clean, options or SynthesisOptions())

        async def _piped() -> AsyncIterator[bytes]:
            try:
                async for chunk in inner:
                    yield chunk
            finally:
                await _close_provider(provider)

        return _piped()

    # --- speech-to-text ----------------------------------------------------

    async def transcribe(self, audio: bytes) -> TranscriptionResult:
        _, provider = self._build_asr()
        try:
            return await provider.transcribe(audio)
        finally:
            await _close_provider(provider)

    def transcribe_stream(
        self, audio_stream: AsyncIterator[bytes]
    ) -> AsyncIterator[TranscriptionResult]:
        _, provider = self._build_asr()
        return provider.stream(audio_stream)

    # --- load / unload (local providers) ------------------------------------

    async def load(self, provider_id: str) -> tuple[bool, str]:
        """Load a local provider's model into memory (BUILD_SPEC section 95's
        Load/Unload buttons). Only local providers implement ``load``; asking
        for it on ElevenLabs is a configuration error, not a crash."""
        provider = self._build_specific(provider_id)
        loader = getattr(provider, "load", None)
        if loader is None:
            raise ProviderNotConfiguredError(f"{provider_id!r} has no load/unload lifecycle")
        healthy, message = await loader()
        return healthy, message

    async def unload(self, provider_id: str) -> tuple[bool, str]:
        provider = self._build_specific(provider_id)
        unloader = getattr(provider, "unload", None)
        if unloader is None:
            raise ProviderNotConfiguredError(f"{provider_id!r} has no load/unload lifecycle")
        return await unloader()
