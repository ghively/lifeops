"""Universal search result shape (BUILD_SPEC section 19).

Phase 1 implemented case-insensitive substring search over three domains:
people, preferences, tasks. A later pass widened it to ten of section 19's
twelve categories — providers, assets, appointments, memory, documents,
knowledge, and bills joined them. This pass closes the remaining two:

* ``events`` — BUILD_SPEC's ``Event`` world-entity type already has a real
  projection (``domain/calendar.py``'s ``calendar_event_to_entity``, written
  every time ``read_calendar`` runs), so this is the same
  ``search_full(entity_types=[...])`` pattern providers/assets/appointments
  already use, not new machinery. The earlier reasoning here ("no domain
  wrapper exists") was a false negative — the wrapper existed, search just
  never reached for it.
* ``actions`` and ``historical_facts`` — both map to a concrete, already-
  persisted object after all: ``domain.actions.Action`` (the outbox,
  section 60) and ``domain.audit.AuditRecord`` (section 62's durable log).
  ``GET /audit`` and ``list_actions`` remain the dedicated, full-fidelity
  read surfaces for each; this only adds the same substring filter every
  other category already gets, over a bounded recent window, so a search
  actually surfaces "the appointment because of an action that failed" or
  "why did Hermes do that" without a separate lookup.

Semantic/BM25 retrieval, graph expansion, and ranking remain future work —
this is still a substring match, wider rather than smarter.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from lifeops.domain.actions import Action
from lifeops.domain.audit import AuditRecord
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
    events: list[WorldEntity] = Field(default_factory=list)
    memories: list[MemoryRecord] = Field(default_factory=list)
    documents: list[Document] = Field(default_factory=list)
    knowledge: list[Knowledge] = Field(default_factory=list)
    bills: list[Bill] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)
    historical_facts: list[AuditRecord] = Field(default_factory=list)
