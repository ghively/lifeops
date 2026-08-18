"""Provider definitions and the field-schema registry (BUILD_SPEC section 22).

Providers declare their configuration *shape* in code. The Console renders
forms from those schemas, so adding a provider does not mean writing a new
settings page — and, critically, it does not mean a developer ever needs the
user's API key to finish the work (sections 5 and 88).

A ProviderDefinition is a description, not a client. The adapters that actually
call ElevenLabs or DeepSeek arrive in the phases that need them; what exists
here is enough for the Console to show every provider, collect its settings,
and report it as disabled until the user fills it in.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FieldKind(StrEnum):
    TEXT = "text"
    SECRET = "secret"
    NUMBER = "number"
    BOOLEAN = "boolean"
    SELECT = "select"
    URL = "url"


class ProviderCategory(StrEnum):
    LLM = "llm"
    VOICE_TTS = "voice_tts"
    VOICE_ASR = "voice_asr"
    MESSAGING = "messaging"
    CALENDAR = "calendar"
    EMAIL = "email"
    BROWSER = "browser"
    TELEPHONY = "telephony"


class ProviderState(StrEnum):
    """BUILD_SPEC section 109 item 16.

    NOT_CONFIGURED and DISABLED are distinct on purpose: "I have not set this
    up yet" and "I set it up and turned it off" mean different things to a
    human reading the System screen.
    """

    NOT_CONFIGURED = "not_configured"
    CONFIGURED = "configured"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DISABLED = "disabled"


class ProviderField(BaseModel):
    """One configurable setting on a provider."""

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: FieldKind
    label: str
    required: bool = False
    description: str = ""
    default: Any = None
    placeholder: str | None = None
    # Static choices. Dynamic ones come from options_from, which names a
    # discovery operation the adapter exposes (e.g. ElevenLabs "voices").
    options: list[dict[str, str]] = Field(default_factory=list)
    options_from: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    advanced: bool = False

    @property
    def is_secret(self) -> bool:
        return self.kind is FieldKind.SECRET


def TextField(name: str, label: str, **kw: Any) -> ProviderField:
    return ProviderField(name=name, kind=FieldKind.TEXT, label=label, **kw)


def SecretField(name: str, label: str, **kw: Any) -> ProviderField:
    return ProviderField(name=name, kind=FieldKind.SECRET, label=label, **kw)


def NumberField(name: str, label: str, **kw: Any) -> ProviderField:
    return ProviderField(name=name, kind=FieldKind.NUMBER, label=label, **kw)


def BooleanField(name: str, label: str, **kw: Any) -> ProviderField:
    return ProviderField(name=name, kind=FieldKind.BOOLEAN, label=label, **kw)


def SelectField(name: str, label: str, **kw: Any) -> ProviderField:
    return ProviderField(name=name, kind=FieldKind.SELECT, label=label, **kw)


def UrlField(name: str, label: str, **kw: Any) -> ProviderField:
    return ProviderField(name=name, kind=FieldKind.URL, label=label, **kw)


class ProviderDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: ProviderCategory
    display_name: str
    summary: str
    fields: list[ProviderField] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    # Which phase actually wires the adapter. The Console shows this so a
    # provider that is visible but not yet functional reads as planned work
    # rather than as a bug.
    available_in_phase: int = 0
    docs_url: str | None = None

    def field(self, name: str) -> ProviderField | None:
        return next((f for f in self.fields if f.name == name), None)

    @property
    def secret_fields(self) -> list[ProviderField]:
        return [f for f in self.fields if f.is_secret]

    @property
    def required_fields(self) -> list[ProviderField]:
        return [f for f in self.fields if f.required]


# --- Provider definitions ----------------------------------------------------
# Every provider below ships disabled and unconfigured. A fresh checkout boots
# with all of them in NOT_CONFIGURED and the Console fully reachable
# (BUILD_SPEC section 104).

_ENABLED = BooleanField(
    "enabled",
    "Enabled",
    default=False,
    description="Turn this provider on once its settings are complete.",
)

DEEPSEEK = ProviderDefinition(
    id="deepseek",
    category=ProviderCategory.LLM,
    display_name="DeepSeek",
    summary="Primary language and reasoning engine used by Hermes.",
    available_in_phase=0,
    fields=[
        _ENABLED,
        SecretField("api_key", "API key", required=True, placeholder="sk-..."),
        UrlField(
            "api_base",
            "API endpoint",
            default="https://api.deepseek.com/v1",
            description="OpenAI-compatible base URL.",
        ),
        SelectField(
            "model",
            "Model",
            required=True,
            options_from="models",
            description="Discovered from the provider once the API key is set.",
        ),
        NumberField("timeout_s", "Request timeout (s)", default=60, minimum=1, maximum=600),
        NumberField("max_tokens", "Max tokens", default=4096, minimum=1, advanced=True),
        SelectField("fallback_model", "Fallback model", options_from="models", advanced=True),
    ],
    capabilities=["chat", "streaming_chat"],
)

ELEVENLABS = ProviderDefinition(
    id="elevenlabs",
    category=ProviderCategory.VOICE_TTS,
    display_name="ElevenLabs",
    summary="Fastest path to high-quality streamed speech.",
    available_in_phase=5,
    fields=[
        _ENABLED,
        SecretField("api_key", "API key", required=True),
        SelectField("voice_id", "Voice", required=True, options_from="voices"),
        SelectField(
            "model_id",
            "Model",
            options_from="models",
            description="Discovered at runtime rather than pinned, so a new "
            "low-latency model does not require a code change.",
        ),
        SelectField(
            "output_format",
            "Output format",
            default="mp3_44100_128",
            options=[
                {"value": "mp3_44100_128", "label": "MP3 44.1 kHz 128 kbps"},
                {"value": "pcm_16000", "label": "PCM 16 kHz"},
                {"value": "pcm_24000", "label": "PCM 24 kHz"},
            ],
        ),
        NumberField("stability", "Stability", default=0.5, minimum=0, maximum=1, step=0.05),
        NumberField(
            "similarity_boost", "Similarity boost", default=0.75, minimum=0, maximum=1, step=0.05
        ),
        NumberField("speed", "Speed", default=1.0, minimum=0.5, maximum=2.0, step=0.05),
        BooleanField("streaming", "Stream audio", default=True),
    ],
    capabilities=["tts", "streaming_tts", "list_voices", "list_models", "health_check"],
)

#: Static device choices. No torch/CUDA dependency exists to enumerate the
#: machine's actual GPUs (BUILD_SPEC section 105), so this is a fixed,
#: reasonable list rather than free text — good enough for the Console's
#: device selector today, and cheap to make dynamic later if it matters.
_DEVICE_OPTIONS = [
    {"value": "cpu", "label": "CPU"},
    {"value": "cuda:0", "label": "GPU 0 (cuda:0)"},
    {"value": "cuda:1", "label": "GPU 1 (cuda:1)"},
]

LOCAL_TTS = ProviderDefinition(
    id="local_tts",
    category=ProviderCategory.VOICE_TTS,
    display_name="Local TTS (RTX)",
    summary="GPU-accelerated local speech synthesis.",
    available_in_phase=6,
    fields=[
        _ENABLED,
        SelectField(
            "model",
            "Model",
            required=True,
            options=[{"value": "kokoro", "label": "Kokoro (82M, PyTorch)"}],
            description="BUILD_SPEC section 30 also lists Qwen3-TTS and Chatterbox "
            "Turbo as candidates; only Kokoro has a real adapter wired up so far "
            "(voice.local.LocalTTSProvider) — the others stay unlisted rather than "
            "offered and silently unimplemented.",
        ),
        SelectField(
            "voice",
            "Voice",
            default="af_heart",
            options=[
                {"value": "af_heart", "label": "af_heart (US English, female)"},
                {"value": "af_bella", "label": "af_bella (US English, female)"},
                {"value": "am_michael", "label": "am_michael (US English, male)"},
                {"value": "bf_emma", "label": "bf_emma (British English, female)"},
            ],
            description="A curated subset of Kokoro's voice packs, not the full "
            "catalog — Kokoro's own VOICES.md is the complete list.",
        ),
        SelectField("device", "Device", default="cuda:0", options=_DEVICE_OPTIONS),
        NumberField("speed", "Speed", default=1.0, minimum=0.5, maximum=2.0, step=0.05),
    ],
    capabilities=["tts", "streaming_tts", "health_check"],
)

LOCAL_ASR = ProviderDefinition(
    id="local_asr",
    category=ProviderCategory.VOICE_ASR,
    display_name="Local ASR (RTX)",
    summary="GPU-accelerated local speech recognition.",
    available_in_phase=6,
    fields=[
        _ENABLED,
        SelectField(
            "model",
            "Model",
            required=True,
            options=[
                {"value": "large-v3-turbo", "label": "large-v3-turbo (fast, most accurate)"},
                {
                    "value": "distil-large-v3",
                    "label": "distil-large-v3 (fastest, slightly less accurate)",
                },
                {"value": "large-v3", "label": "large-v3 (most accurate, slower)"},
                {"value": "medium", "label": "medium (lower VRAM)"},
                {"value": "small", "label": "small (CPU-friendly)"},
            ],
            description="BUILD_SPEC section 30 candidates: faster-whisper "
            "large-v3-turbo, faster-whisper distil-large-v3.",
        ),
        SelectField("device", "Device", default="cuda:0", options=_DEVICE_OPTIONS),
        TextField("language", "Language", default="en"),
    ],
    capabilities=["transcribe", "streaming_transcribe", "health_check"],
)

TELEGRAM = ProviderDefinition(
    id="telegram",
    category=ProviderCategory.MESSAGING,
    display_name="Telegram",
    summary="Messaging gateway to Hermes.",
    available_in_phase=1,
    fields=[
        _ENABLED,
        SecretField("bot_token", "Bot token", required=True),
        TextField(
            "allowed_chat_ids",
            "Allowed chat IDs",
            description="Comma-separated. Messages from anyone else are ignored.",
        ),
    ],
    capabilities=["send_message", "receive_message", "health_check"],
)

CALENDAR = ProviderDefinition(
    id="calendar",
    category=ProviderCategory.CALENDAR,
    display_name="Calendar",
    summary="Read availability, hold time, and create events.",
    available_in_phase=7,
    fields=[
        _ENABLED,
        SelectField(
            "backend",
            "Backend",
            required=True,
            options=[
                {"value": "caldav", "label": "CalDAV"},
                {"value": "google", "label": "Google Calendar"},
            ],
        ),
        UrlField("url", "Server URL", description="CalDAV only."),
        TextField("username", "Username"),
        SecretField("password", "Password or app token"),
        SelectField("default_calendar", "Default calendar", options_from="calendars"),
    ],
    capabilities=["read_events", "free_busy", "create_hold", "create_event", "health_check"],
)

EMAIL = ProviderDefinition(
    id="email",
    category=ProviderCategory.EMAIL,
    display_name="Email",
    summary="Read threads and send messages on the user's behalf.",
    available_in_phase=7,
    fields=[
        _ENABLED,
        TextField("imap_host", "IMAP host", required=True),
        NumberField("imap_port", "IMAP port", default=993),
        TextField("smtp_host", "SMTP host", required=True),
        NumberField("smtp_port", "SMTP port", default=587),
        TextField("username", "Username", required=True),
        SecretField("password", "Password or app token"),
        TextField("from_address", "From address"),
    ],
    capabilities=["search", "read_thread", "send", "reply", "health_check"],
)

BROWSER = ProviderDefinition(
    id="browser",
    category=ProviderCategory.BROWSER,
    display_name="Browser",
    summary="Authenticated browsing for sites without a usable API.",
    available_in_phase=9,
    fields=[
        _ENABLED,
        UrlField("endpoint", "Remote browser endpoint", placeholder="ws://127.0.0.1:9222"),
        BooleanField("headless", "Headless", default=True),
        NumberField("timeout_s", "Navigation timeout (s)", default=30),
    ],
    # Contexts stay separated so a shopping session cannot read a billing
    # session's cookies (BUILD_SPEC section 66).
    capabilities=["search", "extract", "interact", "separate_contexts", "health_check"],
)

TELEPHONY = ProviderDefinition(
    id="telephony",
    category=ProviderCategory.TELEPHONY,
    display_name="Telephony",
    summary="Place calls with a constrained objective, over Twilio's REST API.",
    available_in_phase=8,
    fields=[
        _ENABLED,
        TextField("account_sid", "Account SID", required=True, placeholder="AC..."),
        SecretField("auth_token", "Auth token", required=True),
        TextField(
            "from_number",
            "Caller ID (E.164)",
            required=True,
            placeholder="+15551234567",
            description="A phone number or Verified Caller ID on the Twilio account.",
        ),
    ],
    capabilities=["dial", "hangup", "send_dtmf", "get_status", "health_check"],
    docs_url="https://www.twilio.com/docs/voice/api/call-resource",
)


_REGISTRY: dict[str, ProviderDefinition] = {
    p.id: p
    for p in (
        DEEPSEEK,
        ELEVENLABS,
        LOCAL_TTS,
        LOCAL_ASR,
        TELEGRAM,
        CALENDAR,
        EMAIL,
        BROWSER,
        TELEPHONY,
    )
}


def get_provider(provider_id: str) -> ProviderDefinition | None:
    return _REGISTRY.get(provider_id)


def all_providers() -> list[ProviderDefinition]:
    return sorted(_REGISTRY.values(), key=lambda p: (p.category, p.id))


def providers_in_category(category: ProviderCategory) -> list[ProviderDefinition]:
    return [p for p in all_providers() if p.category is category]
