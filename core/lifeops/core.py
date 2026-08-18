"""LifeOpsCore — the single application service.

Every meaningful state change passes through here (BUILD_SPEC section 3).
Agents do not mutate NornicDB, the Console does not mutate NornicDB, and
integrations do not mutate NornicDB. They call these operations.

The HTTP API and the MCP server are both thin adapters over this class. That
is deliberate: if each surface orchestrated its own repository calls, the
capability checks and state-machine rules would drift apart, and the MCP path
is precisely the one where drift is least visible.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from lifeops.browser.service import BrowserProviderService
from lifeops.calendar.service import CalendarProviderService
from lifeops.clock import Clock, SystemClock, now_iso
from lifeops.domain import shopping as shopping_domain
from lifeops.domain.actions import REQUIRES_APPROVAL as ACTIONS_REQUIRING_APPROVAL
from lifeops.domain.actions import (
    Action,
    ActionDraft,
    ActionStatus,
    ActionType,
    payload_hash,
    record_attempt,
    risk_for_action,
)
from lifeops.domain.actions import prepare as prepare_action
from lifeops.domain.approvals import (
    Approval,
    ApprovalStatus,
    authorises,
)
from lifeops.domain.approvals import consume as consume_approval
from lifeops.domain.approvals import decide as decide_approval
from lifeops.domain.approvals import request as request_approval
from lifeops.domain.audit import AuditRecord
from lifeops.domain.bills import (
    Bill,
    BillDraft,
    BillStatus,
    Payee,
    PayeeDraft,
    may_pay,
    validate_amount,
)
from lifeops.domain.calendar import (
    Appointment,
    AppointmentHoldDraft,
    AppointmentStatus,
    CalendarEvent,
    FreeBusyResult,
    appointment_to_entity,
    calendar_event_to_entity,
    confirm_booking,
    entity_to_appointment,
    hold_is_expired,
)
from lifeops.domain.calendar import cancel_appointment as cancel_appointment_domain
from lifeops.domain.calendar import place_hold as place_hold_domain
from lifeops.domain.documents import (
    Document,
    DocumentDraft,
    document_to_entity,
)
from lifeops.domain.documents import create_document as create_document_domain
from lifeops.domain.email import (
    EmailMessage,
    EmailSendDraft,
    EmailThread,
)
from lifeops.domain.email import build_send_payload as build_send_email_payload
from lifeops.domain.memory import (
    MemoryDraft,
    MemoryRecord,
    MemoryType,
    validate_durable_content,
)
from lifeops.domain.people import Person, PersonDraft
from lifeops.domain.preferences import (
    Preference,
    PreferenceDraft,
    PreferenceSource,
    normalise_key,
)
from lifeops.domain.search import SearchResults
from lifeops.domain.service_request import (
    ServiceRequest,
    ServiceRequestDraft,
    entity_to_service_request,
    service_request_to_entity,
)
from lifeops.domain.service_request import cancel as cancel_service_request
from lifeops.domain.service_request import complete as complete_service_request
from lifeops.domain.service_request import open_request as open_service_request
from lifeops.domain.service_request import record_booked as record_service_booked
from lifeops.domain.service_request import (
    record_booking_requested as record_service_booking_requested,
)
from lifeops.domain.service_request import record_contact as record_service_contact
from lifeops.domain.service_request import record_quote as record_service_quote
from lifeops.domain.service_request import record_waiting as record_service_waiting
from lifeops.domain.shopping import (
    ProductResult,
    ShoppingItem,
    ShoppingList,
    ShoppingListDraft,
    ShoppingListStatus,
    SubstitutionDraft,
    entity_to_shopping_list,
    shopping_list_to_entity,
)
from lifeops.domain.tasks import (
    Task,
    TaskDraft,
    TaskState,
    TaskUpdate,
    VerificationState,
    apply_transition,
)
from lifeops.domain.telephony import CallResult, objective_from_payload
from lifeops.domain.telephony import build_objective as build_call_objective
from lifeops.domain.telephony import call_payload as build_call_payload
from lifeops.domain.waiting import (
    WaitingDraft,
    WaitingItem,
    WaitingStatus,
    next_followup_at,
)
from lifeops.domain.waiting import record_followup as record_followup_rule
from lifeops.domain.waiting import resolve as resolve_waiting
from lifeops.domain.world import (
    EntityDetail,
    EntityDraft,
    EntityHistory,
    WorldEdge,
    WorldEntity,
    WorldEntityType,
    WorldGraph,
    WorldNode,
    WorldRelationship,
    assemble_world_graph,
    is_world_entity_id,
    parse_entity_types,
    parse_relationship,
    validate_facts,
)
from lifeops.email.service import EmailProviderService
from lifeops.errors import (
    ConfigurationError,
    ConflictError,
    NotFoundError,
    ProviderError,
    ValidationError,
    VerificationRequiredError,
)
from lifeops.events import (
    ACTION_CHANGED,
    APPROVAL_CHANGED,
    MEMORY_CHANGED,
    PERSON_CHANGED,
    PREFERENCE_CHANGED,
    TASK_CHANGED,
    WAITING_CHANGED,
    WORLD_CHANGED,
    EventBus,
)
from lifeops.ids import PREFIX_PERSON, slug_id
from lifeops.observability.logging import operation
from lifeops.policy import Capability, ClientIdentity, require
from lifeops.policy.capabilities import capability_for_action
from lifeops.policy.trust import may_supersede
from lifeops.repositories.interfaces import (
    ActionRepository,
    ApprovalRepository,
    AuditRepository,
    BillRepository,
    MemoryRepository,
    PersonRepository,
    PreferenceRepository,
    TaskRepository,
    WaitingRepository,
    WorldRepository,
)
from lifeops.telephony.service import TelephonyProviderService

logger = logging.getLogger(__name__)


class MemoryService:
    """Memory operations (BUILD_SPEC sections 42–47).

    Section 44 is enforced by construction: this service holds only a
    ``MemoryRepository`` (plus clock and event publishing). It has no
    reference to tasks, preferences, approvals, payments, or idempotency
    state, so no memory operation — whatever a caller asks for — can rewrite
    transactional reality. Subject resolution and capability checks stay on
    ``LifeOpsCore``, which delegates here once they pass.
    """

    def __init__(
        self,
        *,
        memories: MemoryRepository,
        clock: Clock,
        publish: Callable[[str], None] | None = None,
    ) -> None:
        self._memories = memories
        self._clock = clock
        self._publish_event = publish

    def _notify(self, memory: MemoryRecord) -> None:
        if self._publish_event is not None:
            self._publish_event(memory.id)

    async def remember(
        self, draft: MemoryDraft, *, subject_id: str, client_id: str
    ) -> MemoryRecord:
        """Persist a memory after the section 47 durability rules pass."""
        content = validate_durable_content(draft.content)

        # Re-stating an identical memory is a no-op rather than a new record,
        # so repeated conversation turns do not pile up duplicates.
        duplicate = await self._memories.get_current_duplicate(
            subject_id, draft.type, content
        )
        if duplicate is not None:
            return duplicate

        now = now_iso(self._clock)
        memory = MemoryRecord(
            id=MemoryRecord.make_id(),
            subject_id=subject_id,
            type=draft.type,
            content=content,
            source_type=draft.source_type,
            source_id=draft.source_id,
            confidence=draft.confidence,
            importance=draft.importance,
            observed_at=draft.observed_at or now,
            created_at=now,
            valid_from=now,
            valid_to=None,
            supersedes=None,
            entity_ids=draft.entity_ids,
            created_by_client=client_id,
        )
        with operation(
            "memory.write",
            memory_type=str(memory.type),
            subject_id=subject_id,
            client_id=client_id,
        ):
            saved = await self._memories.save_superseding(memory, supersedes=None)
        self._notify(saved)
        return saved

    async def recall(
        self,
        *,
        query: str = "",
        subject_id: str | None = None,
        memory_types: list[MemoryType] | None = None,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        """Current memories matching a query; blank query lists the most relevant."""
        if query.strip():
            return await self._memories.search(
                query, subject_id=subject_id, memory_types=memory_types, limit=limit
            )
        return await self._memories.list_current(
            subject_id, memory_types=memory_types, limit=limit
        )

    async def get(self, memory_id: str) -> MemoryRecord:
        memory = await self._memories.get(memory_id)
        if memory is None:
            raise NotFoundError(f"no such memory: {memory_id}", memory_id=memory_id)
        return memory

    async def list_for_entity(
        self, entity_id: str, *, current_only: bool = True, limit: int = 50
    ) -> list[MemoryRecord]:
        """Memories referencing a world entity, newest first.

        Entity-scoped rather than subject-scoped: this is what the Phase 3
        entity inspector and entity history read. It stays a memory operation
        — the world service never gets a memory repository of its own.
        """
        return await self._memories.list_for_entity(
            entity_id, current_only=current_only, limit=limit
        )

    async def history(self, memory_id: str) -> list[MemoryRecord]:
        memory = await self._memories.get(memory_id)
        if memory is None:
            raise NotFoundError(f"no such memory: {memory_id}", memory_id=memory_id)
        return await self._memories.list_history(memory_id)

    async def invalidate(
        self, memory_id: str, *, reason: str | None, client_id: str
    ) -> MemoryRecord:
        """Close a memory's validity window without replacing it."""
        with operation("memory.invalidate", memory_id=memory_id, client_id=client_id):
            updated = await self._memories.invalidate(
                memory_id, at=now_iso(self._clock), reason=reason
            )
        if updated is None:
            raise NotFoundError(f"no such memory: {memory_id}", memory_id=memory_id)
        self._notify(updated)
        return updated

    async def correct(
        self,
        memory_id: str,
        *,
        new_content: str,
        source_type: PreferenceSource,
        confidence: float,
        importance: float | None,
        client_id: str,
    ) -> MemoryRecord:
        """Replace a memory's content through temporal supersession.

        Nothing is edited in place: the old record's window closes and the
        correction opens a new record pointing back with SUPERSEDES.
        """
        existing = await self._memories.get(memory_id)
        if existing is None:
            raise NotFoundError(f"no such memory: {memory_id}", memory_id=memory_id)
        if not existing.is_current:
            raise ConflictError(
                f"memory {memory_id} is already invalidated or superseded; "
                "correct the current version instead",
                memory_id=memory_id,
                reason="memory_not_current",
            )
        # A weaker source may not silently displace a stronger one (section 46).
        if not may_supersede(source_type, existing.source_type):
            raise ConflictError(
                f"memory was recorded from a more authoritative source "
                f"({existing.source_type}); this correction ({source_type}) "
                "cannot replace it",
                memory_id=memory_id,
                existing_source=str(existing.source_type),
                incoming_source=str(source_type),
            )

        content = validate_durable_content(new_content)
        if existing.content == content:
            return existing

        now = now_iso(self._clock)
        correction = MemoryRecord(
            id=MemoryRecord.make_id(),
            subject_id=existing.subject_id,
            type=existing.type,
            content=content,
            source_type=source_type,
            source_id=None,
            confidence=confidence,
            importance=importance if importance is not None else existing.importance,
            observed_at=now,
            created_at=now,
            valid_from=now,
            valid_to=None,
            supersedes=existing.id,
            entity_ids=list(existing.entity_ids),
            created_by_client=client_id,
        )
        with operation(
            "memory.correct",
            memory_id=memory_id,
            supersedes=existing.id,
            client_id=client_id,
        ):
            saved = await self._memories.save_superseding(correction, supersedes=existing)
        self._notify(saved)
        return saved


