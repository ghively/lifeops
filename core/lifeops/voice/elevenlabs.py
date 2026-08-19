"""ElevenLabsTTSProvider — the real adapter (BUILD_SPEC section 27).

Talks to the official ElevenLabs REST API over ``httpx``, already a project
dependency (AGENTS.md: no new dependency without written justification). The
API key travels only in the ``xi-api-key`` header and is never logged — this
module never calls ``logging`` with anything derived from the key.

Discovery (voices, models) hits the provider live rather than pinning a
model identifier in code, so a new low-latency ElevenLabs model shows up in
the Console without a LifeOps release (BUILD_SPEC section 27).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from lifeops.domain.voice import SynthesisOptions, TTSModel, Voice
from lifeops.errors import ProviderError

_BASE_URL = "https://api.elevenlabs.io"
_DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
_TIMEOUT_S = 30.0


class ElevenLabsTTSProvider:
    """One configured ElevenLabs voice/model pairing.

    Constructed fresh per call from the currently stored configuration
    (``lifeops.voice.service.VoiceService``) rather than cached across
    requests, so a changed API key or voice takes effect immediately.
    """

    def __init__(
        self,
        *,
        api_key: str,
        voice_id: str | None = None,
        model_id: str | None = None,
        output_format: str = _DEFAULT_OUTPUT_FORMAT,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        speed: float = 1.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._voice_id = voice_id
        self._model_id = model_id
        self._output_format = output_format
        self._stability = stability
        self._similarity_boost = similarity_boost
        self._speed = speed
        self._client = client or httpx.AsyncClient(base_url=_BASE_URL, timeout=_TIMEOUT_S)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        return {"xi-api-key": self._api_key, "accept": "application/json"}

    def _voice_settings(self, options: SynthesisOptions) -> dict[str, float]:
        return {
            "stability": options.stability if options.stability is not None else self._stability,
            "similarity_boost": (
                options.similarity_boost
                if options.similarity_boost is not None
                else self._similarity_boost
            ),
            "speed": options.speed if options.speed is not None else self._speed,
        }

    def _voice_id_for(self, options: SynthesisOptions) -> str:
        voice_id = options.voice_id or self._voice_id
        if not voice_id:
            raise ProviderError(
                "no ElevenLabs voice selected — choose one in Configuration first",
                provider="elevenlabs",
            )
        return voice_id

    def _request_body(self, text: str, options: SynthesisOptions) -> dict[str, Any]:
        model_id = options.model_id or self._model_id
        body: dict[str, Any] = {"text": text, "voice_settings": self._voice_settings(options)}
        if model_id:
            body["model_id"] = model_id
        return body

    async def synthesize(self, text: str, options: SynthesisOptions) -> bytes:
        voice_id = self._voice_id_for(options)
        try:
            response = await self._client.post(
                f"/v1/text-to-speech/{voice_id}",
                json=self._request_body(text, options),
                params={"output_format": options.output_format or self._output_format},
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise _transport_error(exc) from exc
        _raise_for_status(response)
        return response.content

    async def stream(self, text: str, options: SynthesisOptions) -> AsyncIterator[bytes]:
        voice_id = self._voice_id_for(options)
        try:
            async with self._client.stream(
                "POST",
                f"/v1/text-to-speech/{voice_id}/stream",
                json=self._request_body(text, options),
                params={"output_format": options.output_format or self._output_format},
                headers=self._headers(),
            ) as response:
                _raise_for_status(response)
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
        except httpx.HTTPError as exc:
            raise _transport_error(exc) from exc

    async def list_voices(self) -> list[Voice]:
        try:
            response = await self._client.get("/v1/voices", headers=self._headers())
        except httpx.HTTPError as exc:
            raise _transport_error(exc) from exc
        _raise_for_status(response)
        data = response.json()
        return [
            Voice(
                id=entry["voice_id"],
                name=entry.get("name", entry["voice_id"]),
                category=entry.get("category"),
                preview_url=entry.get("preview_url"),
            )
            for entry in data.get("voices", [])
        ]

    async def list_models(self) -> list[TTSModel]:
        try:
            response = await self._client.get("/v1/models", headers=self._headers())
        except httpx.HTTPError as exc:
            raise _transport_error(exc) from exc
        _raise_for_status(response)
        data = response.json()
        return [
            TTSModel(
                id=entry["model_id"],
                name=entry.get("name", entry["model_id"]),
                supports_streaming=bool(entry.get("can_do_text_to_speech_streaming", True)),
            )
            for entry in data
            # Only models ElevenLabs marks usable for TTS belong in a TTS
            # voice/model picker; the same /v1/models list includes others.
            if entry.get("can_do_text_to_speech", True)
        ]

    async def health(self) -> tuple[bool, str]:
        """Is this key usable *for what this provider does* — synthesis?

        The probe is ``/v1/user`` because it is free and side-effect-free;
        a real synthesis call would spend the user's credits every time the
        System screen refreshed. But the question the probe stands in for is
        "can this key synthesise", and those two come apart for a
        permission-scoped key.

        ElevenLabs answers a scoped key with 401 and a body saying
        ``status: missing_permissions``, naming the permission — distinct
        from a genuinely bad key, which has no such marker. Treating both as
        rejection reported a *working* TTS key as unusable: found on a live
        deployment (2026-08-19) with a key scoped to text-to-speech alone,
        where synthesis returned a valid MP3 while the Console showed
        "ElevenLabs rejected the API key" and the provider stayed unhealthy.

        That is the same dishonesty BUILD_SPEC section 88's never-fake-success
        rule guards against, pointed the other way — reporting an absent
        capability that is really present. So a missing permission reports
        healthy and names the limitation, rather than denying the provider
        works.
        """
        try:
            response = await self._client.get("/v1/user", headers=self._headers())
        except httpx.HTTPError as exc:
            return False, f"could not reach ElevenLabs: {exc}"
        if response.status_code == 200:
            return True, "connected"
        if response.status_code == 401:
            missing = _missing_permission(response)
            if missing is not None:
                return True, (
                    "connected — this key is scoped and cannot read account "
                    f"details ({missing}). Synthesis works; voice and model "
                    "discovery will be empty, so set them by hand."
                )
            return False, "ElevenLabs rejected the API key"
        return False, f"ElevenLabs returned HTTP {response.status_code}"


def _missing_permission(response: httpx.Response) -> str | None:
    """The permission name when ElevenLabs refused for scope rather than
    for a bad key, else ``None``.

    Shape (observed live, 2026-08-19)::

        {"detail": {"status": "missing_permissions",
                    "message": "The API key you used is missing the
                                permission voices_read to execute this
                                operation."}}

    Anything unparseable is treated as a genuine rejection: a malformed
    body is not evidence the key is fine.
    """
    try:
        detail = response.json().get("detail")
    except ValueError:
        return None
    if not isinstance(detail, dict):
        return None
    if detail.get("status") != "missing_permissions":
        return None
    message = detail.get("message")
    return message if isinstance(message, str) and message else "permission scope"


def _transport_error(exc: httpx.HTTPError) -> ProviderError:
    """Wrap a connect/timeout failure so the API layer's LifeOpsError
    handling turns it into a structured error, not an unhandled 500 — the
    CalDAV adapter already did this; only ElevenLabs let them escape. The
    message never includes headers, so the API key cannot leak through it."""
    return ProviderError(
        f"ElevenLabs request failed: {exc.__class__.__name__}: {exc}",
        provider="elevenlabs",
    )


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code >= 400:
        raise ProviderError(
            f"ElevenLabs request failed with HTTP {response.status_code}",
            provider="elevenlabs",
            status_code=response.status_code,
        )
