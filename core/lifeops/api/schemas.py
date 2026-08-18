"""HTTP request and response shapes for LifeOps Console."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from lifeops.domain.actions import ActionStatus, ActionType
from lifeops.domain.approvals import ApprovalStatus
from lifeops.domain.calendar import DEFAULT_HOLD_MINUTES, AppointmentStatus
from lifeops.domain.memory import MemorySource, MemoryType
from lifeops.domain.preferences import PreferenceSource
from lifeops.domain.service_request import ServiceRequestStatus
from lifeops.domain.shopping import ShoppingListStatus
from lifeops.domain.tasks import TaskPriority, TaskState, VerificationState
from lifeops.domain.waiting import DEFAULT_MAX_FOLLOWUPS, WaitingStatus


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


# --- console authentication --------------------------------------------------


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=500)


class LoginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # False when no console password is configured: the API is open and no
    # token is needed (or issued).
    auth_enabled: bool
    token: str | None = None
    expires_at: str | None = None


class MeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: str
    display_name: str
    auth_enabled: bool


class SetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Required once a password exists — proving the current one is what
    # authorises replacing it. Absent on first setup only.
    current_password: str | None = Field(default=None, max_length=500)
    new_password: str = Field(min_length=8, max_length=500)


class SetPasswordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auth_enabled: bool


# --- system logs sink ----------------------------------------------------------


class ConsoleLogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str = Field(default="info", max_length=10)
    message: str = Field(min_length=1, max_length=2000)
    context: dict[str, Any] | None = None
    ts: str | None = None


class ConsoleLogBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Bounded so a runaway Console tab cannot stream unbounded log volume into
    # the server.
    entries: list[ConsoleLogEntry] = Field(max_length=100)


# --- people ------------------------------------------------------------------


class PersonResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str
    is_primary: bool
    aliases: list[str]
    timezone: str | None
    created_at: str
    updated_at: str


class CreatePersonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=200)
    is_primary: bool = False
    aliases: list[str] = Field(default_factory=list)
    timezone: str | None = None


# --- preferences -------------------------------------------------------------


class PreferenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    subject_id: str
    key: str
    value: str
    source_type: PreferenceSource
    source_id: str | None
    confidence: float
    importance: float
    observed_at: str
    created_at: str
    valid_from: str
    valid_to: str | None
    supersedes: str | None
    created_by_client: str | None
    notes: str | None
    is_current: bool


class PreferenceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferences: list[PreferenceResponse]
    subject_id: str
    total: int


class SavePreferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=4000)
    subject_id: str | None = None
    source_type: PreferenceSource = PreferenceSource.USER_EXPLICIT
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    notes: str | None = None


# --- tasks -------------------------------------------------------------------


class TaskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str | None
    state: TaskState
    priority: TaskPriority
    created_at: str
    updated_at: str
    due_at: str | None
    owner_entity_id: str | None
    assigned_client: str | None
    current_action: str | None
    waiting_item_id: str | None
    verification_required: bool
    verification_state: str
    verification_evidence: str | None
    related_entity_ids: list[str]
    source: str | None
    created_by_client: str | None
    needs_attention: bool


class TaskListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tasks: list[TaskResponse]
    total: int
    by_state: dict[str, int]


class CreateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=20000)
    priority: TaskPriority = TaskPriority.MEDIUM
    due_at: str | None = None
    owner_entity_id: str | None = None
    related_entity_ids: list[str] = Field(default_factory=list)
    verification_required: bool = False
    source: str | None = None


class UpdateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=20000)
    state: TaskState | None = None
    priority: TaskPriority | None = None
    due_at: str | None = None
    owner_entity_id: str | None = None
    current_action: str | None = None
    related_entity_ids: list[str] | None = None
    verification_evidence: str | None = None


# --- memory (BUILD_SPEC sections 42-47) ---------------------------------------


class MemoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    subject_id: str
    type: MemoryType
    content: str
    source_type: MemorySource
    source_id: str | None
    observed_at: str
    created_at: str
    confidence: float
    importance: float
    valid_from: str
    valid_to: str | None
    supersedes: str | None
    entity_ids: list[str]
    created_by_client: str | None
    invalidation_reason: str | None


class MemoryListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memories: list[MemoryResponse]
    total: int


class MemoryHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: str
    history: list[MemoryResponse]
    total: int


class RememberRequest(BaseModel):
    """A new memory. None-valued fields are dropped before the domain draft is
    built so the domain's own defaults govern (source, confidence, importance).
    """

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=8000)
    type: MemoryType
    subject_id: str | None = None
    source_type: MemorySource | None = None
    source_id: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    entity_ids: list[str] | None = None


class InvalidateMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # A memory is closed, never deleted (section 45), so the reason is part of
    # the record's history and is required.
    reason: str = Field(min_length=1, max_length=2000)


class CorrectMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Correction is supersession: the old record closes and a new one carries
    # this content. Never an in-place edit.
    content: str = Field(min_length=1, max_length=8000)


# --- world (BUILD_SPEC sections 36, 39, 92) ------------------------------------
#
# These mirror ``lifeops.domain.world`` one-for-one. The wire contract is
# restated here rather than reusing the domain models directly so the Console's
# API can stay stable while the domain evolves — but the shapes must not
# diverge in meaning, and every field below has a domain counterpart.


class WorldEntityType(StrEnum):
    """Entity types the world API may create.

    The graph *reads* every type in BUILD_SPEC section 36 including persons;
    writes here are narrower on purpose — persons carry primary-user semantics
    and go through the person surface — so an invalid value is a 422 at the
    schema rather than a surprise in the domain.
    """

    HOUSEHOLD = "household"
    PROVIDER = "provider"
    ASSET = "asset"


class WorldRelationshipType(StrEnum):
    """The BUILD_SPEC section 39 relationship vocabulary, in the spec's order.

    Syntactic validity only: this mirrors ``domain.world.WorldRelationship``
    so the wire contract and the domain accept exactly the same set. Which
    types are meaningful between which entity kinds is deliberately not
    encoded — section 39 warns against predefining every relationship in a
    human life, and a rule invented here would be one the spec never asked
    for.
    """

    MEMBER_OF = "MEMBER_OF"
    RELATED_TO = "RELATED_TO"
    PREFERS = "PREFERS"
    OWNS = "OWNS"
    USES_PROVIDER = "USES_PROVIDER"
    ASSIGNED_TO = "ASSIGNED_TO"
    ABOUT = "ABOUT"
    WITH_PROVIDER = "WITH_PROVIDER"
    FOR_ASSET = "FOR_ASSET"
    WAITING_ON = "WAITING_ON"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"
    AUTHORIZES = "AUTHORIZES"
    CREATED_BY = "CREATED_BY"
    REQUESTED_BY = "REQUESTED_BY"
    EXECUTED_BY = "EXECUTED_BY"
    VERIFIED_BY = "VERIFIED_BY"
    DERIVED_FROM = "DERIVED_FROM"
    SUPERSEDES = "SUPERSEDES"
    RELATED_MEMORY = "RELATED_MEMORY"
    REFERENCES = "REFERENCES"


class WorldNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    entity_type: str
    label: str
    status: str


class WorldEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    target: str
    type: str


class WorldGraphResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[WorldNode]
    edges: list[WorldEdge]


class WorldEntityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    entity_type: str
    display_name: str
    facts: dict[str, str] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    created_by_client: str | None = None


class CreateEntityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: WorldEntityType
    display_name: str = Field(min_length=1, max_length=200)
    facts: dict[str, str] = Field(default_factory=dict)


class LinkRelationshipRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=200)
    target_id: str = Field(min_length=1, max_length=200)
    rel_type: WorldRelationshipType


class EntityDetailResponse(BaseModel):
    """The entity inspector aggregate (BUILD_SPEC section 16).

    ``relationships`` carries the raw edges and ``neighbors`` the same
    endpoints with their labels, so the panel can name a relation without a
    second round trip.

    A client that cannot read tasks or memory gets those lists empty rather
    than a 403: the inspector degrades to what the caller may see.
    """

    model_config = ConfigDict(extra="forbid")

    entity: WorldEntityResponse
    relationships: list[WorldEdge] = Field(default_factory=list)
    neighbors: list[WorldNode] = Field(default_factory=list)
    related_tasks: list[TaskResponse] = Field(default_factory=list)
    related_memories: list[MemoryResponse] = Field(default_factory=list)


class EntityHistoryResponse(BaseModel):
    """What Phase 3 can honestly report about an entity's past.

    ``covers`` states the scope in words. World entity facts are current-only
    until a later phase, so the history is the memory record referencing the
    entity — closed versions included — and never claims to be the durable
    audit log (Phase 4, section 62).
    """

    model_config = ConfigDict(extra="forbid")

    entity_id: str
    memories: list[MemoryResponse] = Field(default_factory=list)
    covers: list[str] = Field(default_factory=list)


# --- bills and payees (BUILD_SPEC sections 72, 99) -----------------------------


class PayeeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str
    provider_entity_id: str | None
    #: A handle into the secret store. Never a credential — section 72.
    secret_ref: str | None
    created_at: str
    approved_at: str | None
    approved_by: str | None
    created_by_client: str | None
    is_approved: bool


class PayeeListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payees: list[PayeeResponse]
    total: int


class CreatePayeeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=200)
    provider_entity_id: str | None = None
    secret_ref: str | None = Field(default=None, max_length=200)


class BillResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    payee_id: str
    description: str
    #: A string, never a number. Section 72 binds an approval to the amount,
    #: and JSON floats would reintroduce the precision the domain removed.
    amount: str
    currency: str
    due_at: str | None
    status: str
    action_id: str | None
    paid_at: str | None
    external_reference: str | None
    source_document_id: str | None
    created_at: str
    updated_at: str
    created_by_client: str | None
    is_payable: bool


class BillListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bills: list[BillResponse]
    total: int


class CreateBillRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payee_id: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=500)
    amount: str = Field(min_length=1, max_length=40)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    due_at: str | None = None
    source_document_id: str | None = None


class SettleBillRequest(BaseModel):
    """Section 72: external confirmation required. The reference is the
    provider's, not ours — a bill is not paid because LifeOps believes it."""

    model_config = ConfigDict(extra="forbid")

    external_reference: str = Field(min_length=1, max_length=200)