class WorldService:
    """World-graph operations (BUILD_SPEC sections 36–39, 92).

    Built with the same discipline as ``MemoryService``: it holds only a
    ``WorldRepository``, so no world write can reach tasks, preferences,
    approvals, or payments. The entity inspector does show related tasks and
    memories, but that aggregate is assembled by ``LifeOpsCore`` — which
    already owns those repositories — rather than by widening this service's
    reach to build one read model.

    Capability checks stay on ``LifeOpsCore``, which delegates here once they
    pass.
    """

    def __init__(
        self,
        *,
        world: WorldRepository,
        clock: Clock,
        publish: Callable[[str], None] | None = None,
    ) -> None:
        self._world = world
        self._clock = clock
        self._publish_event = publish

    def _notify(self, entity_id: str) -> None:
        if self._publish_event is not None:
            self._publish_event(entity_id)

    # --- reads ---------------------------------------------------------------

    async def get(self, entity_id: str) -> WorldEntity:
        entity = await self._world.get(entity_id)
        if entity is None:
            raise NotFoundError(f"no such entity: {entity_id}", entity_id=entity_id)
        return entity

    async def graph(
        self,
        *,
        query: str = "",
        entity_types: list[WorldEntityType] | None = None,
        limit: int = 500,
    ) -> WorldGraph:
        """The World screen's graph, narrowed by type filter and search text.

        The text filter is applied to entities before edges are assembled, so
        a search that hides a node also hides the arrows into it rather than
        leaving them pointing at nothing.
        """
        entities = await self._world.list_entities(types=entity_types, limit=limit)
        needle = query.strip().lower()
        if needle:
            entities = [
                entity
                for entity in entities
                if needle in entity.display_name.lower() or needle in entity.id.lower()
            ]
        edges = await self._world.list_edges()
        return assemble_world_graph(entities, edges, limit=limit)

    async def neighborhood(self, entity_id: str, *, depth: int) -> WorldGraph:
        # Resolve the entity first: an unknown id is a 404, not an empty graph
        # that the Console would render as "this thing exists but is lonely".
        await self.get(entity_id)
        entities, edges = await self._world.neighborhood(entity_id, depth=depth)
        return assemble_world_graph(entities, edges, limit=len(entities))

    async def relationships_for(
        self, entity_id: str
    ) -> tuple[list[WorldEdge], list[WorldNode]]:
        """Edges touching an entity, with their far endpoints labelled.

        Only edges between entities the World screen actually renders are
        returned. An ``ABOUT`` edge to a Task, or a ``PREFERS`` edge to a
        superseded preference, is left out — section 16 gives tasks, waiting
        items, documents, and memories their own panels, so repeating them
        here as unlabelled ids would duplicate them badly rather than inform.

        Edges and neighbours are built in one pass so the two can never
        disagree about which relationships the panel is showing.
        """
        edges: list[WorldEdge] = []
        neighbors: dict[str, WorldNode] = {}

        for edge in await self._world.list_edges_for(entity_id):
            other_id = edge.target if edge.source == entity_id else edge.source
            if other_id == entity_id or not is_world_entity_id(other_id):
                continue
            if other_id not in neighbors:
                found = await self._world.get(other_id)
                if found is None:
                    continue
                neighbors[other_id] = WorldNode(
                    id=found.id,
                    entity_type=found.entity_type,
                    label=found.display_name,
                )
            edges.append(edge)

        return edges, list(neighbors.values())

    # --- writes --------------------------------------------------------------

    async def create(self, draft: EntityDraft, *, client_id: str) -> WorldEntity:
        facts = validate_facts(draft.facts)
        display_name = draft.display_name.strip()
        try:
            entity_id = WorldEntity.make_id(draft.entity_type, display_name)
        except ValueError as exc:
            # A name of pure punctuation passes min_length but yields no slug.
            raise ValidationError(str(exc), field="display_name") from None

        if await self._world.exists(entity_id):
            raise ConflictError(
                f"entity {entity_id} already exists", entity_id=entity_id
            )

        now = now_iso(self._clock)
        entity = WorldEntity(
            id=entity_id,
            entity_type=draft.entity_type,
            display_name=display_name,
            facts=facts,
            created_at=now,
            updated_at=now,
            created_by_client=client_id,
        )
        with operation(
            "world.create_entity",
            entity_id=entity_id,
            entity_type=str(draft.entity_type),
            client_id=client_id,
        ):
            created = await self._world.create(entity)
        self._notify(created.id)
        return created

    async def link(
        self,
        source_id: str,
        target_id: str,
        rel_type: WorldRelationship,
        *,
        client_id: str,
    ) -> WorldEdge:
        if source_id == target_id:
            raise ValidationError(
                "an entity cannot be related to itself", field="target_id"
            )
        # Both endpoints are checked before writing so a typo produces a 404
        # rather than an edge into an entity that does not exist.
        for field, entity_id in (("source_id", source_id), ("target_id", target_id)):
            if not await self._world.exists(entity_id):
                raise NotFoundError(
                    f"no such entity: {entity_id}", entity_id=entity_id, field=field
                )

        with operation(
            "world.link",
            source_id=source_id,
            target_id=target_id,
            rel_type=str(rel_type),
            client_id=client_id,
        ):
            edge = await self._world.link(source_id, target_id, rel_type)
        self._notify(source_id)
        return edge

    async def unlink(
        self,
        source_id: str,
        target_id: str,
        rel_type: WorldRelationship,
        *,
        client_id: str,
    ) -> None:
        with operation(
            "world.unlink",
            source_id=source_id,
            target_id=target_id,
            rel_type=str(rel_type),
            client_id=client_id,
        ):
            removed = await self._world.unlink(source_id, target_id, rel_type)
        if not removed:
            raise NotFoundError(
                f"no {rel_type} relationship from {source_id} to {target_id}",
                source_id=source_id,
                target_id=target_id,
                rel_type=str(rel_type),
            )
        self._notify(source_id)


class WaitingService:
    """Waiting items and the due-work lease (BUILD_SPEC sections 13, 54, 55).

    Holds only a ``WaitingRepository``, like the memory and world services.
    Following up on a provider must not be able to move money or rewrite a
    task's state as a side effect; keeping the reach narrow is what makes that
    true by construction rather than by review.
    """

    def __init__(
        self,
        *,
        waiting: WaitingRepository,
        clock: Clock,
        publish: Callable[[str], None] | None = None,
    ) -> None:
        self._waiting = waiting
        self._clock = clock
        self._publish_event = publish

    def _notify(self, waiting_id: str) -> None:
        if self._publish_event is not None:
            self._publish_event(waiting_id)

    async def get(self, waiting_id: str) -> WaitingItem:
        item = await self._waiting.get(waiting_id)
        if item is None:
            raise NotFoundError(
                f"no such waiting item: {waiting_id}", waiting_id=waiting_id
            )
        return item

    async def create(self, draft: WaitingDraft, *, client_id: str) -> WaitingItem:
        now = now_iso(self._clock)
        item = WaitingItem(
            id=WaitingItem.make_id(),
            task_id=draft.task_id,
            subject=draft.subject.strip(),
            waiting_on_entity_id=draft.waiting_on_entity_id,
            waiting_since=now,
            expected_by=draft.expected_by,
            next_action_at=next_followup_at(0, now=now),
            max_followups=draft.max_followups,
            created_by_client=client_id,
        )
        with operation("waiting.create", waiting_id=item.id, client_id=client_id):
            created = await self._waiting.create(item)
        self._notify(created.id)
        return created

    async def list(
        self, *, statuses: list[WaitingStatus] | None = None, limit: int = 100
    ) -> list[WaitingItem]:
        return await self._waiting.list_by_status(statuses=statuses, limit=limit)

    async def list_for_task(self, task_id: str) -> list[WaitingItem]:
        return await self._waiting.list_for_task(task_id)

    async def record_followup(self, waiting_id: str, *, client_id: str) -> WaitingItem:
        item = await self.get(waiting_id)
        updated = record_followup_rule(item, now=now_iso(self._clock))
        with operation(
            "waiting.followup",
            waiting_id=waiting_id,
            followup_count=updated.followup_count,
            status=str(updated.status),
            client_id=client_id,
        ):
            saved = await self._waiting.update(updated)
        self._notify(saved.id)
        return saved

    async def resolve(self, waiting_id: str, *, client_id: str) -> WaitingItem:
        item = await self.get(waiting_id)
        with operation("waiting.resolve", waiting_id=waiting_id, client_id=client_id):
            saved = await self._waiting.update(resolve_waiting(item, now=now_iso(self._clock)))
        self._notify(saved.id)
        return saved

    async def due(self, *, limit: int = 50) -> list[WaitingItem]:
        return await self._waiting.list_due(now=now_iso(self._clock), limit=limit)

    async def claim(
        self, waiting_id: str, *, owner: str, lease_seconds: int = 300
    ) -> WaitingItem | None:
        """Take the lease, or return None when another worker already holds it."""
        from datetime import datetime, timedelta

        now = now_iso(self._clock)
        until = (
            datetime.fromisoformat(now.replace("Z", "+00:00"))
            + timedelta(seconds=lease_seconds)
        ).isoformat().replace("+00:00", "Z")
        return await self._waiting.claim(waiting_id, owner=owner, until=until, now=now)


class ActionService:
    """The action outbox and its approvals (BUILD_SPEC sections 57-61).

    Actions and approvals live in one service because section 57's
    PREPARE -> APPROVE -> COMMIT -> VERIFY is a single flow: an approval that
    could be granted without reference to the action it authorises would not be
    an approval of anything. Splitting them would put the binding check on the
    caller, which is exactly where it must not be.
    """

    def __init__(
        self,
        *,
        actions: ActionRepository,
        approvals: ApprovalRepository,
        clock: Clock,
        publish: Callable[[str, str], None] | None = None,
    ) -> None:
        self._actions = actions
        self._approvals = approvals
        self._clock = clock
        self._publish_event = publish

    def _notify(self, kind: str, entity_id: str) -> None:
        if self._publish_event is not None:
            self._publish_event(kind, entity_id)

    async def get(self, action_id: str) -> Action:
        action = await self._actions.get(action_id)
        if action is None:
            raise NotFoundError(f"no such action: {action_id}", action_id=action_id)
        return action

    async def prepare(self, draft: ActionDraft, *, client_id: str) -> Action:
        """Persist the intent before anything external happens (section 60).

        An identical intent already recorded is returned as-is rather than
        duplicated: two Actions carrying one idempotency key would be two
        chances to book the same appointment.
        """
        now = now_iso(self._clock)
        candidate = prepare_action(draft, now=now, client_id=client_id)

        existing = await self._actions.get_by_idempotency_key(candidate.idempotency_key)
        if existing is not None and existing.is_live:
            return existing

        with operation(
            "action.prepare",
            action_id=candidate.id,
            action_type=str(candidate.type),
            client_id=client_id,
        ):
            created = await self._actions.create(candidate)

        if created.status is ActionStatus.NEEDS_APPROVAL:
            approval = request_approval(created, now=now, requested_by=client_id)
            await self._approvals.create(approval)
            self._notify(APPROVAL_CHANGED, approval.id)

        self._notify(ACTION_CHANGED, created.id)
        return created

    async def list(
        self, *, statuses: list[ActionStatus] | None = None, limit: int = 100
    ) -> list[Action]:
        return await self._actions.list_by_status(statuses=statuses, limit=limit)

    async def pending_approvals(self, *, limit: int = 50) -> list[Approval]:
        return await self._approvals.list_pending(limit=limit)

    async def approval_for(self, action_id: str) -> Approval | None:
        return await self._approvals.get_for_action(action_id)

    async def decide(
        self, approval_id: str, *, approved: bool, by: str
    ) -> Approval:
        """Record a human decision and move the action with it."""
        approval = await self._approvals.get(approval_id)
        if approval is None:
            raise NotFoundError(
                f"no such approval: {approval_id}", approval_id=approval_id
            )
        now = now_iso(self._clock)
        decided = decide_approval(approval, approved=approved, by=by, now=now)

        with operation(
            "approval.decide",
            approval_id=approval_id,
            status=str(decided.status),
            client_id=by,
        ):
            saved = await self._approvals.update(decided)

        action = await self._actions.get(saved.action_id)
        if action is not None:
            if saved.status is ApprovalStatus.APPROVED:
                action.status = ActionStatus.APPROVED
            elif saved.status is ApprovalStatus.DECLINED:
                action.status = ActionStatus.CANCELLED
                action.failure_reason = "declined by the user"
            await self._actions.update(action)
            self._notify(ACTION_CHANGED, action.id)

        self._notify(APPROVAL_CHANGED, saved.id)
        return saved

    async def begin_commit(self, action_id: str, *, client_id: str) -> Action:
        """Clear an action to go out, spending its approval (section 57).

        The approval is re-checked against the action's *current* payload hash,
        so a payload edited after approval no longer matches and the commit is
        refused. That is "material change invalidates approval" enforced rather
        than documented.
        """
        action = await self.get(action_id)
        now = now_iso(self._clock)

        if action.type in ACTIONS_REQUIRING_APPROVAL:
            approval = await self._approvals.get_for_action(action.id)
            if approval is None or not authorises(approval, action, now=now):
                raise ConflictError(
                    f"action {action.id} has no valid approval for its current payload",
                    action_id=action.id,
                    reason="approval_required",
                )
            await self._approvals.update(consume_approval(approval, now=now))
            self._notify(APPROVAL_CHANGED, approval.id)

        with operation(
            "action.commit",
            action_id=action.id,
            action_type=str(action.type),
            attempt=action.attempt_count + 1,
            client_id=client_id,
        ):
            saved = await self._actions.update(record_attempt(action, now=now))
        self._notify(ACTION_CHANGED, saved.id)
        return saved

    async def update_payload(
        self, action_id: str, *, payload: dict[str, object], client_id: str
    ) -> Action:
        """Replace a live action's payload, recomputing its hash (section 57).

        Exists for flows where the *plan* an already-prepared Action carries
        can still change before it commits — section 98's substitutions being
        the first: a substitution applied to a cart after a human approved
        checkout must not ride through on that approval. Recomputing the hash
        is what ``begin_commit`` checks against the stored approval, so a
        stale approval is refused there automatically; this method also
        requests a fresh approval immediately, so the Console has something
        to decide rather than a checkout silently stuck with no valid one.

        Refuses once the action is no longer live: a finished action's record
        of what actually happened must not be rewritten after the fact.
        """
        action = await self.get(action_id)
        if not action.is_live:
            raise ConflictError(
                f"action {action.id} is {action.status}; its payload can no "
                "longer be changed",
                action_id=action.id,
                reason="not_live",
            )
        now = now_iso(self._clock)
        action.payload = dict(payload)
        action.payload_hash = payload_hash(payload)
        if action.type in ACTIONS_REQUIRING_APPROVAL:
            action.status = ActionStatus.NEEDS_APPROVAL
            approval = request_approval(action, now=now, requested_by=client_id)
            await self._approvals.create(approval)
            self._notify(APPROVAL_CHANGED, approval.id)
        with operation(
            "action.update_payload", action_id=action.id, client_id=client_id
        ):
            saved = await self._actions.update(action)
        self._notify(ACTION_CHANGED, saved.id)
        return saved

    async def record_result(
        self,
        action_id: str,
        *,
        succeeded: bool,
        external_reference: str | None = None,
        failure_reason: str | None = None,
    ) -> Action:
        """Persist what the external system said (section 60 step 3)."""
        action = await self.get(action_id)
        action.status = ActionStatus.EXECUTED if succeeded else ActionStatus.FAILED
        action.external_reference = external_reference
        action.failure_reason = failure_reason
        saved = await self._actions.update(action)
        self._notify(ACTION_CHANGED, saved.id)
        return saved

    async def verify(self, action_id: str, *, evidence: str) -> Action:
        """Confirm the thing actually happened (section 6).

        Executed is not verified: an accepted request is a claim, and evidence
        from the target system is what turns it into a fact.
        """
        action = await self.get(action_id)
        if action.status is not ActionStatus.EXECUTED:
            raise ConflictError(
                f"action {action.id} is {action.status}; only an executed action "
                "can be verified",
                action_id=action.id,
                reason="not_executed",
            )
        action.status = ActionStatus.VERIFIED
        action.verification_state = VerificationState.VERIFIED
        action.external_reference = action.external_reference or evidence
        saved = await self._actions.update(action)
        self._notify(ACTION_CHANGED, saved.id)
        return saved


