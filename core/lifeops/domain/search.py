"""Universal search result shape (BUILD_SPEC section 19).

Phase 1 implemented case-insensitive substring search over three domains:
people, preferences, tasks. This pass widens it to ten of section 19's
twelve categories — providers, assets, appointments, memory, documents,
knowledge, and bills join them — closing the gap an audit found. Still
missing: "events" (BUILD_SPEC's own Event entity type has no domain wrapper
anywhere in this codebase yet — Phase 7 added the world-graph label but
nothing converts to or from it, so search would have nothing coherent to
return) and "actions"/"historical facts" (neither maps to one concrete
object; the durable audit log already has its own dedicated read surface at
``GET /audit`` rather than needing a second one here). Semantic/BM25
retrieval, graph expansion, and ranking remain future work — this is still
a substring match, wider rather than smarter.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from lifeops.domain.bills import Bill
from lifeops.domain.calendar import Appointment
from lifeops.domain.documents import Document
from lifeops.domain.knowledge import Knowledge
from lifeops.domain.memory import MemoryRecord
from lifeops.domain.people import Person
from lifeops.domain.preferences import Preference
from lifeops.domain.tasks import Task
from lifeops.domain.world import WorldEntity


class SearchResults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    people: list[Person] = Field(default_factory=list)
    preferences: list[Preference] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    providers: list[WorldEntity] = Field(default_factory=list)
    assets: list[WorldEntity] = Field(default_factory=list)
    appointments: list[Appointment] = Field(default_factory=list)
    memories: list[MemoryRecord] = Field(default_factory=list)
    documents: list[Document] = Field(default_factory=list)
    knowledge: list[Knowledge] = Field(default_factory=list)
    bills: list[Bill] = Field(default_factory=list)