# --- configuration -----------------------------------------------------------


class UpdateProviderRequest(BaseModel):
    """Partial provider configuration update.

    Extra keys are permitted by the model and rejected by the validator
    against the provider's own field schema, which produces a message naming
    the offending field.
    """

    model_config = ConfigDict(extra="allow")


class UpdateSystemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    timezone: str | None = None
    household_name: str | None = None
    primary_person_id: str | None = None
    local_url: str | None = None
    setup_completed: bool | None = None
    safe_mode: bool | None = None
    # Loosely typed like every other field here: the enum check happens in
    # ConfigurationService.update_system, which reports it through the
    # LifeOps error taxonomy instead of FastAPI's default 422 shape.
    voice_mode: str | None = None


class TestProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    healthy: bool
    state: str
    message: str
    checked_at: str


class DiscoverResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    field: str
    options: list[dict[str, str]]
    message: str = ""


# --- voice (BUILD_SPEC section 27, phase 5) -----------------------------------


class SynthesizeSpeechRequest(BaseModel):
    """The Console's Preview voice button (BUILD_SPEC section 27).

    Every field but ``text`` is optional: previewing a voice before saving it
    means the caller can override just ``voice_id`` and let stability,
    model, and the rest fall back to what is already configured.
    """

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
    voice_id: str | None = None
    model_id: str | None = None
    output_format: str | None = None
    stability: float | None = Field(default=None, ge=0.0, le=1.0)
    similarity_boost: float | None = Field(default=None, ge=0.0, le=1.0)
    speed: float | None = Field(default=None, ge=0.5, le=2.0)


