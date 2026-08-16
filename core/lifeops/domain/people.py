"""Person domain model (BUILD_SPEC section 36)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from lifeops.ids import PREFIX_PERSON, slug_id


class Person(BaseModel):
    """A human in the user's personal world.

    Phase 0 keeps this deliberately thin. Contact details, household
    membership, and relationships arrive in Phase 3 (World) where they can be
    modelled as graph edges rather than as a widening property bag.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str
    # The single human the assistant primarily acts for. Exactly one Person
    # carries this flag; the repository enforces it.
    is_primary: bool = False
    aliases: list[str] = Field(default_factory=list)
    timezone: str | None = None
    created_at: str
    updated_at: str

    @staticmethod
    def make_id(display_name: str) -> str:
        return slug_id(PREFIX_PERSON, display_name)


class PersonDraft(BaseModel):
    """Input shape for creating a Person."""

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=200)
    is_primary: bool = False
    aliases: list[str] = Field(default_factory=list)
    timezone: str | None = None