class AppointmentService:
    """Calendar reads and the appointment lifecycle (BUILD_SPEC sections 63,
    96), following section 63's mandatory order: read, free/busy, hold,
    create, update, cancel.

    Holds two dependencies rather than one, unlike the other services in this
    module: ``world`` for the local Appointment/CalendarEvent record and
    ``calendar`` for the actual provider call. Both are needed for the same
    reason ``ActionService`` holds actions and approvals together — placing a
    hold or booking a slot is one operation with an external half and a local
    half, and splitting them across two callers is how the external half gets
    forgotten.

    ``execute_booking`` and ``execute_cancellation`` are called only from
    ``LifeOpsCore.execute_action``, after an Action has been committed. This
    class never calls ``prepare_action`` or ``verify_action`` itself — the
    outbox is Phase 4's, and this consumes it rather than re-implementing it.
    """

    def __init__(
        self,
        *,
        world: WorldRepository,
        calendar: CalendarProviderService,
        clock: Clock,
        publish: Callable[[str], None] | None = None,
    ) -> None:
        self._world = world
        self._calendar = calendar
        self._clock = clock
        self._publish_event = publish

    def _notify(self, entity_id: str) -> None:
        if self._publish_event is not None:
            self._publish_event(entity_id)

    async def get(self, appointment_id: str) -> Appointment:
        entity = await self._world.get(appointment_id)
        if entity is None:
            raise NotFoundError(
                f"no such appointment: {appointment_id}", appointment_id=appointment_id
            )
        return entity_to_appointment(entity)

    async def list(
        self, *, status: AppointmentStatus | None = None, task_id: str | None = None
    ) -> list[Appointment]:
        entities = await self._world.list_entities(types=[WorldEntityType.APPOINTMENT])
        appointments = [entity_to_appointment(e) for e in entities]
        if status is not None:
            appointments = [a for a in appointments if a.status is status]
        if task_id is not None:
            appointments = [a for a in appointments if a.task_id == task_id]
        return sorted(appointments, key=lambda a: a.start_at)

    # --- section 63 step 1-2: read ------------------------------------------

    async def read_calendar(self, *, start_at: str, end_at: str) -> list[CalendarEvent]:
        events = await self._calendar.list_events(start_at=start_at, end_at=end_at)
        now = now_iso(self._clock)
        for event in events:
            # Upsert, not append: reading the same window twice must not
            # duplicate the node (module docstring — the id is deterministic).
            await self._world.create(calendar_event_to_entity(event, now=now))
        return events

    async def free_busy(self, *, start_at: str, end_at: str) -> FreeBusyResult:
        slots = await self._calendar.free_busy(start_at=start_at, end_at=end_at)
        return FreeBusyResult(start_at=start_at, end_at=end_at, slots=slots)

    # --- section 63 step 3: hold ---------------------------------------------

    async def hold(self, draft: AppointmentHoldDraft, *, client_id: str) -> Appointment:
        hold_reference = await self._calendar.create_hold(
            subject=draft.subject,
            start_at=draft.start_at,
            end_at=draft.end_at,
            notes=draft.notes,
        )
        now = now_iso(self._clock)
        appointment = place_hold_domain(
            draft, now=now, client_id=client_id, hold_reference=hold_reference
        )
        await self._world.create(appointment_to_entity(appointment))
        self._notify(appointment.id)
        return appointment

    # --- section 63 steps 4 and 6: execution, called from execute_action ----

    async def execute_booking(self, action: Action) -> tuple[str, str]:
        appointment_id = action.payload.get("appointment_id")
        if not appointment_id:
            raise ValidationError(
                "a book_appointment action needs appointment_id in its payload",
                action_id=action.id,
            )
        appointment = await self.get(str(appointment_id))
        now = now_iso(self._clock)
        if appointment.status is not AppointmentStatus.HELD:
            raise ValidationError(
                f"appointment {appointment_id} is {appointment.status}, not held; "
                "it cannot be booked",
                appointment_id=appointment_id,
            )
        if hold_is_expired(appointment, now=now):
            raise ValidationError(
                f"the hold for appointment {appointment_id} expired at "
                f"{appointment.hold_expires_at}",
                appointment_id=appointment_id,
            )
        external_id = await self._calendar.create_event(
            subject=str(action.payload.get("subject") or appointment.subject),
            start_at=str(action.payload.get("start_at") or appointment.start_at),
            end_at=str(action.payload.get("end_at") or appointment.end_at),
            location=str(action.payload.get("location") or appointment.location),
            notes=str(action.payload.get("notes") or appointment.notes),
            hold_reference=appointment.hold_reference,
        )
        return external_id, f"created via calendar provider: {external_id}"

    async def execute_cancellation(self, action: Action) -> tuple[str, str]:
        appointment_id = action.payload.get("appointment_id")
        if not appointment_id:
            raise ValidationError(
                "a cancel_appointment action needs appointment_id in its payload",
                action_id=action.id,
            )
        appointment = await self.get(str(appointment_id))
        if appointment.is_terminal:
            raise ValidationError(
                f"appointment {appointment_id} is already {appointment.status}",
                appointment_id=appointment_id,
            )
        reference = appointment.external_event_id or appointment.hold_reference
        if not reference:
            raise ValidationError(
                f"appointment {appointment_id} has no calendar reference to cancel",
                appointment_id=appointment_id,
            )
        await self._calendar.cancel_event(reference)
        return reference, f"cancelled via calendar provider: {reference}"

    # --- independent confirmation, called from verify_action_externally ----

    async def confirm_evidence(self, external_event_id: str) -> tuple[bool, str]:
        event = await self._calendar.get_event(external_event_id)
        if event is None:
            return False, f"no event {external_event_id!r} found on the calendar"
        return True, f"confirmed on the calendar: {event.external_event_id} ({event.title})"

    async def confirm_cancellation_evidence(self, external_event_id: str) -> tuple[bool, str]:
        event = await self._calendar.get_event(external_event_id)
        if event is not None:
            return False, f"event {external_event_id!r} is still on the calendar"
        return True, f"confirmed absent from the calendar: {external_event_id}"

    # --- local state sync, called only after verify_action succeeds --------

    async def mark_booked(
        self, appointment_id: str, *, external_event_id: str, action_id: str, now: str
    ) -> Appointment:
        appointment = await self.get(appointment_id)
        updated = confirm_booking(
            appointment, external_event_id=external_event_id, action_id=action_id, now=now
        )
        await self._world.create(appointment_to_entity(updated))
        self._notify(updated.id)
        return updated

    async def mark_cancelled(
        self, appointment_id: str, *, action_id: str, now: str
    ) -> Appointment:
        appointment = await self.get(appointment_id)
        updated = cancel_appointment_domain(appointment, action_id=action_id, now=now)
        await self._world.create(appointment_to_entity(updated))
        self._notify(updated.id)
        return updated


class ShoppingService:
    """Grocery search, cart building, and checkout (BUILD_SPEC section 98).

    Holds two dependencies, the same shape ``AppointmentService`` uses for
    calendar + world: ``world`` for the durable ``ShoppingList`` record and
    ``browser`` for the actual site interaction. ``execute_cart_build`` and
    ``execute_checkout`` are called only from ``LifeOpsCore.execute_action``,
    after an Action has been committed — this class never calls
    ``prepare_action`` or ``verify_action`` itself, the discipline
    ``AppointmentService`` documents for the identical reason.
    """

    def __init__(
        self,
        *,
        world: WorldRepository,
        browser: BrowserProviderService,
        clock: Clock,
        publish: Callable[[str], None] | None = None,
    ) -> None:
        self._world = world
        self._browser = browser
        self._clock = clock
        self._publish_event = publish

    def _notify(self, entity_id: str) -> None:
        if self._publish_event is not None:
            self._publish_event(entity_id)

    async def get(self, list_id: str) -> ShoppingList:
        entity = await self._world.get(list_id)
        if entity is None:
            raise NotFoundError(
                f"no such shopping list: {list_id}", shopping_list_id=list_id
            )
        return entity_to_shopping_list(entity)

    async def list(
        self,
        *,
        status: ShoppingListStatus | None = None,
        task_id: str | None = None,
    ) -> list[ShoppingList]:
        entities = await self._world.list_entities(types=[WorldEntityType.SHOPPING_LIST])
        lists = [entity_to_shopping_list(e) for e in entities]
        if status is not None:
            lists = [item for item in lists if item.status is status]
        if task_id is not None:
            lists = [item for item in lists if item.task_id == task_id]
        return sorted(lists, key=lambda item: item.created_at, reverse=True)

    async def create(self, draft: ShoppingListDraft, *, client_id: str) -> ShoppingList:
        now = now_iso(self._clock)
        shopping_list = shopping_domain.create(draft, now=now, client_id=client_id)
        await self._world.create(shopping_list_to_entity(shopping_list))
        self._notify(shopping_list.id)
        return shopping_list

    async def add_items(
        self, list_id: str, items: list[ShoppingItem], *, client_id: str
    ) -> ShoppingList:
        current = await self.get(list_id)
        updated = shopping_domain.add_items(current, items, now=now_iso(self._clock))
        await self._world.create(shopping_list_to_entity(updated))
        self._notify(updated.id)
        return updated

    async def apply_substitution(
        self, list_id: str, draft: SubstitutionDraft, *, client_id: str
    ) -> ShoppingList:
        """Update the plan. Whether a live checkout Action's payload must be
        refreshed with it — invalidating a stale approval (section 57) — is
        decided by ``LifeOpsCore.apply_substitution``, which holds the Action
        state this service does not."""
        current = await self.get(list_id)
        updated = shopping_domain.apply_substitution(
            current, draft, now=now_iso(self._clock)
        )
        await self._world.create(shopping_list_to_entity(updated))
        self._notify(updated.id)
        return updated

    async def search(
        self, query: str, *, store: str = "", limit: int = 10
    ) -> list[ProductResult]:
        return await self._browser.search(query, store=store, limit=limit)

    # --- section 98 steps: execution, called from execute_action -------------

    async def execute_cart_build(self, action: Action) -> tuple[str, str]:
        list_id = action.payload.get("shopping_list_id")
        if not list_id:
            raise ValidationError(
                "a build_grocery_cart action needs shopping_list_id in its payload",
                action_id=action.id,
            )
        shopping_list = await self.get(str(list_id))
        items = [ShoppingItem(**item) for item in (action.payload.get("items") or [])]
        result = await self._browser.build_cart(
            store=str(action.payload.get("store") or shopping_list.store), items=items
        )
        return result.cart_reference, f"cart built via browser worker: {result.cart_reference}"

    async def execute_checkout(self, action: Action) -> tuple[str, str]:
        list_id = action.payload.get("shopping_list_id")
        if not list_id:
            raise ValidationError(
                "a submit_grocery_order action needs shopping_list_id in its payload",
                action_id=action.id,
            )
        shopping_list = await self.get(str(list_id))
        cart_reference = action.payload.get("cart_reference") or shopping_list.cart_reference
        if not cart_reference:
            raise ValidationError(
                f"shopping list {list_id} has no cart to check out", action_id=action.id
            )
        items = [ShoppingItem(**item) for item in (action.payload.get("items") or [])]
        result = await self._browser.submit_order(
            store=str(action.payload.get("store") or shopping_list.store),
            cart_reference=str(cart_reference),
            items=items,
        )
        return (
            result.order_reference,
            f"order submitted via browser worker: {result.order_reference}",
        )

    # --- independent confirmation, called from verify_action_externally -----

    async def confirm_cart_evidence(
        self, action: Action, cart_reference: str
    ) -> tuple[bool, str]:
        store = await self._store_for(action)
        return await self._browser.confirm_cart(store=store, cart_reference=cart_reference)

    async def confirm_order_evidence(
        self, action: Action, order_reference: str
    ) -> tuple[bool, str]:
        store = await self._store_for(action)
        return await self._browser.confirm_order(store=store, order_reference=order_reference)

    async def _store_for(self, action: Action) -> str:
        store = str(action.payload.get("store") or "")
        list_id = action.payload.get("shopping_list_id")
        if not store and list_id:
            shopping_list = await self.get(str(list_id))
            store = shopping_list.store
        return store

    # --- local state sync, called only after verify_action succeeds ---------

    async def mark_cart_building(
        self, list_id: str, *, action_id: str, now: str
    ) -> ShoppingList:
        shopping_list = await self.get(list_id)
        updated = shopping_domain.mark_cart_building(
            shopping_list, action_id=action_id, now=now
        )
        await self._world.create(shopping_list_to_entity(updated))
        self._notify(updated.id)
        return updated

    async def mark_cart_built(
        self, list_id: str, *, cart_reference: str, total_estimate: str | None, now: str
    ) -> ShoppingList:
        shopping_list = await self.get(list_id)
        updated = shopping_domain.mark_cart_built(
            shopping_list, cart_reference=cart_reference, total_estimate=total_estimate, now=now
        )
        await self._world.create(shopping_list_to_entity(updated))
        self._notify(updated.id)
        return updated

    async def mark_cart_failed(self, list_id: str, *, now: str) -> ShoppingList:
        shopping_list = await self.get(list_id)
        updated = shopping_domain.mark_cart_failed(shopping_list, now=now)
        await self._world.create(shopping_list_to_entity(updated))
        self._notify(updated.id)
        return updated

    async def mark_submitting(
        self, list_id: str, *, action_id: str, now: str
    ) -> ShoppingList:
        shopping_list = await self.get(list_id)
        updated = shopping_domain.mark_submitting(shopping_list, action_id=action_id, now=now)
        await self._world.create(shopping_list_to_entity(updated))
        self._notify(updated.id)
        return updated

    async def mark_order_verified(
        self, list_id: str, *, order_reference: str, now: str
    ) -> ShoppingList:
        shopping_list = await self.get(list_id)
        updated = shopping_domain.mark_submitted(
            shopping_list, order_reference=order_reference, now=now
        )
        updated = shopping_domain.mark_verified(updated, now=now)
        await self._world.create(shopping_list_to_entity(updated))
        self._notify(updated.id)
        return updated