# --- durable work (BUILD_SPEC sections 13, 54-62, phase 4) --------------------
#
# These mirror ``lifeops.domain.waiting``, ``.actions``, ``.approvals``, and
# ``.audit`` one-for-one, the same discipline the world schemas follow.
# LifeOps Core decides everything that matters here — whether an action needs
# approval, when a waiting item escalates, what an approval authorises. The
# wire shapes below only carry that decision to the Console; none of them
# compute it.


class WaitingItemResponse(BaseModel):
    """One WaitingItem (BUILD_SPEC section 54), for the Waiting screen
    (section 13)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    task_id: str
    subject: str
    waiting_on_entity_id: str | None
    waiting_since: str
    expected_by: str | None
    next_action_at: str | None
    last_contact_at: str | None
    followup_count: int
    max_followups: int
    status: WaitingStatus
    attempt_count: int
    lease_owner: str | None
    lease_until: str | None
    created_by_client: str | None


class WaitingListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[WaitingItemResponse]
    total: int


class CreateWaitingItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=500)
    waiting_on_entity_id: str | None = None
    expected_by: str | None = None
    max_followups: int = Field(default=DEFAULT_MAX_FOLLOWUPS, ge=0, le=10)


class ActionResponse(BaseModel):
    """One outbox Action (BUILD_SPEC section 60)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: ActionType
    status: ActionStatus
    idempotency_key: str
    payload_hash: str
    payload: dict[str, Any]
    task_id: str | None
    target_entity_id: str | None
    created_at: str
    attempt_count: int
    last_attempt_at: str | None
    external_reference: str | None
    verification_state: VerificationState
    failure_reason: str | None
    created_by_client: str | None


class ActionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actions: list[ActionResponse]
    total: int


class ApprovalResponse(BaseModel):
    """One Approval (BUILD_SPEC sections 57-59), enriched for the Approval
    screen (section 58).

    ``action_payload`` and ``action_status`` are read from the action this
    approval binds to. Section 58 renders "what will happen" from the exact
    payload the human is approving, and re-fetching the action from the
    Console would be a second round trip for data the server already has on
    hand while building this response.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    action_id: str
    payload_hash: str
    requested_by: str
    approved_by: str | None
    approved_at: str | None
    expires_at: str
    consumed_at: str | None
    status: ApprovalStatus
    action_type: str
    #: Section 58's two lists: what saying yes authorises, and what it
    #: explicitly does not. Carried from the domain rather than composed here,
    #: so the boundary the human sees is the boundary the domain enforces.
    authorises_action: str
    does_not_authorise: list[str] = Field(default_factory=list)
    target_entity_id: str | None
    amount: str | None
    created_at: str
    action_payload: dict[str, Any] = Field(default_factory=dict)
    action_status: ActionStatus | None = None


class ApprovalListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approvals: list[ApprovalResponse]
    total: int


class DecideApprovalRequest(BaseModel):
    """Section 58: the Console only submits the decision. Whether approval
    was required, and what it binds to, was already decided by LifeOps Core
    when the approval was created."""

    model_config = ConfigDict(extra="forbid")

    approved: bool


class AuditRecordResponse(BaseModel):
    """One audit record (BUILD_SPEC section 62), append-only at the source."""

    model_config = ConfigDict(extra="forbid")

    id: str
    requester: str | None
    user: str | None
    client: str
    session: str | None
    intent: str | None
    tool: str | None
    risk: str | None
    approval: str | None
    action: str | None
    target: str | None
    result: str
    verification: str | None
    timestamp: str
    trace_id: str | None
    details: dict[str, str]


class AuditListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[AuditRecordResponse]
    total: int


# --- calendar (BUILD_SPEC sections 63, 96) ------------------------------------


class CalendarEventResponse(BaseModel):
    """One read-only calendar entry (section 63 step 1)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    external_event_id: str
    calendar_provider_id: str
    title: str
    start_at: str
    end_at: str
    location: str


class CalendarEventListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[CalendarEventResponse]
    total: int


class FreeBusySlotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_at: str
    end_at: str
    busy: bool


class FreeBusyResponse(BaseModel):
    """Section 63 step 2."""

    model_config = ConfigDict(extra="forbid")

    start_at: str
    end_at: str
    slots: list[FreeBusySlotResponse]


class AppointmentResponse(BaseModel):
    """One Appointment (section 63, 96): a hold or a booking LifeOps is
    driving, distinct from a bare ``CalendarEventResponse``."""

    model_config = ConfigDict(extra="forbid")

    id: str
    subject: str
    status: AppointmentStatus
    provider_entity_id: str | None
    task_id: str | None
    start_at: str
    end_at: str
    location: str
    notes: str
    calendar_provider_id: str
    hold_reference: str | None
    hold_expires_at: str | None
    external_event_id: str | None
    booking_action_id: str | None
    created_at: str
    updated_at: str
    created_by_client: str | None


class AppointmentListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appointments: list[AppointmentResponse]
    total: int


