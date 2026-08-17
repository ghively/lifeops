"""Memory domain model with provenance and temporal validity (BUILD_SPEC 42–47).

Memory is the assistant's durable recollection of the user's world: episodes,
facts, candidate preferences, summaries, and associations. Like preferences, a
memory is never edited in place — correction closes the old record's validity
window and opens a new one that SUPERSEDES it, so "what did the assistant
believe when it said that?" stays answerable.

Two invariants live here rather than in the database:

  * BUILD_SPEC section 44 — memory may observe, never rewrite transactional
    reality. ``MemoryDraft`` forbids extra fields, so no caller can smuggle a
    ``task_id`` or ``action_id`` into a write, and ``MemoryRecord`` carries no
    state that tasks, approvals, payments, or idempotency ever read.

  * BUILD_SPEC section 47 — not every utterance deserves permanence.
    ``validate_durable_content`` applies the lightweight promotion rules
    (no filler, no secrets, bounded scores) before anything is persisted.
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from lifeops.domain.preferences import PreferenceSource
from lifeops.errors import ValidationError
from lifeops.ids import new_memory_id


class MemoryType(StrEnum):
    """The five kinds of memory LifeOps keeps (BUILD_SPEC section 45).

    ``PREFERENCE_CANDIDATE`` is deliberately *not* a preference: it is an
    observation that the user might want something, parked for confirmation.
    It is stored under the Memory label and can never be read back through
    the preference surface (section 44).
    """

    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PREFERENCE_CANDIDATE = "preference_candidate"
    SUMMARY = "summary"
    ASSOCIATION = "association"


#: Provenance for a memory is exactly the section 45 source list, which
#: ``PreferenceSource`` already defines and ``policy.trust`` already ranks.
MemorySource = PreferenceSource

_MIN_CONTENT_LENGTH = 4

#: Utterances that carry no durable signal (section 47: conversational filler).
#: Compared against the whole content after case/punctuation normalisation, so
#: "Thanks!" matches but "Thanks for the recommendation, I loved it" does not.
_FILLER_PHRASES = frozenset(
    {
        "ok",
        "okay",
        "k",
        "yes",
        "no",
        "yeah",
        "nah",
        "sure",
        "hi",
        "hey",
        "hello",
        "bye",
        "goodbye",
        "thanks",
        "thank you",
        "hmm",
        "hm",
        "lol",
        "nice",
        "cool",
        "great",
        "got it",
        "i see",
        "never mind",
        "nevermind",
    }
)

_FILLER_NORMALISE = re.compile(r"[^a-z ]+")

#: Heuristics for content that looks like a credential rather than a memory
#: (section 47: never store secrets; section 24 lists the categories). This is
#: a first line of defence, not a secret scanner — real secrets live in the
#: SecretStore and never reach this layer. Mirrors the key names that
#: ``observability.logging`` redacts from log payloads.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        # "password: hunter2", "api_key = sk-...", "bearer: eyJ..."
        r"(?i)\b(password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token"
        r"|bot[_-]?token|secret|bearer|cvv|card[_ -]?number|mfa[_ -]?code|otp)"
        r"\b\s*[:=]\s*\S+",
        # PEM private key material
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        # AWS access key IDs
        r"\bAKIA[0-9A-Z]{16}\b",
        # OpenAI-style API keys
        r"\bsk-[A-Za-z0-9]{20,}\b",
        # Slack tokens
        r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b",
        # GitHub tokens
        r"\bgh[pousr]_[A-Za-z0-9]{20,}\b",
    )
)


def _normalise_utterance(content: str) -> str:
    return _FILLER_NORMALISE.sub("", content.lower()).strip()


def is_filler_content(content: str) -> bool:
    """Whether the content is too thin to deserve permanence (section 47)."""
    stripped = content.strip()
    if len(stripped) < _MIN_CONTENT_LENGTH:
        return True
    return _normalise_utterance(stripped) in _FILLER_PHRASES


def looks_like_secret(content: str) -> bool:
    """Heuristic: does this content resemble a credential?

    Conservative on purpose: it only fires on assignment-shaped or
    well-known-token-shaped content, so "my password manager is Bitwarden"
    stays memorable while "password: hunter2" is refused.
    """
    return any(pattern.search(content) for pattern in _SECRET_PATTERNS)


def validate_durable_content(content: str) -> str:
    """Apply the section 47 promotion rules, returning the cleaned content.

    Raises ValidationError with a stable ``reason`` detail so both the Console
    and an MCP model can tell *why* a memory was refused instead of retrying
    blindly.
    """
    cleaned = content.strip()
    if not cleaned:
        raise ValidationError(
            "memory content must not be empty", field="content", reason="empty_content"
        )
    if is_filler_content(cleaned):
        raise ValidationError(
            "memory content is conversational filler and is not worth keeping",
            field="content",
            reason="filler_content",
        )
    if looks_like_secret(cleaned):
        raise ValidationError(
            "memory content looks like a secret; secrets belong in the SecretStore "
            "and are never stored as memory",
            field="content",
            reason="secret_like_content",
        )
    return cleaned


class MemoryRecord(BaseModel):
    """One durable memory with provenance and a validity window (section 45)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    subject_id: str
    type: MemoryType
    content: str

    source_type: MemorySource = MemorySource.USER_EXPLICIT
    source_id: str | None = None
    # 0.0-1.0. Inferences arrive below 1.0 and are surfaced for correction
    # rather than acted on silently (section 46).
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)

    observed_at: str
    created_at: str
    valid_from: str
    # None means "still believed". Every current-state query filters on this.
    valid_to: str | None = None
    supersedes: str | None = None

    # Entities this memory mentions. Stored as IDs; Phase 3 (World) promotes
    # them to graph edges, as it will for Task.related_entity_ids.
    entity_ids: list[str] = Field(default_factory=list)

    created_by_client: str | None = None
    # Why the window was closed by invalidation. Correction instead records
    # provenance on the superseding record.
    invalidation_reason: str | None = None

    @property
    def is_current(self) -> bool:
        return self.valid_to is None

    @staticmethod
    def make_id() -> str:
        return new_memory_id()


class MemoryDraft(BaseModel):
    """Input shape for remembering.

    ``extra="forbid"`` is part of the section 44 defence: a draft that tries
    to carry a task, action, approval, or payment reference is rejected at
    the boundary instead of being silently ignored.
    """

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=8000)
    type: MemoryType = MemoryType.SEMANTIC
    subject_id: str | None = None
    source_type: MemorySource = MemorySource.CONVERSATION
    source_id: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    observed_at: str | None = None
    entity_ids: list[str] = Field(default_factory=list)
