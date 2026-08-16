"""Preference domain model with temporal validity (BUILD_SPEC sections 40, 45, 46).

A preference is never edited in place. Changing one closes the old record's
validity window and opens a new record that SUPERSEDES it. History is the
point: "what did the assistant believe on the day it booked that appointment?"
must stay answerable after the preference changes.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from lifeops.ids import new_preference_id


class PreferenceSource(StrEnum):
    """Where a stated preference came from (BUILD_SPEC section 45).

    The value order matters: it feeds the trust hierarchy in
    ``lifeops.policy.trust``. External content produces evidence, never
    authority.
    """

    USER_EXPLICIT = "user_explicit"
    USER_INFERRED = "user_inferred"
    CONVERSATION = "conversation"
    EMAIL = "email"
    CALENDAR = "calendar"
    DOCUMENT = "document"
    WEBSITE = "website"
    PHONE_CALL = "phone_call"
    SYSTEM = "system"
    AGENT = "agent"


class Preference(BaseModel):
    """One durable statement about how the user wants things done.

    ``key`` is the stable identity of the *topic* (e.g.
    ``scheduling.earliest_appointment_time``). ``value`` is free-form text
    because a personal preference is frequently a sentence rather than a
    scalar, and prematurely typing it would push the nuance into the agent's
    prompt instead of the record.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    subject_id: str
    key: str
    value: str

    source_type: PreferenceSource = PreferenceSource.USER_EXPLICIT
    source_id: str | None = None
    # 0.0-1.0. Explicit user statements are 1.0; inferences arrive lower and
    # are surfaced in the Console for correction rather than acted on silently.
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)

    observed_at: str
    created_at: str
    valid_from: str
    # None means "still true". Every current-state query filters on this.
    valid_to: str | None = None
    supersedes: str | None = None

    created_by_client: str | None = None
    notes: str | None = None

    @property
    def is_current(self) -> bool:
        return self.valid_to is None

    @staticmethod
    def make_id() -> str:
        return new_preference_id()


class PreferenceDraft(BaseModel):
    """Input shape for saving a preference."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=4000)
    subject_id: str | None = None
    source_type: PreferenceSource = PreferenceSource.USER_EXPLICIT
    source_id: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    observed_at: str | None = None
    notes: str | None = None


def normalise_key(key: str) -> str:
    """Canonicalise a preference key.

    Keys are matched exactly when deciding whether a save supersedes an
    existing preference, so ``Scheduling.Earliest `` and
    ``scheduling.earliest`` must not become two competing "current" records.
    """
    cleaned = key.strip().lower().replace(" ", "_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("._")
