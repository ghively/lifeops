"""Universal search result shape (BUILD_SPEC section 19).

Phase 1 implements case-insensitive substring search over the three domains
that exist so far: people, preferences, tasks. Semantic/BM25 retrieval and
the remaining domains arrive with the memory layer in Phase 2 — the shape is
grouped now so the Console's Search screen does not change when ranking
improves underneath it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from lifeops.domain.people import Person
from lifeops.domain.preferences import Preference
from lifeops.domain.tasks import Task


class SearchResults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    people: list[Person] = Field(default_factory=list)
    preferences: list[Preference] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