class CreateAppointmentHoldRequest(BaseModel):
    """Section 63 step 3."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=300)
    start_at: str
    end_at: str
    provider_entity_id: str | None = None
    task_id: str | None = None
    location: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=2000)
    hold_minutes: int = Field(default=DEFAULT_HOLD_MINUTES, ge=1, le=24 * 60)


# --- email (BUILD_SPEC sections 61, 64, 96) -----------------------------------


class EmailMessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str
    thread_id: str
    from_address: str
    to_addresses: list[str]
    subject: str
    snippet: str
    received_at: str
    folder: str


class EmailSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[EmailMessageResponse]
    total: int


class EmailThreadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread_id: str
    subject: str
    messages: list[EmailMessageResponse]


class SendEmailRequest(BaseModel):
    """Section 64's send/reply. A reply sets both ``thread_id`` and
    ``in_reply_to``; a new message sets neither."""

    model_config = ConfigDict(extra="forbid")

    to_addresses: list[str] = Field(min_length=1, max_length=25)
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=50_000)
    thread_id: str | None = None
    in_reply_to: str | None = None
    task_id: str | None = None
    target_entity_id: str | None = None


# --- documents (BUILD_SPEC sections 36, 64, 96) -------------------------------


class DocumentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    source: str
    source_ref: str
    mime_type: str
    summary: str
    created_at: str
    updated_at: str
    created_by_client: str | None


class CreateDocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    source: str = Field(min_length=1, max_length=50)
    source_ref: str = Field(default="", max_length=500)
    mime_type: str = Field(default="", max_length=200)
    summary: str = Field(default="", max_length=4000)


# --- service requests (BUILD_SPEC sections 36, 67, 68, 97, 101) ---------------


class ServiceRequestResponse(BaseModel):
    """One ServiceRequest (section 67's provider workflow, section 101's
    electrician scenario)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    subject: str
    status: ServiceRequestStatus
    task_id: str | None
    asset_entity_id: str | None
    provider_entity_id: str | None
    availability: list[str]
    diagnostic_fee: str | None
    waiting_item_id: str | None
    contact_action_id: str | None
    booking_action_id: str | None
    appointment_id: str | None
    notes: str
    created_at: str
    updated_at: str
    created_by_client: str | None


class ServiceRequestListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_requests: list[ServiceRequestResponse]
    total: int


class CreateServiceRequestRequest(BaseModel):
    """Section 101 step 1: identify the relevant asset."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=300)
    task_id: str | None = None
    asset_entity_id: str | None = None
    provider_entity_id: str | None = None
    notes: str = Field(default="", max_length=2000)


class RequestProviderContactRequest(BaseModel):
    """Section 101 steps 5-7: contact the provider by phone, or request a
    quote, to collect availability and a fee. ``authorize_charge`` and
    ``authorize_repairs`` are not fields here — BUILD_SPEC section 97's hard
    rule and section 101 step 9 are enforced by ``build_call_objective``
    never accepting them, not by validating a value a caller could submit."""

    model_config = ConfigDict(extra="forbid")

    provider_entity_id: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=200)
    collect: list[str] = Field(default_factory=list, max_length=10)


class RequestServiceBookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appointment_id: str = Field(min_length=1, max_length=200)


class ConfirmServiceBookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appointment_id: str = Field(min_length=1, max_length=200)


# --- shopping (BUILD_SPEC sections 36, 56, 98) --------------------------------


class ShoppingItemSchema(BaseModel):
    """Mirrors ``lifeops.domain.shopping.ShoppingItem`` one-for-one, the same
    discipline the rest of this module follows."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    quantity: str = Field(default="1", max_length=50)
    notes: str = Field(default="", max_length=300)
    substitution_allowed: bool = True
    substituted_with: str | None = None
    substitution_reason: str | None = None
    estimated_price: str | None = None


class ShoppingListResponse(BaseModel):
    """One ShoppingList (section 98's cart/checkout lifecycle)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    store: str
    task_id: str | None
    status: ShoppingListStatus
    items: list[ShoppingItemSchema]
    cart_reference: str | None
    order_reference: str | None
    cart_action_id: str | None
    checkout_action_id: str | None
    total_estimate: str | None
    created_at: str
    updated_at: str
    created_by_client: str | None


class ShoppingListListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shopping_lists: list[ShoppingListResponse]
    total: int


class CreateShoppingListRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    store: str = Field(default="", max_length=200)
    task_id: str | None = None
    items: list[ShoppingItemSchema] = Field(default_factory=list)


class AddShoppingItemsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ShoppingItemSchema] = Field(min_length=1, max_length=60)


class SubstitutionRequest(BaseModel):
    """Section 98's substitutions."""

    model_config = ConfigDict(extra="forbid")

    item_name: str = Field(min_length=1, max_length=200)
    substituted_with: str = Field(min_length=1, max_length=200)
    reason: str = Field(default="", max_length=300)


class ProductResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    price: str | None = None
    availability: str | None = None
    url: str | None = None


class ShoppingSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[ProductResultResponse]
    total: int