class ServiceRequestService:
    """The section 67 provider workflow record (BUILD_SPEC sections 36, 97,
    101), following ``AppointmentService``'s shape: a ``WorldRepository`` for
    the local record, projected the same way ``Appointment`` is rather than
    through a dedicated repository — there is nothing this record needs that
    ``WorldEntity.facts`` cannot carry (section 105: no infrastructure this
    workflow does not need).

    Holds no reference to ``ActionService`` or ``WaitingService``: those stay
    on ``LifeOpsCore``, which already orchestrates actions, approvals, and
    waiting items, so a service request records their *ids* rather than
    re-implementing calls into them.
    """

    def __init__(
        self,
        *,
        world: WorldRepository,
        clock: Clock,
        publish: Callable[[str], None] | None = None,
    ) -> None:
        self._world = world
        self._clock = clock
        self._publish_event = publish

    def _notify(self, entity_id: str) -> None:
        if self._publish_event is not None:
            self._publish_event(entity_id)

    async def get(self, service_request_id: str) -> ServiceRequest:
        entity = await self._world.get(service_request_id)
        if entity is None:
            raise NotFoundError(
                f"no such service request: {service_request_id}",
                service_request_id=service_request_id,
            )
        return entity_to_service_request(entity)

    async def list(self, *, task_id: str | None = None) -> list[ServiceRequest]:
        entities = await self._world.list_entities(types=[WorldEntityType.SERVICE_REQUEST])
        requests = [entity_to_service_request(e) for e in entities]
        if task_id is not None:
            requests = [r for r in requests if r.task_id == task_id]
        return sorted(requests, key=lambda r: r.created_at, reverse=True)

    async def _save(self, request: ServiceRequest) -> ServiceRequest:
        await self._world.create(service_request_to_entity(request))
        self._notify(request.id)
        return request

    async def open(self, draft: ServiceRequestDraft, *, client_id: str) -> ServiceRequest:
        """Section 101 step 1: identify the relevant asset, and open the
        record research starts from."""
        now = now_iso(self._clock)
        request = open_service_request(draft, now=now, client_id=client_id)
        return await self._save(request)

    async def record_contact(
        self, service_request_id: str, *, action_id: str, provider_entity_id: str | None
    ) -> ServiceRequest:
        """Section 101 steps 5-6: a call or quote request went out."""
        request = await self.get(service_request_id)
        updated = record_service_contact(
            request,
            action_id=action_id,
            provider_entity_id=provider_entity_id,
            now=now_iso(self._clock),
        )
        return await self._save(updated)

    async def record_waiting(
        self, service_request_id: str, *, waiting_item_id: str
    ) -> ServiceRequest:
        """Section 101 step 8: create a waiting item when necessary."""
        request = await self.get(service_request_id)
        updated = record_service_waiting(
            request, waiting_item_id=waiting_item_id, now=now_iso(self._clock)
        )
        return await self._save(updated)

    async def record_quote(
        self,
        service_request_id: str,
        *,
        availability: list[str] | None = None,
        diagnostic_fee: str | None = None,
    ) -> ServiceRequest:
        """Section 101 steps 6-7: availability and the diagnostic fee."""
        request = await self.get(service_request_id)
        updated = record_service_quote(
            request,
            availability=availability,
            diagnostic_fee=diagnostic_fee,
            now=now_iso(self._clock),
        )
        return await self._save(updated)

    async def record_booking_requested(
        self, service_request_id: str, *, action_id: str
    ) -> ServiceRequest:
        """Section 101 step 10: prepare booking."""
        request = await self.get(service_request_id)
        updated = record_service_booking_requested(
            request, action_id=action_id, now=now_iso(self._clock)
        )
        return await self._save(updated)

    async def record_booked(
        self, service_request_id: str, *, appointment_id: str
    ) -> ServiceRequest:
        """Section 101 step 13: called only after the booking is
        independently verified, never merely because it executed."""
        request = await self.get(service_request_id)
        updated = record_service_booked(
            request, appointment_id=appointment_id, now=now_iso(self._clock)
        )
        return await self._save(updated)

    async def complete(self, service_request_id: str) -> ServiceRequest:
        """Section 101 step 16: complete only after verification."""
        request = await self.get(service_request_id)
        updated = complete_service_request(request, now=now_iso(self._clock))
        return await self._save(updated)

    async def cancel(self, service_request_id: str) -> ServiceRequest:
        request = await self.get(service_request_id)
        updated = cancel_service_request(request, now=now_iso(self._clock))
        return await self._save(updated)


