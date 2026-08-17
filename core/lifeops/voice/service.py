"""VoiceService — selects and calls the enabled TTS provider (phase 5).

Lives next to ``ConfigurationService`` rather than in ``LifeOpsCore``: it
composes provider configuration and the SecretStore into calls against an
external speech API, and it never reads or writes a person, task, or
preference — LifeOpsCore's world model is untouched.

Only one TTS provider is meant to be enabled at a time; BUILD_SPEC section 29
lets the user choose which through the voice mode setting. ``_FACTORIES``
maps a provider id to the adapter it builds, so a local TTS provider
(phase 6) registers itself here without this class changing.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from lifeops.config.provider_registry import ProviderCategory, providers_in_category
from lifeops.config.service import ConfigurationService, HealthReport
from lifeops.domain.voice import SynthesisOptions, TTSModel, Voice, validate_synthesis_text
from lifeops.errors import ProviderNotConfiguredError
from lifeops.secrets.interface import SecretStore, secret_ref
from lifeops.voice.elevenlabs import ElevenLabsTTSProvider
from lifeops.voice.provider import TTSProvider

ProviderFactory = Callable[[dict[str, Any], SecretStore], TTSProvider]


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
        stability=float(settings.get("stability") or 0.5),
        similarity_boost=float(settings.get("similarity_boost") or 0.75),
        speed=float(settings.get("speed") or 1.0),
    )


_DEFAULT_FACTORIES: dict[str, ProviderFactory] = {"elevenlabs": _build_elevenlabs}


class VoiceService:
    def __init__(
        self,
        *,
        config: ConfigurationService,
        secret_store: SecretStore,
        factories: dict[str, ProviderFactory] | None = None,
    ) -> None:
        self._config = config
        self._secrets = secret_store
        self._factories = factories if factories is not None else _DEFAULT_FACTORIES

    def _active_provider_id(self) -> str | None:
        """The first enabled, fully-configured provider in the voice_tts category.

        "Enabled" and not merely "configured": a provider a user filled in but
        left off must not silently start speaking.
        """
        for definition in providers_in_category(ProviderCategory.VOICE_TTS):
            if definition.id not in self._factories:
                continue
            status = self._config.get_status(definition.id)
            if status.enabled and not status.missing_required:
                return definition.id
        return None

    def _build(self) -> tuple[str, TTSProvider]:
        provider_id = self._active_provider_id()
        if provider_id is None:
            raise ProviderNotConfiguredError(
                "no text-to-speech provider is enabled and fully configured yet"
            )
        status = self._config.get_status(provider_id)
        provider = self._factories[provider_id](status.settings, self._secrets)
        return provider_id, provider

    async def health(self) -> tuple[str, HealthReport]:
        """Raises ``ProviderNotConfiguredError`` rather than recording a health
        entry against a provider nobody has chosen yet."""
        provider_id, provider = self._build()
        healthy, message = await provider.health()
        report = self._config.record_health(provider_id, healthy=healthy, message=message)
        return provider_id, report

    async def list_voices(self) -> list[Voice]:
        _, provider = self._build()
        return await provider.list_voices()

    async def list_models(self) -> list[TTSModel]:
        _, provider = self._build()
        return await provider.list_models()

    async def synthesize(self, text: str, options: SynthesisOptions | None = None) -> bytes:
        clean = validate_synthesis_text(text)
        _, provider = self._build()
        return await provider.synthesize(clean, options or SynthesisOptions())

    def stream(
        self, text: str, options: SynthesisOptions | None = None
    ) -> AsyncIterator[bytes]:
        """Not a coroutine, so a missing provider or bad text raises here and
        now — before a caller has committed to a streaming HTTP response."""
        clean = validate_synthesis_text(text)
        _, provider = self._build()
        return provider.stream(clean, options or SynthesisOptions())