class LifeOpsCore:
    def __init__(
        self,
        *,
        people: PersonRepository,
        preferences: PreferenceRepository,
        tasks: TaskRepository,
        memory: MemoryRepository | None = None,
        world: WorldRepository | None = None,
        waiting: WaitingRepository | None = None,
        actions: ActionRepository | None = None,
        approvals: ApprovalRepository | None = None,
        audit: AuditRepository | None = None,
        bills: BillRepository | None = None,
        calendar: CalendarProviderService | None = None,
        email: EmailProviderService | None = None,
        telephony: TelephonyProviderService | None = None,
        browser: BrowserProviderService | None = None,
        clock: Clock | None = None,
        safe_mode: bool = False,
        events: EventBus | None = None,
    ) -> None:
        self._people = people
        self._preferences = preferences
        self._tasks = tasks
        # Kept alongside ``_world_service`` (not instead of it) for the one
        # flow — documents — that builds a ``WorldEntity`` directly rather
        # than through ``EntityDraft``, the same reason ``AppointmentService``
        # above takes ``world`` as its own dependency.
        self._world_repo = world
        self._clock = clock or SystemClock()
        self.safe_mode = safe_mode
        self._events = events
        # Memory is deliberately segregated behind its own service (section
        # 44): nothing here hands it the task or preference repositories.
        self._memory_service = (
            MemoryService(
                memories=memory,
                clock=self._clock,
                publish=(
                    lambda memory_id: self._publish(MEMORY_CHANGED, memory_id=memory_id)
                ),
            )
            if memory is not None
            else None
        )
        self._world_service = (
            WorldService(
                world=world,
                clock=self._clock,
                publish=(
                    lambda entity_id: self._publish(WORLD_CHANGED, entity_id=entity_id)
                ),
            )
            if world is not None
            else None
        )
        self._waiting_service = (
            WaitingService(
                waiting=waiting,
                clock=self._clock,
                publish=(
                    lambda waiting_id: self._publish(
                        WAITING_CHANGED, waiting_id=waiting_id
                    )
                ),
            )
            if waiting is not None
            else None
        )
        # Actions and approvals are one service: section 57's two-phase commit
        # is a single flow, and an approval that cannot see its action cannot
        # bind to it.
        self._action_service = (
            ActionService(
                actions=actions,
                approvals=approvals,
                clock=self._clock,
                publish=(lambda kind, entity_id: self._publish(kind, id=entity_id)),
            )
            if actions is not None and approvals is not None
            else None
        )
        self._audit_repo = audit
        self._bills_repo = bills
        # Calendar/email (Phase 7, section 96) need both a persistence path
        # (``world``) and a provider adapter (``calendar``), the same
        # two-dependency shape ``ActionService`` uses for actions+approvals.
        self._appointment_service = (
            AppointmentService(
                world=world,
                calendar=calendar,
                clock=self._clock,
                publish=(
                    lambda entity_id: self._publish(WORLD_CHANGED, entity_id=entity_id)
                ),
            )
            if world is not None and calendar is not None
            else None
        )
        self._email_service = email
        self._telephony_service = telephony
        # Phase 8 (BUILD_SPEC section 97): a service request needs only the
        # world repository, the same as documents — its contact/booking calls
        # are ordinary ``prepare_action``/``create_waiting_item`` calls on
        # this class, not a second copy of that orchestration.
        self._service_request_service = (
            ServiceRequestService(
                world=world,
                clock=self._clock,
                publish=(
                    lambda entity_id: self._publish(WORLD_CHANGED, entity_id=entity_id)
                ),
            )
            if world is not None
            else None
        )
        # Phase 9 (BUILD_SPEC section 98): shopping needs both a persistence
        # path (``world``) and a provider adapter (``browser``), the same
        # two-dependency shape ``AppointmentService`` uses for world+calendar.
        self._shopping_service = (
            ShoppingService(
                world=world,
                browser=browser,
                clock=self._clock,
                publish=(
                    lambda entity_id: self._publish(WORLD_CHANGED, entity_id=entity_id)
                ),
            )
            if world is not None and browser is not None
            else None
        )

    def _require(self, client: ClientIdentity, capability: Capability) -> None:
        require(client, capability, safe_mode=self.safe_mode)

    def _publish(self, event_type: str, **fields: object) -> None:
        """Notify Console subscribers after a successful mutation.

        Best-effort by design: a missed event costs one refetch, so a broker
        failure must never fail the mutation that triggered it (events.py).
        """
        if self._events is not None:
            self._events.publish({"type": event_type, **fields})

    # --- people -------------------------------------------------------------

    async def get_person(
        self, client: ClientIdentity, *, person_id: str | None = None
    ) -> Person:
        """Fetch a person, defaulting to the primary user.

        ``get_person()`` with no argument is the common case: an agent asking
        "who am I acting for?".
        """
        self._require(client, Capability.READ_WORLD)

        with operation("person.get", person_id=person_id, client_id=client.client_id):
            person = (
                await self._people.get(person_id)
                if person_id
                else await self._people.get_primary()
            )

        if person is None:
            raise NotFoundError(
                f"no such person: {person_id}" if person_id else "no primary person is set",
                person_id=person_id,
            )
        return person

    async def find_people(self, client: ClientIdentity, *, name: str) -> list[Person]:
        self._require(client, Capability.READ_WORLD)
        return await self._people.find_by_name(name)

    async def list_people(self, client: ClientIdentity, *, limit: int = 100) -> list[Person]:
        self._require(client, Capability.READ_WORLD)
        return await self._people.list_all(limit=limit)

    async def create_person(
        self, client: ClientIdentity, draft: PersonDraft
    ) -> Person:
        # Creating people is world-shaping rather than preference-stating, so
        # it sits behind the same capability that guards preference writes
        # until Phase 3 gives it a capability of its own.
        self._require(client, Capability.WRITE_PREFERENCE)

        now = now_iso(self._clock)
        person_id = slug_id(PREFIX_PERSON, draft.display_name)

        existing = await self._people.get(person_id)
        if existing is not None:
            raise ConflictError(
                f"person {person_id} already exists", person_id=person_id
            )

        person = Person(
            id=person_id,
            display_name=draft.display_name,
            is_primary=draft.is_primary,
            aliases=draft.aliases,
            timezone=draft.timezone,
            created_at=now,
            updated_at=now,
        )
        with operation("person.create", person_id=person_id, client_id=client.client_id):
            created = await self._people.upsert(person)
        self._publish(PERSON_CHANGED, person_id=created.id)
        return created

    async def ensure_primary_person(self, display_name: str) -> Person:
        """Create the primary person if none exists yet.

        Used by first-run setup. Idempotent, so re-running bootstrap does not
        fork the user's identity.
        """
        existing = await self._people.get_primary()
        if existing is not None:
            return existing

        now = now_iso(self._clock)
        person = Person(
            id=slug_id(PREFIX_PERSON, display_name),
            display_name=display_name,
            is_primary=True,
            created_at=now,
            updated_at=now,
        )
        return await self._people.upsert(person)

    async def _resolve_subject(self, subject_id: str | None) -> str:
        if subject_id:
            person = await self._people.get(subject_id)
            if person is None:
                raise NotFoundError(f"no such person: {subject_id}", person_id=subject_id)
            return person.id

        primary = await self._people.get_primary()
        if primary is None:
            raise NotFoundError(
                "no primary person is set; run first-run setup before saving "
                "preferences"
            )
        return primary.id

    # --- memory (BUILD_SPEC sections 42–47) -----------------------------------

    def _memory(self) -> MemoryService:
        if self._memory_service is None:
            raise ConfigurationError(
                "no memory repository is configured", component="memory"
            )
        return self._memory_service

    async def remember(self, client: ClientIdentity, draft: MemoryDraft) -> MemoryRecord:
        """Store a durable memory (section 47 durability rules apply).

        This records an observation; it executes nothing and changes no
        transactional state (section 44).
        """
        self._require(client, Capability.WRITE_MEMORY)
        resolved = await self._resolve_subject(draft.subject_id)
        return await self._memory().remember(
            draft, subject_id=resolved, client_id=client.client_id
        )

    async def recall(
        self,
        client: ClientIdentity,
        *,
        query: str = "",
        subject_id: str | None = None,
        memory_types: list[MemoryType] | None = None,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        """Search current memories. A blank query lists the most relevant."""
        self._require(client, Capability.READ_MEMORY)
        if subject_id is not None:
            resolved: str | None = await self._resolve_subject(subject_id)
        else:
            resolved = None  # recall spans subjects unless one is named
        with operation("memory.recall", client_id=client.client_id):
            return await self._memory().recall(
                query=query, subject_id=resolved, memory_types=memory_types, limit=limit
            )

    async def get_memory(self, client: ClientIdentity, *, memory_id: str) -> MemoryRecord:
        self._require(client, Capability.READ_MEMORY)
        return await self._memory().get(memory_id)

    async def memory_history(
        self, client: ClientIdentity, *, memory_id: str
    ) -> list[MemoryRecord]:
        """Every version of a memory, newest first (section 45 provenance)."""
        self._require(client, Capability.READ_MEMORY)
        return await self._memory().history(memory_id)

    async def invalidate_memory(
        self, client: ClientIdentity, *, memory_id: str, reason: str | None = None
    ) -> MemoryRecord:
        """Close a memory's validity window. The record is kept, not deleted."""
        self._require(client, Capability.WRITE_MEMORY)
        return await self._memory().invalidate(
            memory_id, reason=reason, client_id=client.client_id
        )

    async def correct_memory(
        self,
        client: ClientIdentity,
        *,
        memory_id: str,
        new_content: str,
        source_type: PreferenceSource = PreferenceSource.USER_EXPLICIT,
        confidence: float = 1.0,
        importance: float | None = None,
    ) -> MemoryRecord:
        """Correct a memory by superseding it; the old version stays queryable."""
        self._require(client, Capability.WRITE_MEMORY)
        return await self._memory().correct(
            memory_id,
            new_content=new_content,
            source_type=source_type,
            confidence=confidence,
            importance=importance,
            client_id=client.client_id,
        )

    # --- preferences --------------------------------------------------------

    async def get_preferences(
        self,
        client: ClientIdentity,
        *,
        subject_id: str | None = None,
        key_prefix: str | None = None,
    ) -> list[Preference]:
        """Current preferences for a subject."""
        self._require(client, Capability.READ_PREFERENCES)
        resolved = await self._resolve_subject(subject_id)

        with operation(
            "preference.list", subject_id=resolved, client_id=client.client_id
        ):
            return await self._preferences.list_current(
                resolved, key_prefix=normalise_key(key_prefix) if key_prefix else None
            )

    async def get_preference_history(
        self, client: ClientIdentity, *, key: str, subject_id: str | None = None
    ) -> list[Preference]:
        self._require(client, Capability.READ_PREFERENCES)
        resolved = await self._resolve_subject(subject_id)
        return await self._preferences.list_history(resolved, normalise_key(key))

    async def save_preference(
        self, client: ClientIdentity, draft: PreferenceDraft
    ) -> Preference:
        """Record a preference, superseding any current value for the key.

        Nothing is overwritten. The previous record's validity window is
        closed and the new one points at it with SUPERSEDES, so the history in
        BUILD_SPEC section 40 is queryable rather than lost.
        """
        self._require(client, Capability.WRITE_PREFERENCE)

        key = normalise_key(draft.key)
        if not key:
            raise ValidationError("preference key must not be empty", field="key")

        resolved = await self._resolve_subject(draft.subject_id)
        now = now_iso(self._clock)
        current = await self._preferences.get_current_by_key(resolved, key)

        if current is not None:
            # A weaker source may not silently displace a stronger one. A web
            # page or a model guess does not get to overwrite something the
            # user stated directly (section 46).
            if not may_supersede(draft.source_type, current.source_type):
                raise ConflictError(
                    f"a preference for {key!r} from a more authoritative source "
                    f"({current.source_type}) is already recorded; this claim "
                    f"({draft.source_type}) cannot replace it",
                    key=key,
                    existing_source=str(current.source_type),
                    incoming_source=str(draft.source_type),
                    existing_preference_id=current.id,
                )
            # Re-stating an identical value is a no-op rather than a new
            # record, so repeated conversation turns do not pile up history.
            if current.value.strip() == draft.value.strip():
                return current

        preference = Preference(
            id=Preference.make_id(),
            subject_id=resolved,
            key=key,
            value=draft.value.strip(),
            source_type=draft.source_type,
            source_id=draft.source_id,
            confidence=draft.confidence,
            importance=draft.importance,
            observed_at=draft.observed_at or now,
            created_at=now,
            valid_from=now,
            valid_to=None,
            supersedes=current.id if current else None,
            created_by_client=client.client_id,
            notes=draft.notes,
        )

        with operation(
            "preference.write",
            key=key,
            subject_id=resolved,
            client_id=client.client_id,
            supersedes=current.id if current else None,
        ):
            saved = await self._preferences.save_superseding(
                preference, supersedes=current
            )
        self._publish(PREFERENCE_CHANGED, key=key, subject_id=resolved)
        return saved

    async def invalidate_preference(
        self, client: ClientIdentity, *, preference_id: str
    ) -> Preference:
        """Close a preference's validity window without replacing it."""
        self._require(client, Capability.WRITE_PREFERENCE)

        updated = await self._preferences.invalidate(
            preference_id, at=now_iso(self._clock)
        )
        if updated is None:
            raise NotFoundError(
                f"no such preference: {preference_id}", preference_id=preference_id
            )
        self._publish(PREFERENCE_CHANGED, key=updated.key, subject_id=updated.subject_id)
        return updated

    # --- tasks --------------------------------------------------------------

    async def create_task(self, client: ClientIdentity, draft: TaskDraft) -> Task:
        self._require(client, Capability.CREATE_TASK)

        now = now_iso(self._clock)
        owner = draft.owner_entity_id
        if owner is None:
            primary = await self._people.get_primary()
            owner = primary.id if primary else None
        elif await self._people.get(owner) is None:
            raise NotFoundError(f"no such person: {owner}", person_id=owner)

        task = Task(
            id=Task.make_id(),
            title=draft.title.strip(),
            description=draft.description,
            state=draft.state,
            priority=draft.priority,
            created_at=now,
            updated_at=now,
            due_at=draft.due_at,
            owner_entity_id=owner,
            assigned_client=None,
            verification_required=draft.verification_required,
            verification_state=(
                VerificationState.PENDING
                if draft.verification_required
                else VerificationState.NOT_REQUIRED
            ),
            related_entity_ids=draft.related_entity_ids,
            source=draft.source,
            created_by_client=client.client_id,
        )

        with operation("task.create", task_id=task.id, client_id=client.client_id):
            created = await self._tasks.create(task)
        self._publish(TASK_CHANGED, task_id=created.id)
        return created

    async def get_task(self, client: ClientIdentity, *, task_id: str) -> Task:
        self._require(client, Capability.READ_TASKS)
        task = await self._tasks.get(task_id)
        if task is None:
            raise NotFoundError(f"no such task: {task_id}", task_id=task_id)
        return task

    async def list_tasks(
        self,
        client: ClientIdentity,
        *,
        states: list[TaskState] | None = None,
        owner_entity_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        self._require(client, Capability.READ_TASKS)
        with operation("task.list", client_id=client.client_id):
            return await self._tasks.list(
                states=states,
                owner_entity_id=owner_entity_id,
                limit=limit,
                offset=offset,
            )

    async def count_tasks_by_state(self, client: ClientIdentity) -> dict[str, int]:
        self._require(client, Capability.READ_TASKS)
        return await self._tasks.count_by_state()

    async def update_task(
        self, client: ClientIdentity, *, task_id: str, update: TaskUpdate
    ) -> Task:
        """Apply a partial update, validating any state change.

        The state change runs through the state machine rather than being
        assigned, so an illegal transition proposed by a model is rejected
        here instead of being written and discovered later.
        """
        self._require(client, Capability.UPDATE_TASK)

        task = await self._tasks.get(task_id)
        if task is None:
            raise NotFoundError(f"no such task: {task_id}", task_id=task_id)

        now = now_iso(self._clock)
        working = task.model_copy(deep=True)

        for field in (
            "title",
            "description",
            "priority",
            "due_at",
            "current_action",
            "related_entity_ids",
            "verification_evidence",
        ):
            value = getattr(update, field)
            if value is not None:
                setattr(working, field, value)

        if update.owner_entity_id is not None:
            if await self._people.get(update.owner_entity_id) is None:
                raise NotFoundError(
                    f"no such person: {update.owner_entity_id}",
                    person_id=update.owner_entity_id,
                )
            working.owner_entity_id = update.owner_entity_id

        working.updated_at = now

        if update.state is not None and update.state != task.state:
            with operation(
                "task.transition",
                task_id=task_id,
                from_state=str(task.state),
                to_state=str(update.state),
                client_id=client.client_id,
            ):
                working = apply_transition(
                    working,
                    update.state,
                    now=now,
                    verification_evidence=update.verification_evidence,
                    actor_client=client.client_id,
                )

        updated = await self._tasks.update(working)
        self._publish(TASK_CHANGED, task_id=updated.id)
        return updated

    # --- world (BUILD_SPEC sections 36–39, 92) --------------------------------

    def _world(self) -> WorldService:
        if self._world_service is None:
            raise ConfigurationError(
                "no world repository is configured", component="world"
            )
        return self._world_service

    async def world_graph(
        self,
        client: ClientIdentity,
        *,
        query: str = "",
        entity_types: list[str] | None = None,
        limit: int = 500,
    ) -> WorldGraph:
        """The world graph, optionally narrowed by search text and type filter."""
        self._require(client, Capability.READ_WORLD)
        types = parse_entity_types(entity_types)
        with operation("world.graph", client_id=client.client_id):
            return await self._world().graph(query=query, entity_types=types, limit=limit)

    async def world_neighborhood(
        self, client: ClientIdentity, *, entity_id: str, depth: int = 1
    ) -> WorldGraph:
        """The subgraph around one entity, out to ``depth`` hops."""
        self._require(client, Capability.READ_WORLD)
        with operation(
            "world.neighborhood", entity_id=entity_id, client_id=client.client_id
        ):
            return await self._world().neighborhood(entity_id, depth=depth)

    async def get_entity_detail(
        self, client: ClientIdentity, *, entity_id: str
    ) -> EntityDetail:
        """The entity inspector aggregate (section 16).

        Assembled here rather than in ``WorldService`` because it spans three
        repositories; the world service is kept narrow on purpose. Related
        tasks and memories are read through the same capabilities that guard
        them elsewhere, so a client that may see the graph but not the task
        list gets an inspector without a task panel instead of a 403.
        """
        self._require(client, Capability.READ_WORLD)

        with operation("world.entity_detail", entity_id=entity_id, client_id=client.client_id):
            world = self._world()
            entity = await world.get(entity_id)
            edges, neighbors = await world.relationships_for(entity_id)

            tasks: list[Task] = []
            if Capability.READ_TASKS in client.capabilities:
                tasks = await self._tasks.list_related_to_entity(entity_id)

            memories: list[MemoryRecord] = []
            if Capability.READ_MEMORY in client.capabilities and self._memory_service:
                memories = await self._memory().list_for_entity(
                    entity_id, current_only=True
                )

        return EntityDetail(
            entity=entity,
            relationships=edges,
            neighbors=neighbors,
            related_tasks=tasks,
            related_memories=memories,
        )

    async def entity_history(
        self, client: ClientIdentity, *, entity_id: str
    ) -> EntityHistory:
        """What the record can honestly say about how an entity changed.

        World entity facts are current-only in Phase 3, so the history is the
        full memory record referencing the entity — closed versions included.
        ``covers`` travels with the answer so no consumer mistakes it for the
        durable audit log (Phase 4, section 62).
        """
        self._require(client, Capability.READ_WORLD)

        with operation("world.entity_history", entity_id=entity_id, client_id=client.client_id):
            await self._world().get(entity_id)

            covers = ["memories referencing this entity, including closed versions"]
            memories: list[MemoryRecord] = []
            if Capability.READ_MEMORY in client.capabilities and self._memory_service:
                memories = await self._memory().list_for_entity(
                    entity_id, current_only=False
                )
            else:
                covers = ["nothing: this client cannot read memory"]

        return EntityHistory(entity_id=entity_id, memories=memories, covers=covers)

    async def create_entity(
        self, client: ClientIdentity, draft: EntityDraft
    ) -> WorldEntity:
        """Create a household, provider, or asset.

        This records world state; it executes nothing. Persons keep their own
        surface (``create_person``) because they carry primary-user semantics.
        """
        self._require(client, Capability.WRITE_WORLD)
        return await self._world().create(draft, client_id=client.client_id)

    async def link_entities(
        self, client: ClientIdentity, *, source_id: str, target_id: str, rel_type: str
    ) -> WorldEdge:
        """Relate two existing entities with a relationship from the vocabulary."""
        self._require(client, Capability.WRITE_WORLD)
        return await self._world().link(
            source_id,
            target_id,
            parse_relationship(rel_type),
            client_id=client.client_id,
        )

    async def unlink_entities(
        self, client: ClientIdentity, *, source_id: str, target_id: str, rel_type: str
    ) -> None:
        """Remove a relationship, identified by its (source, target, type) triple."""
        self._require(client, Capability.WRITE_WORLD)
        await self._world().unlink(
            source_id,
            target_id,
            parse_relationship(rel_type),
            client_id=client.client_id,
        )

    # --- durable work (BUILD_SPEC sections 13, 54-62) --------------------------

    def _waiting(self) -> WaitingService:
        if self._waiting_service is None:
            raise ConfigurationError(
                "no waiting repository is configured", component="waiting"
            )
        return self._waiting_service

    def _actions(self) -> ActionService:
        if self._action_service is None:
            raise ConfigurationError(
                "no action repository is configured", component="actions"
            )
        return self._action_service

    def _appointments(self) -> AppointmentService:
        if self._appointment_service is None:
            raise ConfigurationError(
                "no calendar provider is configured", component="calendar"
            )
        return self._appointment_service

    def _email(self) -> EmailProviderService:
        if self._email_service is None:
            raise ConfigurationError(
                "no email provider is configured", component="email"
            )
        return self._email_service

    def _telephony(self) -> TelephonyProviderService:
        if self._telephony_service is None:
            raise ConfigurationError(
                "no telephony provider is configured", component="telephony"
            )
        return self._telephony_service

    def _service_requests(self) -> ServiceRequestService:
        if self._service_request_service is None:
            raise ConfigurationError(
                "no world repository is configured", component="service_requests"
            )
        return self._service_request_service

    def _shopping(self) -> ShoppingService:
        if self._shopping_service is None:
            raise ConfigurationError(
                "no browser provider is configured", component="shopping"
            )
        return self._shopping_service

    async def audit(
        self,
        client: ClientIdentity,
        *,
        result: str,
        intent: str | None = None,
        tool: str | None = None,
        risk: str | None = None,
        approval: str | None = None,
        action: str | None = None,
        target: str | None = None,
        verification: str | None = None,
        user: str | None = None,
        session: str | None = None,
        trace_id: str | None = None,
        **details: str,
    ) -> AuditRecord | None:
        """Append one audit record (section 62).

        Best-effort like event publishing: a failure to record must not undo
        the thing that happened. Returns None when no audit repository is
        configured, which is the case in unit tests.
        """
        if self._audit_repo is None:
            return None
        record = AuditRecord(
            id=AuditRecord.make_id(),
            requester=client.client_id,
            user=user,
            client=client.client_id,
            session=session,
            intent=intent,
            tool=tool,
            risk=risk,
            approval=approval,
            action=action,
            target=target,
            result=result,
            verification=verification,
            timestamp=now_iso(self._clock),
            trace_id=trace_id,
            details={k: str(v) for k, v in details.items()},
        )
        return await self._audit_repo.append(record)

    async def read_audit(
        self, client: ClientIdentity, *, target: str | None = None, limit: int = 100
    ) -> list[AuditRecord]:
        """The audit log — "why did Hermes do that?" (section 62)."""
        self._require(client, Capability.READ_TASKS)
        if self._audit_repo is None:
            raise ConfigurationError(
                "no audit repository is configured", component="audit"
            )
        if target is not None:
            return await self._audit_repo.list_for_target(target, limit=limit)
        return await self._audit_repo.list_recent(limit=limit)

    # --- waiting items --------------------------------------------------------

    async def create_waiting_item(
        self, client: ClientIdentity, draft: WaitingDraft
    ) -> WaitingItem:
        """Record that a task is blocked on someone else (section 54).

        Low-risk (section 51): this captures a fact about the world, it sends
        nothing and commits the user to nothing.
        """
        self._require(client, Capability.CREATE_TASK)
        task = await self._tasks.get(draft.task_id)
        if task is None:
            raise NotFoundError(f"no such task: {draft.task_id}", task_id=draft.task_id)
        item = await self._waiting().create(draft, client_id=client.client_id)
        await self.audit(
            client, result="created", intent="create_waiting_item",
            target=item.id, risk="low",
        )
        return item

    async def get_waiting_item(
        self, client: ClientIdentity, *, waiting_id: str
    ) -> WaitingItem:
        self._require(client, Capability.READ_TASKS)
        return await self._waiting().get(waiting_id)

    async def list_waiting(
        self,
        client: ClientIdentity,
        *,
        statuses: list[WaitingStatus] | None = None,
        limit: int = 100,
    ) -> list[WaitingItem]:
        """The Waiting screen's list (section 13)."""
        self._require(client, Capability.READ_TASKS)
        return await self._waiting().list(statuses=statuses, limit=limit)

    async def record_followup(
        self, client: ClientIdentity, *, waiting_id: str
    ) -> WaitingItem:
        """Log a follow-up, escalating when the budget is spent."""
        self._require(client, Capability.UPDATE_TASK)
        item = await self._waiting().record_followup(
            waiting_id, client_id=client.client_id
        )
        await self.audit(
            client, result=str(item.status), intent="record_followup",
            target=item.id, risk="low", followup_count=str(item.followup_count),
        )
        return item

    async def resolve_waiting_item(
        self, client: ClientIdentity, *, waiting_id: str
    ) -> WaitingItem:
        self._require(client, Capability.UPDATE_TASK)
        item = await self._waiting().resolve(waiting_id, client_id=client.client_id)
        await self.audit(
            client, result="resolved", intent="resolve_waiting_item", target=item.id
        )
        return item

    async def due_waiting_items(
        self, client: ClientIdentity, *, limit: int = 50
    ) -> list[WaitingItem]:
        """What the due-work worker should act on now (section 55)."""
        self._require(client, Capability.READ_TASKS)
        return await self._waiting().due(limit=limit)

    async def claim_waiting_item(
        self, client: ClientIdentity, *, waiting_id: str, owner: str
    ) -> WaitingItem | None:
        """Lease an item for this worker, or None if another holds it."""
        self._require(client, Capability.UPDATE_TASK)
        return await self._waiting().claim(waiting_id, owner=owner)

    # --- actions and approvals ------------------------------------------------

    async def prepare_action(
        self, client: ClientIdentity, draft: ActionDraft
    ) -> Action:
        """Record an intended external write before it happens (section 60).

        Gated on the capability for the action's risk class, so a client that
        may send email still cannot book or pay.
        """
        self._require(client, capability_for_action(str(draft.type)))
        action = await self._actions().prepare(draft, client_id=client.client_id)
        await self.audit(
            client,
            result=str(action.status),
            intent="prepare_action",
            tool=str(action.type),
            risk=str(risk_for_action(draft.type)),
            action=action.id,
            target=action.target_entity_id,
        )
        return action

    async def get_action(self, client: ClientIdentity, *, action_id: str) -> Action:
        self._require(client, Capability.READ_TASKS)
        return await self._actions().get(action_id)

    async def list_actions(
        self,
        client: ClientIdentity,
        *,
        statuses: list[ActionStatus] | None = None,
        limit: int = 100,
    ) -> list[Action]:
        self._require(client, Capability.READ_TASKS)
        return await self._actions().list(statuses=statuses, limit=limit)

    async def list_pending_approvals(
        self, client: ClientIdentity, *, limit: int = 50
    ) -> list[Approval]:
        """What the Approval screen shows (section 58)."""
        self._require(client, Capability.READ_TASKS)
        return await self._actions().pending_approvals(limit=limit)

    async def decide_approval(
        self, client: ClientIdentity, *, approval_id: str, approved: bool
    ) -> Approval:
        """Approve or decline one exact action (sections 57-58).

        Only a client holding APPROVE_ACTION may do this, which in practice
        means the Console: an agent approving its own action would defeat the
        gate entirely.
        """
        self._require(client, Capability.APPROVE_ACTION)
        approval = await self._actions().decide(
            approval_id, approved=approved, by=client.client_id
        )
        await self.audit(
            client,
            result=str(approval.status),
            intent="decide_approval",
            approval=approval.id,
            action=approval.action_id,
            risk="approval",
        )
        return approval

    async def commit_action(self, client: ClientIdentity, *, action_id: str) -> Action:
        """Clear an action to execute, spending its approval (section 57)."""
        action = await self._actions().get(action_id)
        self._require(client, capability_for_action(str(action.type)))
        committed = await self._actions().begin_commit(
            action_id, client_id=client.client_id
        )
        await self.audit(
            client,
            result="committing",
            intent="commit_action",
            tool=str(committed.type),
            action=committed.id,
            target=committed.target_entity_id,
            risk=str(risk_for_action(committed.type)),
        )
        return committed

    async def record_action_result(
        self,
        client: ClientIdentity,
        *,
        action_id: str,
        succeeded: bool,
        external_reference: str | None = None,
        failure_reason: str | None = None,
    ) -> Action:
        """Persist what the external system returned (section 60 step 3)."""
        action = await self._actions().get(action_id)
        self._require(client, capability_for_action(str(action.type)))
        saved = await self._actions().record_result(
            action_id,
            succeeded=succeeded,
            external_reference=external_reference,
            failure_reason=failure_reason,
        )
        await self.audit(
            client,
            result=str(saved.status),
            intent="record_action_result",
            action=saved.id,
            tool=str(saved.type),
            verification=str(saved.verification_state),
        )
        return saved

    async def verify_action(
        self, client: ClientIdentity, *, action_id: str, evidence: str
    ) -> Action:
        """Turn an executed action into a verified one, with evidence."""
        action = await self._actions().get(action_id)
        self._require(client, capability_for_action(str(action.type)))
        verified = await self._actions().verify(action_id, evidence=evidence)
        await self.audit(
            client,
            result="verified",
            intent="verify_action",
            action=verified.id,
            tool=str(verified.type),
            verification=str(verified.verification_state),
        )
        return verified

    async def execute_action(self, client: ClientIdentity, *, action_id: str) -> Action:
        """Commit an action and perform its external effect (section 60 steps
        2-3), for the writes this phase implements: booking, cancelling,
        sending email, and — phase 8 — placing a provider phone call or
        requesting a quote (BUILD_SPEC section 97).

        Deliberately not folded into ``commit_action``: committing spends the
        approval and is safe to call on its own; calling the provider is a
        distinct step with its own failure mode, and section 60 asks for both
        to be visible as separate points in the record. This method exists so
        one caller (the Console, or Hermes once a human has approved) does not
        have to reimplement "commit, then call the right provider, then
        record the result" for every action type.
        """
        action = await self._actions().get(action_id)
        self._require(client, capability_for_action(str(action.type)))
        if action.type not in (
            ActionType.BOOK_APPOINTMENT,
            ActionType.CANCEL_APPOINTMENT,
            ActionType.SEND_EMAIL,
            ActionType.PLACE_PHONE_CALL,
            ActionType.REQUEST_QUOTE,
            ActionType.BUILD_GROCERY_CART,
            ActionType.SUBMIT_GROCERY_ORDER,
        ):
            raise ValidationError(
                f"no executor is wired for action type {action.type}",
                action_id=action.id,
                action_type=str(action.type),
            )

        committed = await self.commit_action(client, action_id=action_id)
        try:
            if committed.type is ActionType.BOOK_APPOINTMENT:
                external_reference, _ = await self._appointments().execute_booking(committed)
            elif committed.type is ActionType.CANCEL_APPOINTMENT:
                external_reference, _ = await self._appointments().execute_cancellation(
                    committed
                )
            elif committed.type in (ActionType.PLACE_PHONE_CALL, ActionType.REQUEST_QUOTE):
                external_reference, _ = await self._execute_phone_call(client, committed)
            elif committed.type is ActionType.BUILD_GROCERY_CART:
                external_reference, _ = await self._shopping().execute_cart_build(committed)
            elif committed.type is ActionType.SUBMIT_GROCERY_ORDER:
                external_reference, _ = await self._shopping().execute_checkout(committed)
            else:
                external_reference, _ = await self._execute_send_email(committed)
        except (ProviderError, ValidationError, ConfigurationError) as exc:
            result = await self.record_action_result(
                client, action_id=action_id, succeeded=False, failure_reason=str(exc)
            )
            list_id = committed.payload.get("shopping_list_id")
            if committed.type is ActionType.BUILD_GROCERY_CART and list_id:
                await self._shopping().mark_cart_failed(str(list_id), now=now_iso(self._clock))
            return result
        return await self.record_action_result(
            client, action_id=action_id, succeeded=True, external_reference=external_reference
        )

    async def _execute_send_email(self, action: Action) -> tuple[str, str]:
        draft = EmailSendDraft(**action.payload)
        message_id = await self._email().send(draft)
        return message_id, f"sent via email provider: {message_id}"

    async def _execute_phone_call(
        self, client: ClientIdentity, action: Action
    ) -> tuple[str, str]:
        """Place a PLACE_PHONE_CALL or REQUEST_QUOTE (BUILD_SPEC sections 68,
        97). ``objective_from_payload`` re-validates the objective against the
        section 97 hard rule (no charge/repair authority) even though
        ``prepare_action`` already refused to prepare a payload that violated
        it — defence in depth against a payload read back from storage having
        been tampered with between prepare and execute.

        Folds the structured result (section 69) back onto the ServiceRequest
        the call belongs to, if the payload names one — recording a quote,
        opening a WaitingItem when the provider did not answer with a usable
        answer (section 101 step 8), or both.
        """
        objective = objective_from_payload(action.payload)
        result = await self._telephony().dial(objective)
        service_request_id = action.payload.get("service_request_id")
        if service_request_id:
            await self._apply_call_result(client, str(service_request_id), result)
        reference = result.external_reference or action.idempotency_key
        message = (
            f"call {'connected' if result.connected else 'did not connect'}; "
            f"objective_met={result.objective_met}"
        )
        return reference, message

    async def _apply_call_result(
        self, client: ClientIdentity, service_request_id: str, result: CallResult
    ) -> None:
        """Fold section 69's structured result back onto its service request.

        A WaitingItem is section 54's — it always belongs to a Task
        (``WaitingDraft.task_id`` is required) — so a service request opened
        without one has nothing to attach a follow-up to and this silently
        does not open one. Section 101's scenario always has a task (the
        Electrician request starts from one), so this is a real but narrow
        gap: a taskless service request that goes unanswered stays in
        CONTACTING_PROVIDER with no durable follow-up record.
        """
        request = await self._service_requests().get(service_request_id)
        if (not result.connected or result.follow_up_required) and (
            request.waiting_item_id is None and request.task_id
        ):
            waiting = await self.create_waiting_item(
                client,
                WaitingDraft(
                    task_id=request.task_id,
                    subject=f"waiting to hear back: {request.subject}",
                    waiting_on_entity_id=request.provider_entity_id,
                ),
            )
            await self._service_requests().record_waiting(
                service_request_id, waiting_item_id=waiting.id
            )
        if result.availability or result.diagnostic_fee:
            await self._service_requests().record_quote(
                service_request_id,
                availability=result.availability or None,
                diagnostic_fee=result.diagnostic_fee,
            )

    async def verify_action_externally(
        self, client: ClientIdentity, *, action_id: str
    ) -> Action:
        """Independently confirm an executed action really happened before
        marking it verified — section 63's warning generalised to every write
        this phase makes: neither a hold nor a provider accepting a request is
        proof, only checking again is (section 6).

        This is the only path that can move a booked or cancelled Appointment
        out of ``HELD`` or into ``CANCELLED``: local state changes exactly
        when, and only when, this independent check passes.
        """
        action = await self._actions().get(action_id)
        self._require(client, capability_for_action(str(action.type)))
        if action.status is not ActionStatus.EXECUTED:
            raise ConflictError(
                f"action {action.id} is {action.status}; only an executed action "
                "can be verified",
                action_id=action.id,
                reason="not_executed",
            )
        if not action.external_reference:
            raise VerificationRequiredError(
                f"action {action.id} has no external reference to verify against",
                action_id=action.id,
            )

        if action.type is ActionType.BOOK_APPOINTMENT:
            ok, evidence = await self._appointments().confirm_evidence(
                action.external_reference
            )
        elif action.type is ActionType.CANCEL_APPOINTMENT:
            ok, evidence = await self._appointments().confirm_cancellation_evidence(
                action.external_reference
            )
        elif action.type is ActionType.SEND_EMAIL:
            ok = await self._email().confirm_sent(action.external_reference)
            evidence = (
                f"confirmed in the Sent folder: {action.external_reference}"
                if ok
                else f"not found in the Sent folder: {action.external_reference}"
            )
        elif action.type is ActionType.BUILD_GROCERY_CART:
            ok, evidence = await self._shopping().confirm_cart_evidence(
                action, action.external_reference
            )
        elif action.type is ActionType.SUBMIT_GROCERY_ORDER:
            ok, evidence = await self._shopping().confirm_order_evidence(
                action, action.external_reference
            )
        else:
            raise ValidationError(
                f"no verifier is wired for action type {action.type}", action_id=action.id
            )

        if not ok:
            raise VerificationRequiredError(
                f"could not independently confirm that {action.type} succeeded",
                action_id=action.id,
            )

        verified = await self.verify_action(client, action_id=action_id, evidence=evidence)

        appointment_id = verified.payload.get("appointment_id")
        if appointment_id and verified.external_reference:
            now = now_iso(self._clock)
            if verified.type is ActionType.BOOK_APPOINTMENT:
                await self._appointments().mark_booked(
                    str(appointment_id),
                    external_event_id=verified.external_reference,
                    action_id=verified.id,
                    now=now,
                )
            elif verified.type is ActionType.CANCEL_APPOINTMENT:
                await self._appointments().mark_cancelled(
                    str(appointment_id), action_id=verified.id, now=now
                )

        shopping_list_id = verified.payload.get("shopping_list_id")
        if shopping_list_id and verified.external_reference:
            now = now_iso(self._clock)
            if verified.type is ActionType.BUILD_GROCERY_CART:
                await self._shopping().mark_cart_built(
                    str(shopping_list_id),
                    cart_reference=verified.external_reference,
                    total_estimate=None,
                    now=now,
                )
            elif verified.type is ActionType.SUBMIT_GROCERY_ORDER:
                await self._shopping().mark_order_verified(
                    str(shopping_list_id),
                    order_reference=verified.external_reference,
                    now=now,
                )
        return verified

    # --- calendar (BUILD_SPEC sections 63, 96) -------------------------------
    #
    # Section 63's mandatory order: read, free/busy, hold, create, update,
    # cancel. Reads are gated on READ_WORLD — the lowest-risk step and the one
    # every client that can see the world should be able to take. Holding a
    # slot already touches an external calendar, so it spends BOOK_APPOINTMENT
    # and is blocked in safe mode with it (policy/capabilities.py).

    async def read_calendar(
        self, client: ClientIdentity, *, start_at: str, end_at: str
    ) -> list[CalendarEvent]:
        """Section 63 step 1. Read entries and cache them into the world graph
        (section 63: "Calendar records should relate to LifeOps entities")."""
        self._require(client, Capability.READ_WORLD)
        with operation("calendar.read", client_id=client.client_id):
            return await self._appointments().read_calendar(start_at=start_at, end_at=end_at)

    async def check_calendar_free_busy(
        self, client: ClientIdentity, *, start_at: str, end_at: str
    ) -> FreeBusyResult:
        """Section 63 step 2."""
        self._require(client, Capability.READ_WORLD)
        return await self._appointments().free_busy(start_at=start_at, end_at=end_at)

    async def get_appointment(
        self, client: ClientIdentity, *, appointment_id: str
    ) -> Appointment:
        self._require(client, Capability.READ_WORLD)
        return await self._appointments().get(appointment_id)

    async def list_appointments(
        self,
        client: ClientIdentity,
        *,
        status: AppointmentStatus | None = None,
        task_id: str | None = None,
    ) -> list[Appointment]:
        self._require(client, Capability.READ_WORLD)
        return await self._appointments().list(status=status, task_id=task_id)

    async def create_appointment_hold(
        self, client: ClientIdentity, draft: AppointmentHoldDraft
    ) -> Appointment:
        """Section 63 step 3: a reversible write, not yet a commitment."""
        self._require(client, Capability.BOOK_APPOINTMENT)
        appointment = await self._appointments().hold(draft, client_id=client.client_id)
        await self.audit(
            client,
            result="held",
            intent="create_appointment_hold",
            tool="calendar",
            target=appointment.id,
            risk=str(Capability.BOOK_APPOINTMENT),
        )
        return appointment

    async def book_appointment(
        self, client: ClientIdentity, *, appointment_id: str
    ) -> Action:
        """Section 63 step 4, through the outbox (BUILD_SPEC section 60).

        Placing a hold does not do this — only a prepared, approved,
        committed, and independently verified Action can (section 63's
        warning). This method only gets that Action started.
        """
        appointment = await self._appointments().get(appointment_id)
        if appointment.status is not AppointmentStatus.HELD:
            raise ValidationError(
                f"appointment {appointment_id} is {appointment.status}, not held",
                appointment_id=appointment_id,
            )
        payload = {
            "appointment_id": appointment.id,
            "subject": appointment.subject,
            "start_at": appointment.start_at,
            "end_at": appointment.end_at,
            "location": appointment.location,
            "notes": appointment.notes,
            "hold_reference": appointment.hold_reference,
        }
        return await self.prepare_action(
            client,
            ActionDraft(
                type=ActionType.BOOK_APPOINTMENT,
                payload=payload,
                task_id=appointment.task_id,
                target_entity_id=appointment.provider_entity_id,
            ),
        )

    async def cancel_appointment(
        self, client: ClientIdentity, *, appointment_id: str
    ) -> Action:
        """Section 63 step 6, through the outbox."""
        appointment = await self._appointments().get(appointment_id)
        if appointment.is_terminal:
            raise ValidationError(
                f"appointment {appointment_id} is already {appointment.status}",
                appointment_id=appointment_id,
            )
        payload = {
            "appointment_id": appointment.id,
            "external_event_id": appointment.external_event_id,
        }
        return await self.prepare_action(
            client,
            ActionDraft(
                type=ActionType.CANCEL_APPOINTMENT,
                payload=payload,
                task_id=appointment.task_id,
                target_entity_id=appointment.provider_entity_id,
            ),
        )

    # --- service requests (BUILD_SPEC sections 36, 67, 68, 97, 101) ----------
    #
    # Section 97's ordering: provider research, information gathering, phone
    # calls, waiting, quote collection — then approval-gated booking. Reads
    # and opening a request are gated on WRITE_WORLD/READ_WORLD, the same as
    # any other world entity; contacting a provider spends whatever capability
    # ``capability_for_action`` names for PLACE_PHONE_CALL/REQUEST_QUOTE
    # (SEND_EXTERNAL_MESSAGE — policy/capabilities.py) through
    # ``prepare_action``, and booking spends BOOK_APPOINTMENT through the
    # existing calendar flow above. Nothing here invents a second approval
    # gate or a second outbox; it only ties their outcomes back to the request
    # that started them.

    async def create_service_request(
        self, client: ClientIdentity, draft: ServiceRequestDraft
    ) -> ServiceRequest:
        """Section 101 step 1: identify the relevant asset and open the
        record the rest of the workflow updates."""
        self._require(client, Capability.WRITE_WORLD)
        request = await self._service_requests().open(draft, client_id=client.client_id)
        await self.audit(
            client, result="created", intent="create_service_request", target=request.id
        )
        return request

    async def get_service_request(
        self, client: ClientIdentity, *, service_request_id: str
    ) -> ServiceRequest:
        self._require(client, Capability.READ_WORLD)
        return await self._service_requests().get(service_request_id)

    async def list_service_requests(
        self, client: ClientIdentity, *, task_id: str | None = None
    ) -> list[ServiceRequest]:
        self._require(client, Capability.READ_WORLD)
        return await self._service_requests().list(task_id=task_id)

    async def _prepare_provider_contact(
        self,
        client: ClientIdentity,
        *,
        service_request_id: str,
        provider_entity_id: str,
        objective: str,
        collect: list[str] | None,
        action_type: ActionType,
    ) -> Action:
        request = await self._service_requests().get(service_request_id)
        call_objective = build_call_objective(
            objective=objective, provider_entity_id=provider_entity_id, collect=collect
        )
        payload = build_call_payload(call_objective, service_request_id=service_request_id)
        action = await self.prepare_action(
            client,
            ActionDraft(
                type=action_type,
                payload=payload,
                task_id=request.task_id,
                target_entity_id=provider_entity_id,
            ),
        )
        await self._service_requests().record_contact(
            service_request_id, action_id=action.id, provider_entity_id=provider_entity_id
        )
        return action

    async def request_provider_call(
        self,
        client: ClientIdentity,
        *,
        service_request_id: str,
        provider_entity_id: str,
        objective: str,
        collect: list[str] | None = None,
    ) -> Action:
        """Section 101 steps 5-6: call the provider (BUILD_SPEC section 68).
        PLACE_PHONE_CALL is R2 and policy-controlled rather than approval-
        gated by default (domain/actions.py) — Hermes places this call on its
        own, matching section 101's flow. The objective's authority never
        includes ``authorize_charge`` or ``authorize_repairs``
        (domain/telephony.py's ``build_call_objective`` cannot construct
        either as True) — section 97's hard rule and section 101 step 9,
        enforced at construction rather than trusted to a prompt.
        """
        return await self._prepare_provider_contact(
            client,
            service_request_id=service_request_id,
            provider_entity_id=provider_entity_id,
            objective=objective,
            collect=collect,
            action_type=ActionType.PLACE_PHONE_CALL,
        )

    async def request_quote_by_phone(
        self,
        client: ClientIdentity,
        *,
        service_request_id: str,
        provider_entity_id: str,
        objective: str,
        collect: list[str] | None = None,
    ) -> Action:
        """Section 101 step 7's diagnostic-fee collection, via REQUEST_QUOTE.
        Uses the same telephony transport as ``request_provider_call``:
        section 105's anti-overengineering gate does not justify a second
        channel for what is, from LifeOps' side, the same constrained-
        objective call with a different label.
        """
        return await self._prepare_provider_contact(
            client,
            service_request_id=service_request_id,
            provider_entity_id=provider_entity_id,
            objective=objective,
            collect=collect,
            action_type=ActionType.REQUEST_QUOTE,
        )

    async def request_service_booking(
        self, client: ClientIdentity, *, service_request_id: str, appointment_id: str
    ) -> Action:
        """Section 101 step 10: prepare the booking. BOOK_APPOINTMENT is R3
        and always requires approval (domain/actions.py) — this only gets the
        action into NEEDS_APPROVAL; nothing here books anything (section 101
        step 11: request approval before booking)."""
        action = await self.book_appointment(client, appointment_id=appointment_id)
        await self._service_requests().record_booking_requested(
            service_request_id, action_id=action.id
        )
        return action

    async def confirm_service_booking(
        self, client: ClientIdentity, *, service_request_id: str, appointment_id: str
    ) -> ServiceRequest:
        """Section 101 step 13: fold a verified booking into its service
        request. Requires the appointment to already be BOOKED — reachable
        only through ``verify_action_externally``'s independent confirmation
        (AGENTS.md safety invariant 3: external completion requires
        evidence) — so a caller cannot mark a request booked on the strength
        of a hold or an unverified action.
        """
        self._require(client, Capability.WRITE_WORLD)
        appointment = await self._appointments().get(appointment_id)
        if appointment.status is not AppointmentStatus.BOOKED:
            raise ValidationError(
                f"appointment {appointment_id} is {appointment.status}, not booked; "
                "verify the booking before recording it against the service request",
                appointment_id=appointment_id,
            )
        request = await self._service_requests().record_booked(
            service_request_id, appointment_id=appointment_id
        )
        await self.audit(
            client,
            result="booked",
            intent="confirm_service_booking",
            target=request.id,
            action=request.booking_action_id,
        )
        return request

    async def complete_service_request(
        self, client: ClientIdentity, *, service_request_id: str
    ) -> ServiceRequest:
        """Section 101 step 16: mark the request completed. The status
        machine (domain/service_request.py) only allows COMPLETED from
        BOOKED, so this cannot run ahead of ``confirm_service_booking`` — the
        same "no completion without verification" discipline
        domain/tasks.py's state machine applies to tasks.
        """
        self._require(client, Capability.WRITE_WORLD)
        request = await self._service_requests().complete(service_request_id)
        await self.audit(
            client, result="completed", intent="complete_service_request", target=request.id
        )
        return request

    async def cancel_service_request(
        self, client: ClientIdentity, *, service_request_id: str
    ) -> ServiceRequest:
        self._require(client, Capability.WRITE_WORLD)
        request = await self._service_requests().cancel(service_request_id)
        await self.audit(
            client, result="cancelled", intent="cancel_service_request", target=request.id
        )
        return request

    # --- email (BUILD_SPEC sections 61, 64, 96) -------------------------------
    #
    # Reads are gated on READ_WORLD, the same as calendar reads. Sending and
    # replying go through the outbox (prepare_send_email -> prepare_action)
    # rather than a direct call, because section 61 requires an idempotency
    # key LifeOps generates for email writes — never one this method or a
    # caller invents.

    async def search_email(
        self, client: ClientIdentity, *, query: str, limit: int = 25
    ) -> list[EmailMessage]:
        """Section 64's search/read."""
        self._require(client, Capability.READ_WORLD)
        return await self._email().search(query, limit=limit)

    async def read_email_thread(
        self, client: ClientIdentity, *, thread_id: str
    ) -> EmailThread:
        """Section 64's thread read."""
        self._require(client, Capability.READ_WORLD)
        return await self._email().read_thread(thread_id)

    async def prepare_send_email(
        self, client: ClientIdentity, draft: EmailSendDraft
    ) -> Action:
        """Section 64's send/reply, prepared through the outbox."""
        payload = build_send_email_payload(draft)
        return await self.prepare_action(
            client,
            ActionDraft(
                type=ActionType.SEND_EMAIL,
                payload=payload,
                task_id=draft.task_id,
                target_entity_id=draft.target_entity_id,
            ),
        )

    # --- documents (BUILD_SPEC sections 36, 64, 96) ---------------------------

    async def create_document(
        self, client: ClientIdentity, draft: DocumentDraft
    ) -> Document:
        """Section 64: "associate message with task/provider/entity" and
        "ingest relevant observations" both start here — a Document is the
        durable reference; linking it to a task or entity is an ordinary
        ``link_entities`` call with the existing REFERENCES/ABOUT edges
        (section 39), not a new relationship type.
        """
        self._require(client, Capability.WRITE_WORLD)
        now = now_iso(self._clock)
        document = create_document_domain(draft, now=now, client_id=client.client_id)
        if self._world_repo is None:
            raise ConfigurationError(
                "no world repository is configured", component="world"
            )
        entity = await self._world_repo.create(document_to_entity(document))
        self._publish(WORLD_CHANGED, entity_id=entity.id)
        await self.audit(
            client,
            result="created",
            intent="create_document",
            tool="documents",
            target=document.id,
        )
        return document

    # --- shopping (BUILD_SPEC section 98) -------------------------------------
    #
    # Section 98: authenticated browser worker, search/research, cart
    # building, substitutions, approval-gated checkout, verification. Cart
    # building (R1, section 56: a cart is reversible and commits nothing) is
    # automatic and prepares *and* executes its Action in one call; checkout
    # (R3: "Shopping checkout" — always approved) only prepares, the same
    # two-step split ``book_appointment`` and ``prepare_send_email`` use.

    async def search_shopping(
        self, client: ClientIdentity, *, query: str, store: str = "", limit: int = 10
    ) -> list[ProductResult]:
        """Section 98's "search/research". Read-only: gated on
        SHOPPING_CHECKOUT because it is still the browser worker doing the
        looking, not a generic web search — the same capability that gates
        every other shopping step."""
        self._require(client, Capability.SHOPPING_CHECKOUT)
        return await self._shopping().search(query, store=store, limit=limit)

    async def create_shopping_list(
        self, client: ClientIdentity, draft: ShoppingListDraft
    ) -> ShoppingList:
        """Open a new list. Local and reversible (R1): no Action, no
        approval — the same reasoning ``create_appointment_hold`` documents."""
        self._require(client, Capability.SHOPPING_CHECKOUT)
        shopping_list = await self._shopping().create(draft, client_id=client.client_id)
        await self.audit(
            client, result="created", intent="create_shopping_list", target=shopping_list.id
        )
        return shopping_list

    async def get_shopping_list(
        self, client: ClientIdentity, *, list_id: str
    ) -> ShoppingList:
        self._require(client, Capability.SHOPPING_CHECKOUT)
        return await self._shopping().get(list_id)

    async def list_shopping_lists(
        self,
        client: ClientIdentity,
        *,
        status: ShoppingListStatus | None = None,
        task_id: str | None = None,
    ) -> list[ShoppingList]:
        self._require(client, Capability.SHOPPING_CHECKOUT)
        return await self._shopping().list(status=status, task_id=task_id)

    async def add_shopping_items(
        self, client: ClientIdentity, *, list_id: str, items: list[ShoppingItem]
    ) -> ShoppingList:
        self._require(client, Capability.SHOPPING_CHECKOUT)
        updated = await self._shopping().add_items(
            list_id, items, client_id=client.client_id
        )
        await self.audit(
            client, result="items_added", intent="add_shopping_items", target=updated.id
        )
        return updated

    async def apply_substitution(
        self, client: ClientIdentity, *, list_id: str, draft: SubstitutionDraft
    ) -> ShoppingList:
        """Section 98's substitutions — a safety surface, not a convenience
        (this is why it is gated the same as checkout itself). If this list
        has a live checkout Action, its payload is refreshed to the new plan,
        which invalidates any approval already granted for the old one
        (section 57's binding, enforced as arithmetic by
        ``ActionService.update_payload``) — a substitution applied after a
        human approved the cart cannot ride through on that approval.
        """
        self._require(client, Capability.SHOPPING_CHECKOUT)
        updated = await self._shopping().apply_substitution(
            list_id, draft, client_id=client.client_id
        )
        if updated.checkout_action_id:
            existing = await self._actions().get(updated.checkout_action_id)
            if existing.is_live:
                await self._actions().update_payload(
                    updated.checkout_action_id,
                    payload=shopping_domain.checkout_payload(updated),
                    client_id=client.client_id,
                )
        await self.audit(
            client,
            result="substitution_applied",
            intent="apply_substitution",
            target=updated.id,
            risk="low",
            item_name=draft.item_name,
            substituted_with=draft.substituted_with,
        )
        return updated

    async def build_grocery_cart(self, client: ClientIdentity, *, list_id: str) -> Action:
        """Section 98's cart building — R1, automatic (section 56: "a cart is
        reversible and commits nothing, so no approval"). This prepares *and*
        executes the Action in one call, because R1 has no human step to wait
        for; ``execute_action`` still runs the full commit/execute/record
        sequence, so the outbox record is identical to any other action.
        """
        self._require(client, Capability.SHOPPING_CHECKOUT)
        shopping_list = await self._shopping().get(list_id)
        if shopping_list.status not in (
            ShoppingListStatus.DRAFT,
            ShoppingListStatus.CART_FAILED,
        ):
            raise ValidationError(
                f"shopping list {list_id} is {shopping_list.status}; a cart "
                "cannot be (re)built from this state",
                shopping_list_id=list_id,
            )
        if not shopping_list.items:
            raise ValidationError(
                f"shopping list {list_id} has no items to build a cart from",
                shopping_list_id=list_id,
            )
        payload = shopping_domain.build_cart_payload(shopping_list)
        action = await self.prepare_action(
            client,
            ActionDraft(
                type=ActionType.BUILD_GROCERY_CART,
                payload=payload,
                task_id=shopping_list.task_id,
                target_entity_id=shopping_list.id,
            ),
        )
        await self._shopping().mark_cart_building(
            list_id, action_id=action.id, now=now_iso(self._clock)
        )
        result = await self.execute_action(client, action_id=action.id)
        if result.status is ActionStatus.FAILED:
            await self._shopping().mark_cart_failed(list_id, now=now_iso(self._clock))
        return result

    async def submit_grocery_order(self, client: ClientIdentity, *, list_id: str) -> Action:
        """Section 98's approval-gated checkout — R3, always approved
        (section 56). This only prepares the Action; a human must approve it
        in the Console (APPROVE_ACTION) before ``execute_action`` may commit
        and run it, the same two-step split ``book_appointment`` uses.
        """
        self._require(client, Capability.SHOPPING_CHECKOUT)
        shopping_list = await self._shopping().get(list_id)
        if shopping_list.status is not ShoppingListStatus.CART_BUILT:
            raise ValidationError(
                f"shopping list {list_id} is {shopping_list.status}, not a "
                "built cart; build_grocery_cart must succeed and be "
                "independently verified first",
                shopping_list_id=list_id,
            )
        payload = shopping_domain.checkout_payload(shopping_list)
        action = await self.prepare_action(
            client,
            ActionDraft(
                type=ActionType.SUBMIT_GROCERY_ORDER,
                payload=payload,
                task_id=shopping_list.task_id,
                target_entity_id=shopping_list.id,
            ),
        )
        await self._shopping().mark_submitting(
            list_id, action_id=action.id, now=now_iso(self._clock)
        )
        return action

    # --- bills and payees (BUILD_SPEC sections 72, 99) -------------------------
    #
    # Section 99: "Bills first. Payments last." Everything here records what is
    # owed and to whom. Moving money goes through the action outbox, which
    # means it inherits approval, idempotency, verification, audit, and the
    # emergency stop rather than re-deriving any of them.

    def _bills(self) -> BillRepository:
        if self._bills_repo is None:
            raise ConfigurationError(
                "no bill repository is configured", component="bills"
            )
        return self._bills_repo

    async def record_payee(self, client: ClientIdentity, draft: PayeeDraft) -> Action:
        """Propose a new payee — which section 72 says always needs approval.

        Returns the *action*, not the payee. A payee nobody approved is not a
        payee you can pay, so recording one is a proposal until a human
        decides; returning the payee here would read as though it were done.
        """
        self._require(client, Capability.FINANCIAL_PAYMENT)
        payee = Payee(
            id=Payee.make_id(draft.display_name),
            display_name=draft.display_name.strip(),
            provider_entity_id=draft.provider_entity_id,
            secret_ref=draft.secret_ref,
            created_at=now_iso(self._clock),
            created_by_client=client.client_id,
        )
        await self._bills().upsert_payee(payee)
        action = await self.prepare_action(
            client,
            ActionDraft(
                type=ActionType.ADD_PAYEE,
                payload={"payee_id": payee.id, "display_name": payee.display_name},
                target_entity_id=payee.provider_entity_id,
            ),
        )
        return action

    async def approve_payee(
        self, client: ClientIdentity, *, payee_id: str, approved_at: str | None = None
    ) -> Payee:
        """Mark a payee usable, once its ADD_PAYEE action was approved."""
        self._require(client, Capability.APPROVE_ACTION)
        payee = await self._bills().get_payee(payee_id)
        if payee is None:
            raise NotFoundError(f"no such payee: {payee_id}", payee_id=payee_id)
        payee.approved_at = approved_at or now_iso(self._clock)
        payee.approved_by = client.client_id
        saved = await self._bills().upsert_payee(payee)
        await self.audit(
            client, result="approved", intent="approve_payee",
            target=saved.id, risk="R4",
        )
        return saved

    async def list_payees(self, client: ClientIdentity) -> list[Payee]:
        self._require(client, Capability.READ_TASKS)
        return await self._bills().list_payees()

    async def record_bill(self, client: ClientIdentity, draft: BillDraft) -> Bill:
        """Record something owed. This tracks a debt; it pays nothing."""
        self._require(client, Capability.CREATE_TASK)
        payee = await self._bills().get_payee(draft.payee_id)
        if payee is None:
            raise NotFoundError(f"no such payee: {draft.payee_id}", payee_id=draft.payee_id)

        now = now_iso(self._clock)
        bill = Bill(
            id=Bill.make_id(),
            payee_id=draft.payee_id,
            description=draft.description.strip(),
            amount=validate_amount(draft.amount),
            currency=draft.currency.upper(),
            due_at=draft.due_at,
            source_document_id=draft.source_document_id,
            created_at=now,
            updated_at=now,
            created_by_client=client.client_id,
        )
        with operation("bill.record", bill_id=bill.id, client_id=client.client_id):
            created = await self._bills().create(bill)
        await self.audit(
            client, result="recorded", intent="record_bill",
            target=created.id, risk="R1",
        )
        return created

    async def get_bill(self, client: ClientIdentity, *, bill_id: str) -> Bill:
        self._require(client, Capability.READ_TASKS)
        bill = await self._bills().get(bill_id)
        if bill is None:
            raise NotFoundError(f"no such bill: {bill_id}", bill_id=bill_id)
        return bill

    async def list_bills(
        self,
        client: ClientIdentity,
        *,
        statuses: list[BillStatus] | None = None,
        limit: int = 100,
    ) -> list[Bill]:
        """What is owed. Readable by any client that may read tasks — knowing
        a bill is due is not the same as being able to pay it."""
        self._require(client, Capability.READ_TASKS)
        return await self._bills().list_bills(statuses=statuses, limit=limit)

    async def prepare_bill_payment(
        self, client: ClientIdentity, *, bill_id: str
    ) -> Action:
        """Prepare a payment for a bill (sections 57, 72).

        Returns an action that always needs approval — R4 is never
        policy-relaxable — and whose payload carries the exact amount, so a
        later edit to that amount invalidates whatever a human agreed to.
        """
        self._require(client, Capability.FINANCIAL_PAYMENT)
        bill = await self.get_bill(client, bill_id=bill_id)
        payee = await self._bills().get_payee(bill.payee_id)
        if payee is None:
            raise NotFoundError(f"no such payee: {bill.payee_id}", payee_id=bill.payee_id)

        may_pay(bill, payee)

        if bill.action_id is not None:
            # Section 60: before starting again, find out whether the previous
            # attempt exists. Two live payment actions for one bill is how a
            # bill gets paid twice.
            existing = await self._actions().get(bill.action_id)
            if existing.is_live:
                return existing

        action = await self.prepare_action(
            client,
            ActionDraft(
                type=ActionType.PREPARE_PAYMENT,
                payload={
                    "bill_id": bill.id,
                    "payee_id": payee.id,
                    "payee": payee.display_name,
                    "amount": bill.amount,
                    "currency": bill.currency,
                    "description": bill.description,
                },
                target_entity_id=payee.provider_entity_id,
            ),
        )
        bill.action_id = action.id
        bill.updated_at = now_iso(self._clock)
        await self._bills().update(bill)
        return action

    async def settle_bill(
        self, client: ClientIdentity, *, bill_id: str, external_reference: str
    ) -> Bill:
        """Mark a bill paid — only with the provider's own confirmation.

        Section 72 requires external confirmation and section 53 requires
        evidence; a bill is not paid because LifeOps believes it is.
        """
        self._require(client, Capability.FINANCIAL_PAYMENT)
        if not external_reference.strip():
            raise ValidationError(
                "a bill is settled only with the provider's confirmation",
                field="external_reference",
                bill_id=bill_id,
            )
        bill = await self.get_bill(client, bill_id=bill_id)
        bill.status = BillStatus.PAID
        bill.paid_at = now_iso(self._clock)
        bill.external_reference = external_reference
        bill.updated_at = bill.paid_at
        saved = await self._bills().update(bill)
        await self.audit(
            client, result="paid", intent="settle_bill", target=saved.id,
            risk="R4", verification=external_reference,
        )
        return saved

    # --- search -------------------------------------------------------------



    async def search(
        self, client: ClientIdentity, *, query: str, limit: int = 10
    ) -> SearchResults:
        """Universal search over people, preferences, and tasks (section 19).

        Phase 1 is a case-insensitive substring match; ranking and semantic
        retrieval arrive with the memory layer (Phase 2).
        """
        self._require(client, Capability.READ_WORLD)
        with operation("search.query", client_id=client.client_id):
            return SearchResults(
                people=await self._people.find_by_name(query),
                preferences=await self._preferences.search(query, limit=limit),
                tasks=list(await self._tasks.search(query, limit=limit)),
            )
