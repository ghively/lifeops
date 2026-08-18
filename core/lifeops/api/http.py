"""LifeOps Core HTTP API — the interface LifeOps Console talks to.

This is an adapter. It resolves a client identity, converts request shapes to
domain drafts, calls LifeOpsCore, and converts the result back. No business
rule lives here; anything that decides what is *allowed* belongs in policy or
the domain layer, where the MCP surface gets it too.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from lifeops.api.events import router as events_router
from lifeops.api.schemas import (
    ActionListResponse,
    ActionResponse,
    AddShoppingItemsRequest,
    AppointmentListResponse,
    AppointmentResponse,
    ApprovalListResponse,
    ApprovalResponse,
    AuditListResponse,
    AuditRecordResponse,
    BillListResponse,
    BillResponse,
    CalendarEventListResponse,
    CalendarEventResponse,
    ConfirmServiceBookingRequest,
    ConsoleLogBatch,
    CorrectMemoryRequest,
    CreateAppointmentHoldRequest,
    CreateBillRequest,
    CreateDocumentRequest,
    CreateEntityRequest,
    CreateKnowledgeRequest,
    CreatePayeeRequest,
    CreatePersonRequest,
    CreateServiceRequestRequest,
    CreateShoppingListRequest,
    CreateTaskRequest,
    CreateWaitingItemRequest,
    DecideApprovalRequest,
    DiscoverResponse,
    DocumentResponse,
    EmailMessageResponse,
    EmailSearchResponse,
    EmailThreadResponse,
    EntityDetailResponse,
    EntityHistoryResponse,
    ErrorResponse,
    FreeBusyResponse,
    FreeBusySlotResponse,
    InvalidateMemoryRequest,
    KnowledgeListResponse,
    KnowledgeResponse,
    LinkRelationshipRequest,
    LoginRequest,
    LoginResponse,
    MemoryHistoryResponse,
    MemoryListResponse,
    MemoryResponse,
    MeResponse,
    PayeeListResponse,
    PayeeResponse,
    PersonResponse,
    PreferenceListResponse,
    PreferenceResponse,
    ProductResultResponse,
    PromoteMemoryRequest,
    RememberRequest,
    RequestProviderContactRequest,
    RequestServiceBookingRequest,
    SavePreferenceRequest,
    SaveWorkflowTemplateRequest,
    SendEmailRequest,
    ServiceRequestListResponse,
    ServiceRequestResponse,
    SetPasswordRequest,
    SetPasswordResponse,
    SettleBillRequest,
    ShoppingListListResponse,
    ShoppingListResponse,
    ShoppingSearchResponse,
    SubstitutionRequest,
    SynthesizeSpeechRequest,
    TaskListResponse,
    TaskResponse,
    TestProviderResponse,
    UpdateProviderRequest,
    UpdateSystemRequest,
    UpdateTaskRequest,
    WaitingItemResponse,
    WaitingListResponse,
    WorkflowTemplateListResponse,
    WorkflowTemplateResponse,
    WorldEdge,
    WorldEntityResponse,
    WorldGraphResponse,
    WorldNode,
    WorldRelationshipType,
)
from lifeops.auth import InvalidCredentialsError
from lifeops.config.provider_registry import all_providers, get_provider
from lifeops.container import Container
from lifeops.domain.actions import Action, ActionStatus
from lifeops.domain.approvals import Approval
from lifeops.domain.audit import AuditRecord
from lifeops.domain.bills import Bill, BillDraft, BillStatus, Payee, PayeeDraft
from lifeops.domain.calendar import (
    Appointment,
    AppointmentHoldDraft,
    CalendarEvent,
    FreeBusyResult,
)
from lifeops.domain.documents import Document, DocumentDraft
from lifeops.domain.email import EmailMessage, EmailSendDraft, EmailThread
from lifeops.domain.knowledge import Knowledge, KnowledgeDraft
from lifeops.domain.memory import MemoryDraft, MemoryRecord, MemoryType
from lifeops.domain.people import Person, PersonDraft
from lifeops.domain.preferences import Preference, PreferenceDraft
from lifeops.domain.service_request import ServiceRequest, ServiceRequestDraft
from lifeops.domain.shopping import (
    ShoppingItem,
    ShoppingList,
    ShoppingListDraft,
    ShoppingListStatus,
    SubstitutionDraft,
)
from lifeops.domain.tasks import Task, TaskDraft, TaskState, TaskUpdate, transition_table
from lifeops.domain.voice import SynthesisOptions
from lifeops.domain.waiting import WaitingDraft, WaitingItem, WaitingStatus
from lifeops.domain.workflow_templates import WorkflowTemplate, WorkflowTemplateDraft
from lifeops.domain.world import EntityDetail, EntityDraft, WorldGraph
from lifeops.domain.world import WorldEntity as DomainWorldEntity
from lifeops.errors import LifeOpsError, NotFoundError, ProviderNotConfiguredError, ValidationError
from lifeops.events import CONFIG_CHANGED
from lifeops.observability.logging import configure_logging, redact, trace_context
from lifeops.policy import CapabilityGrant, ClientIdentity, all_clients, resolve_client
from lifeops.policy.capabilities import CONSOLE, Capability, require
from lifeops.settings import Settings, get_settings
from lifeops.voice.local import LocalASRProvider, LocalTTSProvider

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


# --- dependencies ------------------------------------------------------------


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_client(
    x_lifeops_client: Annotated[str | None, Header()] = None,
) -> ClientIdentity:
    """Resolve the calling client identity.

    Requests without the header are treated as the Console, because this API
    is the Console's transport. MCP clients declare themselves over MCP and do
    not reach these routes.
    """
    if not x_lifeops_client:
        return CONSOLE
    return resolve_client(x_lifeops_client)


ContainerDep = Annotated[Container, Depends(get_container)]
ClientDep = Annotated[ClientIdentity, Depends(get_client)]


def get_configuring_client(
    client: Annotated[ClientIdentity, Depends(get_client)],
) -> ClientIdentity:
    """The caller, proven to hold MANAGE_CONFIGURATION.

    The config surface deliberately bypasses LifeOpsCore (it mutates the
    processes' shared config file, not NornicDB), so the capability check
    the core would have run has to happen here — without it the manifest's
    Console-only grant was decoration, and any identity could flip safe
    mode or point a provider somewhere else. ``safe_mode=False`` on
    purpose: configuration is how the emergency stop is lifted, so the
    stop must not lock the door to its own switch.
    """
    require(client, Capability.MANAGE_CONFIGURATION, safe_mode=False)
    return client


ConfiguringClientDep = Annotated[ClientIdentity, Depends(get_configuring_client)]


# --- serialisers -------------------------------------------------------------


def _person_out(person: Person) -> PersonResponse:
    return PersonResponse(**person.model_dump())


def _preference_out(pref: Preference) -> PreferenceResponse:
    return PreferenceResponse(**pref.model_dump(), is_current=pref.is_current)


def _task_out(task: Task) -> TaskResponse:
    return TaskResponse(**task.model_dump(), needs_attention=task.needs_attention)


def _memory_out(record: MemoryRecord) -> MemoryResponse:
    return MemoryResponse(**record.model_dump())


def _graph_out(graph: WorldGraph) -> WorldGraphResponse:
    return WorldGraphResponse(**graph.model_dump())


def _entity_out(entity: DomainWorldEntity) -> WorldEntityResponse:
    return WorldEntityResponse(**entity.model_dump())


def _entity_detail_out(detail: EntityDetail) -> EntityDetailResponse:
    return EntityDetailResponse(
        entity=_entity_out(detail.entity),
        relationships=[WorldEdge(**e.model_dump()) for e in detail.relationships],
        neighbors=[WorldNode(**n.model_dump()) for n in detail.neighbors],
        related_tasks=[_task_out(t) for t in detail.related_tasks],
        related_memories=[_memory_out(m) for m in detail.related_memories],
    )


def _waiting_out(item: WaitingItem) -> WaitingItemResponse:
    return WaitingItemResponse(**item.model_dump())


async def _approval_out(
    container: Container, client: ClientIdentity, approval: Approval
) -> ApprovalResponse:
    """Enrich an approval with the payload of the action it binds to.

    The Approval screen (section 58) renders "what will happen" from the
    exact payload the human is approving; this is a second call to an
    already-existing operation, not a new business rule.
    """
    action: Action | None
    try:
        action = await container.core.get_action(client, action_id=approval.action_id)
    except NotFoundError:
        action = None
    return ApprovalResponse(
        **approval.model_dump(),
        action_payload=action.payload if action is not None else {},
        action_status=action.status if action is not None else None,
    )


def _action_out(action: Action) -> ActionResponse:
    return ActionResponse(**action.model_dump())


def _audit_out(record: AuditRecord) -> AuditRecordResponse:
    return AuditRecordResponse(**record.model_dump())


def _calendar_event_out(event: CalendarEvent) -> CalendarEventResponse:
    return CalendarEventResponse(**event.model_dump())


def _free_busy_out(result: FreeBusyResult) -> FreeBusyResponse:
    return FreeBusyResponse(
        start_at=result.start_at,
        end_at=result.end_at,
        slots=[FreeBusySlotResponse(**s.model_dump()) for s in result.slots],
    )


def _appointment_out(appointment: Appointment) -> AppointmentResponse:
    return AppointmentResponse(**appointment.model_dump())


def _email_message_out(message: EmailMessage) -> EmailMessageResponse:
    return EmailMessageResponse(**message.model_dump())


def _email_thread_out(thread: EmailThread) -> EmailThreadResponse:
    return EmailThreadResponse(
        thread_id=thread.thread_id,
        subject=thread.subject,
        messages=[_email_message_out(m) for m in thread.messages],
    )


def _document_out(document: Document) -> DocumentResponse:
    return DocumentResponse(**document.model_dump())


def _knowledge_out(knowledge: Knowledge) -> KnowledgeResponse:
    return KnowledgeResponse(**knowledge.model_dump())


def _service_request_out(request: ServiceRequest) -> ServiceRequestResponse:
    return ServiceRequestResponse(**request.model_dump())


def _shopping_list_out(shopping_list: ShoppingList) -> ShoppingListResponse:
    return ShoppingListResponse(**shopping_list.model_dump())


def _publish_config_changed(container: Container, **fields: Any) -> None:
    """Notify Console subscribers that configuration changed.

    Configuration mutations go through ConfigurationService rather than
    LifeOpsCore today, so the adapter publishes the notification; this is
    fan-out, not a business rule.
    """
    events = getattr(container, "events", None)
    if events is not None:
        events.publish({"type": CONFIG_CHANGED, **fields})


# --- routes ------------------------------------------------------------------

router = APIRouter(prefix=API_PREFIX)


@router.get("/health", tags=["system"])
async def health(container: ContainerDep) -> dict[str, Any]:
    return {"status": "ok", "components": await container.health()}


# --- console authentication (SECURITY.md debt #1) ----------------------------


@router.post("/auth/login", response_model=LoginResponse, tags=["auth"])
async def login(payload: LoginRequest, request: Request) -> LoginResponse:
    """Exchange the console password for a bearer token.

    When no console password is configured, auth is disabled and the response
    says so instead of issuing a token — the Console then skips its login
    screen entirely.
    """
    auth = getattr(request.app.state.container, "auth", None)
    if auth is None or not auth.enabled:
        return LoginResponse(auth_enabled=False)
    token, expires_at = auth.login(payload.password)
    return LoginResponse(auth_enabled=True, token=token, expires_at=expires_at)


@router.get("/auth/me", response_model=MeResponse, tags=["auth"])
async def auth_me(request: Request, client: ClientDep) -> MeResponse:
    """The identity behind the current session, for the Console's header."""
    auth = getattr(request.app.state.container, "auth", None)
    return MeResponse(
        client_id=client.client_id,
        display_name=client.display_name,
        auth_enabled=bool(auth is not None and auth.enabled),
    )


@router.post("/auth/password", response_model=SetPasswordResponse, tags=["auth"])
async def set_password(payload: SetPasswordRequest, request: Request) -> SetPasswordResponse:
    """Set or change the console password — the only way auth gets turned on.

    Once a password exists, changing it requires the current one; the bearer
    middleware additionally requires a valid session whenever auth is enabled,
    so this route can never be driven by an anonymous caller. First setup (no
    password yet) is intentionally open on loopback, matching login.
    """
    auth = getattr(request.app.state.container, "auth", None)
    if auth is None:
        raise ValidationError("console authentication is not available")
    if auth.enabled and not (
        payload.current_password and auth.check_password(payload.current_password)
    ):
        raise InvalidCredentialsError("the current console password did not match")
    auth.set_password(payload.new_password)
    return SetPasswordResponse(auth_enabled=auth.enabled)


@router.get("/system/status", tags=["system"])
async def system_status(container: ContainerDep, client: ClientDep) -> dict[str, Any]:
    """Everything the System screen renders in one call."""
    components = await container.health()
    return {
        "components": components,
        "providers": [p.model_dump() for p in container.config.list_status()],
        "system": container.config.get_system().model_dump(),
        "clients": [CapabilityGrant.of(c).model_dump() for c in all_clients()],
        "requesting_client": CapabilityGrant.of(client).model_dump(),
    }


@router.get("/system/activity", tags=["system"])
async def system_activity(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    """Recent semantic operations, newest first.

    Ephemeral by design: an in-memory ring buffer that dies with the process.
    This is the Activity screen's "what just happened", NOT the durable audit
    log — that arrives in Phase 4 (BUILD_SPEC section 62).
    """
    activity = getattr(request.app.state.container, "activity", None)
    entries = activity.recent(limit=limit) if activity is not None else []
    return {"entries": entries, "ephemeral": True}


@router.post("/system/logs", status_code=202, tags=["system"])
async def accept_console_logs(payload: ConsoleLogBatch) -> dict[str, int]:
    """Sink for the Console's client-side logger.

    Entries are re-logged through the server logger under the ``lifeops.console``
    component with context redacted, so a console UI error shows up in the same
    JSON stream as everything else (BUILD_SPEC section 78). The batch size is
    bounded by the schema.
    """
    console_logger = logging.getLogger("lifeops.console")
    for entry in payload.entries:
        level = _LOG_LEVELS.get(entry.level.lower(), logging.INFO)
        console_logger.log(
            level,
            "%s",
            entry.message,
            extra={
                "source": "console",
                "console_ts": entry.ts,
                "context": redact(entry.context) if entry.context else {},
            },
        )
    return {"accepted": len(payload.entries)}


#: Browser log levels that map onto server log levels; anything else is INFO.
_LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


# --- people ---


@router.get("/people/me", response_model=PersonResponse, tags=["people"])
async def get_me(container: ContainerDep, client: ClientDep) -> PersonResponse:
    return _person_out(await container.core.get_person(client))


@router.get("/people", tags=["people"])
async def list_people(
    container: ContainerDep,
    client: ClientDep,
    name: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict[str, Any]:
    people = (
        await container.core.find_people(client, name=name)
        if name
        else await container.core.list_people(client, limit=limit)
    )
    return {"people": [_person_out(p).model_dump() for p in people], "total": len(people)}


@router.get("/people/{person_id}", response_model=PersonResponse, tags=["people"])
async def get_person(
    person_id: str, container: ContainerDep, client: ClientDep
) -> PersonResponse:
    return _person_out(await container.core.get_person(client, person_id=person_id))


@router.post("/people", response_model=PersonResponse, status_code=201, tags=["people"])
async def create_person(
    payload: CreatePersonRequest, container: ContainerDep, client: ClientDep
) -> PersonResponse:
    person = await container.core.create_person(
        client, PersonDraft(**payload.model_dump())
    )
    return _person_out(person)


# --- preferences ---


@router.get("/preferences", response_model=PreferenceListResponse, tags=["preferences"])
async def list_preferences(
    container: ContainerDep,
    client: ClientDep,
    subject_id: Annotated[str | None, Query()] = None,
    key_prefix: Annotated[str | None, Query()] = None,
) -> PreferenceListResponse:
    prefs = await container.core.get_preferences(
        client, subject_id=subject_id, key_prefix=key_prefix
    )
    resolved = prefs[0].subject_id if prefs else (subject_id or "")
    if not resolved:
        resolved = (await container.core.get_person(client)).id
    return PreferenceListResponse(
        preferences=[_preference_out(p) for p in prefs],
        subject_id=resolved,
        total=len(prefs),
    )


@router.get("/preferences/history", tags=["preferences"])
async def preference_history(
    container: ContainerDep,
    client: ClientDep,
    key: Annotated[str, Query()],
    subject_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """Every record for a key, including superseded ones."""
    history = await container.core.get_preference_history(
        client, key=key, subject_id=subject_id
    )
    return {
        "key": key,
        "history": [_preference_out(p).model_dump() for p in history],
        "total": len(history),
    }


@router.post(
    "/preferences", response_model=PreferenceResponse, status_code=201, tags=["preferences"]
)
async def save_preference(
    payload: SavePreferenceRequest, container: ContainerDep, client: ClientDep
) -> PreferenceResponse:
    pref = await container.core.save_preference(
        client, PreferenceDraft(**payload.model_dump())
    )
    return _preference_out(pref)


@router.delete(
    "/preferences/{preference_id}", response_model=PreferenceResponse, tags=["preferences"]
)
async def invalidate_preference(
    preference_id: str, container: ContainerDep, client: ClientDep
) -> PreferenceResponse:
    """Close a preference's validity window. The record is never deleted."""
    pref = await container.core.invalidate_preference(
        client, preference_id=preference_id
    )
    return _preference_out(pref)


# --- memory (BUILD_SPEC sections 42-47) ---------------------------------------
#
# Memory may observe, never rewrite transactional reality (section 44). Every
# rule enforcing that lives in LifeOpsCore and the domain; these routes only
# translate shapes and carry the capability denial, 404, and 422 contracts.
# Mutations publish ``memory_changed`` from LifeOpsCore itself, as task
# mutations do.


@router.get("/memory", response_model=MemoryListResponse, tags=["memory"])
async def list_memories(
    container: ContainerDep,
    client: ClientDep,
    subject_id: Annotated[str | None, Query()] = None,
    type: Annotated[list[MemoryType] | None, Query()] = None,
    include_invalid: Annotated[bool, Query()] = False,
    invalidated_only: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> MemoryListResponse:
    """Current memories, most relevant first.

    A blank-query recall is the list operation: LifeOpsCore exposes no
    separate listing. ``include_invalid`` (current *and* closed, merged into
    one ranked list) is refused loudly rather than silently ignored — that
    merge isn't built. ``invalidated_only`` is a different, narrower thing
    that is built: section 17's dedicated "invalidated/superseded history"
    view, closed records only, not mixed with current ones.
    """
    if include_invalid:
        raise ValidationError(
            "merging current and invalidated memories into one list is not "
            "supported; pass invalidated_only for the closed-records view, or "
            "open a memory's history instead",
            reason="include_invalid_unsupported",
        )
    if invalidated_only:
        records = await container.core.list_invalidated_memories(
            client, subject_id=subject_id, memory_types=type, limit=limit
        )
    else:
        records = await container.core.recall(
            client, query="", subject_id=subject_id, memory_types=type, limit=limit
        )
    return MemoryListResponse(
        memories=[_memory_out(r) for r in records], total=len(records)
    )


@router.post("/memory", response_model=MemoryResponse, status_code=201, tags=["memory"])
async def remember(
    payload: RememberRequest, container: ContainerDep, client: ClientDep
) -> MemoryResponse:
    """Store a memory. This records an observation; it executes nothing."""
    record = await container.core.remember(
        client, MemoryDraft(**payload.model_dump(exclude_none=True))
    )
    return _memory_out(record)


@router.get("/memory/search", response_model=MemoryListResponse, tags=["memory"])
async def search_memories(
    container: ContainerDep,
    client: ClientDep,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    subject_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> MemoryListResponse:
    records = await container.core.recall(
        client, query=q, subject_id=subject_id, limit=limit
    )
    return MemoryListResponse(
        memories=[_memory_out(r) for r in records], total=len(records)
    )


@router.get("/memory/{memory_id}", response_model=MemoryResponse, tags=["memory"])
async def get_memory(
    memory_id: str, container: ContainerDep, client: ClientDep
) -> MemoryResponse:
    return _memory_out(await container.core.get_memory(client, memory_id=memory_id))


@router.get(
    "/memory/{memory_id}/history",
    response_model=MemoryHistoryResponse,
    tags=["memory"],
)
async def memory_history(
    memory_id: str, container: ContainerDep, client: ClientDep
) -> MemoryHistoryResponse:
    """The supersession chain: every version of this memory, current and closed."""
    history = await container.core.memory_history(client, memory_id=memory_id)
    return MemoryHistoryResponse(
        memory_id=memory_id,
        history=[_memory_out(r) for r in history],
        total=len(history),
    )


@router.post(
    "/memory/{memory_id}/invalidate", response_model=MemoryResponse, tags=["memory"]
)
async def invalidate_memory(
    memory_id: str,
    payload: InvalidateMemoryRequest,
    container: ContainerDep,
    client: ClientDep,
) -> MemoryResponse:
    """Close a memory's validity window. The record is never deleted."""
    record = await container.core.invalidate_memory(
        client, memory_id=memory_id, reason=payload.reason
    )
    return _memory_out(record)


@router.post(
    "/memory/{memory_id}/correct", response_model=MemoryResponse, tags=["memory"]
)
async def correct_memory(
    memory_id: str,
    payload: CorrectMemoryRequest,
    container: ContainerDep,
    client: ClientDep,
) -> MemoryResponse:
    """Correct a memory: the old record closes and the returned one supersedes it."""
    record = await container.core.correct_memory(
        client, memory_id=memory_id, new_content=payload.content
    )
    return _memory_out(record)


@router.post(
    "/memory/{memory_id}/promote", response_model=PreferenceResponse, tags=["memory"]
)
async def promote_memory(
    memory_id: str,
    payload: PromoteMemoryRequest,
    container: ContainerDep,
    client: ClientDep,
) -> PreferenceResponse:
    """Section 47's confirm/promote step: a reviewed PREFERENCE_CANDIDATE
    becomes a real preference, and the candidate closes out."""
    preference = await container.core.promote_memory(
        client, memory_id=memory_id, key=payload.key, value=payload.value
    )
    return _preference_out(preference)


# --- tasks ---


@router.get("/tasks", response_model=TaskListResponse, tags=["tasks"])
async def list_tasks(
    container: ContainerDep,
    client: ClientDep,
    state: Annotated[list[TaskState] | None, Query()] = None,
    owner_entity_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TaskListResponse:
    tasks = await container.core.list_tasks(
        client,
        states=state,
        owner_entity_id=owner_entity_id,
        limit=limit,
        offset=offset,
    )
    by_state = await container.core.count_tasks_by_state(client)
    return TaskListResponse(
        tasks=[_task_out(t) for t in tasks],
        total=sum(by_state.values()),
        by_state=by_state,
    )


@router.get("/tasks/transitions", tags=["tasks"])
async def task_transitions() -> dict[str, Any]:
    """The authoritative task state machine, for the Console to render.

    Served from the domain so the Console no longer duplicates a table that
    can drift from the server's enforcement (kimi.md Phase 1 debts).
    """
    return {"transitions": transition_table()}


@router.get("/tasks/{task_id}", response_model=TaskResponse, tags=["tasks"])
async def get_task(
    task_id: str, container: ContainerDep, client: ClientDep
) -> TaskResponse:
    return _task_out(await container.core.get_task(client, task_id=task_id))


@router.post("/tasks", response_model=TaskResponse, status_code=201, tags=["tasks"])
async def create_task(
    payload: CreateTaskRequest, container: ContainerDep, client: ClientDep
) -> TaskResponse:
    task = await container.core.create_task(client, TaskDraft(**payload.model_dump()))
    return _task_out(task)


@router.patch("/tasks/{task_id}", response_model=TaskResponse, tags=["tasks"])
async def update_task(
    task_id: str,
    payload: UpdateTaskRequest,
    container: ContainerDep,
    client: ClientDep,
) -> TaskResponse:
    task = await container.core.update_task(
        client,
        task_id=task_id,
        update=TaskUpdate(**payload.model_dump(exclude_unset=True)),
    )
    return _task_out(task)


# --- world (BUILD_SPEC section 92) -------------------------------------------
#
# The Console's world surface: graph, neighborhood, entity inspector, and the
# narrow write side (households, providers, assets, and their relationships).
# Every rule — capability checks, the relationship vocabulary, what history can
# honestly report — lives in LifeOpsCore and the domain. These routes translate
# shapes and carry the 404/409/422 contracts.


@router.get("/world/graph", response_model=WorldGraphResponse, tags=["world"])
async def world_graph(
    container: ContainerDep,
    client: ClientDep,
    types: Annotated[list[str] | None, Query()] = None,
    query: Annotated[str, Query(max_length=200)] = "",
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> WorldGraphResponse:
    """The world graph, narrowed by entity type and search text.

    ``types`` repeats (``?types=asset&types=provider``) rather than taking a
    comma-joined string, so a display name containing a comma cannot become
    two filters.
    """
    graph = await container.core.world_graph(
        client, query=query, entity_types=types, limit=limit
    )
    return _graph_out(graph)


@router.get("/world/neighborhood", response_model=WorldGraphResponse, tags=["world"])
async def world_neighborhood(
    container: ContainerDep,
    client: ClientDep,
    entity_id: Annotated[str, Query(min_length=1, max_length=200)],
    depth: Annotated[int, Query(ge=1, le=3)] = 1,
) -> WorldGraphResponse:
    """The subgraph around one entity, out to ``depth`` hops."""
    graph = await container.core.world_neighborhood(
        client, entity_id=entity_id, depth=depth
    )
    return _graph_out(graph)


@router.get(
    "/world/entities/{entity_id}",
    response_model=EntityDetailResponse,
    tags=["world"],
)
async def get_entity_detail(
    entity_id: str, container: ContainerDep, client: ClientDep
) -> EntityDetailResponse:
    """The entity inspector aggregate: entity, facts, relationships, related
    tasks, and memories in one call (section 16)."""
    detail = await container.core.get_entity_detail(client, entity_id=entity_id)
    return _entity_detail_out(detail)


@router.get(
    "/world/entities/{entity_id}/history",
    response_model=EntityHistoryResponse,
    tags=["world"],
)
async def entity_history(
    entity_id: str, container: ContainerDep, client: ClientDep
) -> EntityHistoryResponse:
    """The recorded history of an entity, newest first, with its own scope
    stated in ``covers``."""
    history = await container.core.entity_history(client, entity_id=entity_id)
    return EntityHistoryResponse(
        entity_id=history.entity_id,
        memories=[_memory_out(m) for m in history.memories],
        covers=history.covers,
    )


@router.post(
    "/world/entities",
    response_model=WorldEntityResponse,
    status_code=201,
    tags=["world"],
)
async def create_entity(
    payload: CreateEntityRequest, container: ContainerDep, client: ClientDep
) -> WorldEntityResponse:
    """Create a household, provider, or asset. This records world state; it
    executes nothing."""
    entity = await container.core.create_entity(client, EntityDraft(**payload.model_dump()))
    return _entity_out(entity)


@router.post(
    "/world/relationships",
    response_model=WorldEdge,
    status_code=201,
    tags=["world"],
)
async def link_entities(
    payload: LinkRelationshipRequest, container: ContainerDep, client: ClientDep
) -> WorldEdge:
    """Relate two existing entities."""
    edge = await container.core.link_entities(
        client,
        source_id=payload.source_id,
        target_id=payload.target_id,
        rel_type=str(payload.rel_type),
    )
    return WorldEdge(**edge.model_dump())


@router.delete("/world/relationships", status_code=204, tags=["world"])
async def unlink_entities(
    container: ContainerDep,
    client: ClientDep,
    source_id: Annotated[str, Query(min_length=1, max_length=200)],
    target_id: Annotated[str, Query(min_length=1, max_length=200)],
    rel_type: Annotated[WorldRelationshipType, Query()],
) -> None:
    """Remove a relationship, identified by its (source, target, type) triple.

    The triple travels as query parameters, not a body: DELETE bodies are
    dropped by some proxies and HTTP clients, and the relationship has no id
    of its own to put in the path.
    """
    await container.core.unlink_entities(
        client,
        source_id=source_id,
        target_id=target_id,
        rel_type=str(rel_type),
    )


# --- durable work (BUILD_SPEC sections 13, 54-62, phase 4) -------------------
#
# Waiting items, the action outbox, approvals, and the durable audit log.
# LifeOps Core decides every rule that matters here — whether a follow-up
# escalates, whether an action needs approval, what an approval authorises,
# what belongs in the audit trail. These routes translate shapes and carry
# the 404/409/422/403 contracts, exactly like every other adapter route.


@router.get("/waiting", response_model=WaitingListResponse, tags=["waiting"])
async def list_waiting(
    container: ContainerDep,
    client: ClientDep,
    status: Annotated[list[WaitingStatus] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> WaitingListResponse:
    """The Waiting screen's list (BUILD_SPEC section 13)."""
    items = await container.core.list_waiting(client, statuses=status, limit=limit)
    return WaitingListResponse(items=[_waiting_out(i) for i in items], total=len(items))


@router.get("/waiting/{waiting_id}", response_model=WaitingItemResponse, tags=["waiting"])
async def get_waiting_item(
    waiting_id: str, container: ContainerDep, client: ClientDep
) -> WaitingItemResponse:
    return _waiting_out(
        await container.core.get_waiting_item(client, waiting_id=waiting_id)
    )


@router.post(
    "/waiting", response_model=WaitingItemResponse, status_code=201, tags=["waiting"]
)
async def create_waiting_item(
    payload: CreateWaitingItemRequest, container: ContainerDep, client: ClientDep
) -> WaitingItemResponse:
    """Record that a task is blocked on someone else (section 54). This
    captures a fact about the world; it sends nothing."""
    item = await container.core.create_waiting_item(
        client, WaitingDraft(**payload.model_dump())
    )
    return _waiting_out(item)


@router.post(
    "/waiting/{waiting_id}/followup",
    response_model=WaitingItemResponse,
    tags=["waiting"],
)
async def record_waiting_followup(
    waiting_id: str, container: ContainerDep, client: ClientDep
) -> WaitingItemResponse:
    """Log a follow-up, escalating when the budget is spent (section 55)."""
    item = await container.core.record_followup(client, waiting_id=waiting_id)
    return _waiting_out(item)


@router.post(
    "/waiting/{waiting_id}/resolve",
    response_model=WaitingItemResponse,
    tags=["waiting"],
)
async def resolve_waiting_item(
    waiting_id: str, container: ContainerDep, client: ClientDep
) -> WaitingItemResponse:
    """Close a waiting item because the thing arrived."""
    item = await container.core.resolve_waiting_item(client, waiting_id=waiting_id)
    return _waiting_out(item)


@router.get("/approvals", response_model=ApprovalListResponse, tags=["approvals"])
async def list_pending_approvals(
    container: ContainerDep,
    client: ClientDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ApprovalListResponse:
    """What the Approval screen shows (BUILD_SPEC section 58)."""
    approvals = await container.core.list_pending_approvals(client, limit=limit)
    out = [await _approval_out(container, client, a) for a in approvals]
    return ApprovalListResponse(approvals=out, total=len(out))


@router.post(
    "/approvals/{approval_id}/decide",
    response_model=ApprovalResponse,
    tags=["approvals"],
)
async def decide_approval(
    approval_id: str,
    payload: DecideApprovalRequest,
    container: ContainerDep,
    client: ClientDep,
) -> ApprovalResponse:
    """Approve or decline one exact action (sections 57-58).

    LifeOps Core already decided whether approval was required, and what this
    approval binds to, when it was created. This route only submits the
    human's decision.
    """
    approval = await container.core.decide_approval(
        client, approval_id=approval_id, approved=payload.approved
    )
    return await _approval_out(container, client, approval)


@router.get("/actions", response_model=ActionListResponse, tags=["actions"])
async def list_actions(
    container: ContainerDep,
    client: ClientDep,
    status: Annotated[list[ActionStatus] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> ActionListResponse:
    """The action outbox (BUILD_SPEC section 60)."""
    actions = await container.core.list_actions(client, statuses=status, limit=limit)
    return ActionListResponse(actions=[_action_out(a) for a in actions], total=len(actions))


@router.get("/actions/{action_id}", response_model=ActionResponse, tags=["actions"])
async def get_action(
    action_id: str, container: ContainerDep, client: ClientDep
) -> ActionResponse:
    return _action_out(await container.core.get_action(client, action_id=action_id))


@router.post(
    "/actions/{action_id}/execute", response_model=ActionResponse, tags=["actions"]
)
async def execute_action(
    action_id: str, container: ContainerDep, client: ClientDep
) -> ActionResponse:
    """Commit a committed-and-approved action and perform its external effect
    (BUILD_SPEC section 60 steps 2-3; phase 7's booking, cancelling, and
    email-sending executors)."""
    return _action_out(await container.core.execute_action(client, action_id=action_id))


@router.post(
    "/actions/{action_id}/verify-externally",
    response_model=ActionResponse,
    tags=["actions"],
)
async def verify_action_externally(
    action_id: str, container: ContainerDep, client: ClientDep
) -> ActionResponse:
    """Independently confirm an executed action and, only then, mark it
    verified (BUILD_SPEC section 63's warning: a hold, or a provider's
    "accepted" response, is not proof)."""
    return _action_out(
        await container.core.verify_action_externally(client, action_id=action_id)
    )


# --- calendar (BUILD_SPEC sections 63, 96) ------------------------------------


@router.get("/calendar/events", response_model=CalendarEventListResponse, tags=["calendar"])
async def read_calendar(
    container: ContainerDep,
    client: ClientDep,
    start_at: Annotated[str, Query()],
    end_at: Annotated[str, Query()],
) -> CalendarEventListResponse:
    """Section 63 step 1."""
    events = await container.core.read_calendar(client, start_at=start_at, end_at=end_at)
    return CalendarEventListResponse(
        events=[_calendar_event_out(e) for e in events], total=len(events)
    )


@router.get("/calendar/free-busy", response_model=FreeBusyResponse, tags=["calendar"])
async def calendar_free_busy(
    container: ContainerDep,
    client: ClientDep,
    start_at: Annotated[str, Query()],
    end_at: Annotated[str, Query()],
) -> FreeBusyResponse:
    """Section 63 step 2."""
    result = await container.core.check_calendar_free_busy(
        client, start_at=start_at, end_at=end_at
    )
    return _free_busy_out(result)


@router.get("/appointments", response_model=AppointmentListResponse, tags=["calendar"])
async def list_appointments(
    container: ContainerDep,
    client: ClientDep,
    task_id: Annotated[str | None, Query()] = None,
) -> AppointmentListResponse:
    appointments = await container.core.list_appointments(client, task_id=task_id)
    return AppointmentListResponse(
        appointments=[_appointment_out(a) for a in appointments], total=len(appointments)
    )


@router.get(
    "/appointments/{appointment_id}", response_model=AppointmentResponse, tags=["calendar"]
)
async def get_appointment(
    appointment_id: str, container: ContainerDep, client: ClientDep
) -> AppointmentResponse:
    return _appointment_out(
        await container.core.get_appointment(client, appointment_id=appointment_id)
    )


@router.post(
    "/appointments/holds",
    response_model=AppointmentResponse,
    status_code=201,
    tags=["calendar"],
)
async def create_appointment_hold(
    payload: CreateAppointmentHoldRequest, container: ContainerDep, client: ClientDep
) -> AppointmentResponse:
    """Section 63 step 3: a reversible write."""
    draft = AppointmentHoldDraft(**payload.model_dump())
    appointment = await container.core.create_appointment_hold(client, draft)
    return _appointment_out(appointment)


@router.post(
    "/appointments/{appointment_id}/book", response_model=ActionResponse, tags=["calendar"]
)
async def book_appointment(
    appointment_id: str, container: ContainerDep, client: ClientDep
) -> ActionResponse:
    """Section 63 step 4, through the outbox — records intent, executes
    nothing yet. Approve via ``/approvals``, then ``/actions/{id}/execute``."""
    action = await container.core.book_appointment(client, appointment_id=appointment_id)
    return _action_out(action)


@router.post(
    "/appointments/{appointment_id}/cancel", response_model=ActionResponse, tags=["calendar"]
)
async def cancel_appointment(
    appointment_id: str, container: ContainerDep, client: ClientDep
) -> ActionResponse:
    """Section 63 step 6, through the outbox."""
    action = await container.core.cancel_appointment(client, appointment_id=appointment_id)
    return _action_out(action)


# --- email (BUILD_SPEC sections 61, 64, 96) -----------------------------------


@router.get("/email/search", response_model=EmailSearchResponse, tags=["email"])
async def search_email(
    container: ContainerDep,
    client: ClientDep,
    q: Annotated[str, Query(min_length=0, max_length=500)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> EmailSearchResponse:
    """Section 64's search/read."""
    messages = await container.core.search_email(client, query=q, limit=limit)
    return EmailSearchResponse(
        messages=[_email_message_out(m) for m in messages], total=len(messages)
    )


@router.get(
    "/email/threads/{thread_id}", response_model=EmailThreadResponse, tags=["email"]
)
async def read_email_thread(
    thread_id: str, container: ContainerDep, client: ClientDep
) -> EmailThreadResponse:
    """Section 64's thread read."""
    thread = await container.core.read_email_thread(client, thread_id=thread_id)
    return _email_thread_out(thread)


@router.post(
    "/email/send", response_model=ActionResponse, status_code=201, tags=["email"]
)
async def send_email(
    payload: SendEmailRequest, container: ContainerDep, client: ClientDep
) -> ActionResponse:
    """Section 64's send/reply, recorded through the outbox rather than sent
    directly (section 61: the idempotency key is LifeOps's, not the
    caller's)."""
    draft = EmailSendDraft(**payload.model_dump())
    action = await container.core.prepare_send_email(client, draft)
    return _action_out(action)


# --- documents (BUILD_SPEC sections 36, 64, 96) -------------------------------


@router.post(
    "/documents", response_model=DocumentResponse, status_code=201, tags=["documents"]
)
async def create_document(
    payload: CreateDocumentRequest, container: ContainerDep, client: ClientDep
) -> DocumentResponse:
    """A reference to something ingested from email or the calendar (section
    64); link it to a task or entity with the existing ``/world/relationships``
    route."""
    draft = DocumentDraft(**payload.model_dump())
    document = await container.core.create_document(client, draft)
    return _document_out(document)


# --- knowledge (BUILD_SPEC sections 18, 36, 50) --------------------------------


@router.post(
    "/knowledge", response_model=KnowledgeResponse, status_code=201, tags=["knowledge"]
)
async def create_knowledge(
    payload: CreateKnowledgeRequest, container: ContainerDep, client: ClientDep
) -> KnowledgeResponse:
    """Reference content the user authored or distilled from a Document
    (section 18) — an insurance policy note, a checklist, a procedure."""
    draft = KnowledgeDraft(**payload.model_dump())
    knowledge = await container.core.record_knowledge(client, draft)
    return _knowledge_out(knowledge)


@router.get("/knowledge", response_model=KnowledgeListResponse, tags=["knowledge"])
async def search_knowledge(
    container: ContainerDep,
    client: ClientDep,
    q: Annotated[str, Query(max_length=200)] = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> KnowledgeListResponse:
    """Search reference content by title, category, or body text."""
    found = await container.core.search_knowledge(client, query=q, limit=limit)
    return KnowledgeListResponse(
        knowledge=[_knowledge_out(k) for k in found], total=len(found)
    )


@router.get(
    "/knowledge/{knowledge_id}", response_model=KnowledgeResponse, tags=["knowledge"]
)
async def get_knowledge(
    knowledge_id: str, container: ContainerDep, client: ClientDep
) -> KnowledgeResponse:
    found = await container.core.get_knowledge(client, knowledge_id=knowledge_id)
    return _knowledge_out(found)


@router.get("/audit", response_model=AuditListResponse, tags=["audit"])
async def read_audit(
    container: ContainerDep,
    client: ClientDep,
    target: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> AuditListResponse:
    """The durable audit log — "why did Hermes do that?" (section 62)."""
    records = await container.core.read_audit(client, target=target, limit=limit)
    return AuditListResponse(
        records=[_audit_out(r) for r in records], total=len(records)
    )


# --- service requests (BUILD_SPEC sections 36, 67, 68, 97, 101) --------------
#
# Section 101's electrician scenario end to end: open a request, contact a
# provider by phone or with a quote request (through the same outbox and
# approval machinery every other action uses), prepare a booking, and fold
# the independently-verified booking back into the request once it happened.


@router.get(
    "/service-requests", response_model=ServiceRequestListResponse, tags=["service-requests"]
)
async def list_service_requests(
    container: ContainerDep,
    client: ClientDep,
    task_id: Annotated[str | None, Query()] = None,
) -> ServiceRequestListResponse:
    requests = await container.core.list_service_requests(client, task_id=task_id)
    return ServiceRequestListResponse(
        service_requests=[_service_request_out(r) for r in requests], total=len(requests)
    )


@router.get(
    "/service-requests/{service_request_id}",
    response_model=ServiceRequestResponse,
    tags=["service-requests"],
)
async def get_service_request(
    service_request_id: str, container: ContainerDep, client: ClientDep
) -> ServiceRequestResponse:
    return _service_request_out(
        await container.core.get_service_request(
            client, service_request_id=service_request_id
        )
    )


@router.post(
    "/service-requests",
    response_model=ServiceRequestResponse,
    status_code=201,
    tags=["service-requests"],
)
async def create_service_request(
    payload: CreateServiceRequestRequest, container: ContainerDep, client: ClientDep
) -> ServiceRequestResponse:
    """Section 101 step 1: identify the relevant asset and open the record."""
    draft = ServiceRequestDraft(**payload.model_dump())
    request = await container.core.create_service_request(client, draft)
    return _service_request_out(request)


@router.post(
    "/service-requests/{service_request_id}/call",
    response_model=ActionResponse,
    tags=["service-requests"],
)
async def request_provider_call(
    service_request_id: str,
    payload: RequestProviderContactRequest,
    container: ContainerDep,
    client: ClientDep,
) -> ActionResponse:
    """Section 101 steps 5-6: call the provider (BUILD_SPEC section 68)."""
    action = await container.core.request_provider_call(
        client, service_request_id=service_request_id, **payload.model_dump()
    )
    return _action_out(action)


@router.post(
    "/service-requests/{service_request_id}/quote",
    response_model=ActionResponse,
    tags=["service-requests"],
)
async def request_quote_by_phone(
    service_request_id: str,
    payload: RequestProviderContactRequest,
    container: ContainerDep,
    client: ClientDep,
) -> ActionResponse:
    """Section 101 step 7: collect the diagnostic fee."""
    action = await container.core.request_quote_by_phone(
        client, service_request_id=service_request_id, **payload.model_dump()
    )
    return _action_out(action)


@router.post(
    "/service-requests/{service_request_id}/book",
    response_model=ActionResponse,
    tags=["service-requests"],
)
async def request_service_booking(
    service_request_id: str,
    payload: RequestServiceBookingRequest,
    container: ContainerDep,
    client: ClientDep,
) -> ActionResponse:
    """Section 101 step 10: prepare booking, through the outbox — this does
    not book anything by itself. Approve via ``/approvals``, then
    ``/actions/{id}/execute``, then ``/service-requests/{id}/confirm-booking``."""
    action = await container.core.request_service_booking(
        client,
        service_request_id=service_request_id,
        appointment_id=payload.appointment_id,
    )
    return _action_out(action)


@router.post(
    "/service-requests/{service_request_id}/confirm-booking",
    response_model=ServiceRequestResponse,
    tags=["service-requests"],
)
async def confirm_service_booking(
    service_request_id: str,
    payload: ConfirmServiceBookingRequest,
    container: ContainerDep,
    client: ClientDep,
) -> ServiceRequestResponse:
    """Section 101 step 13: fold an independently-verified booking (via
    ``/actions/{id}/verify-externally``) into its service request."""
    request = await container.core.confirm_service_booking(
        client,
        service_request_id=service_request_id,
        appointment_id=payload.appointment_id,
    )
    return _service_request_out(request)


@router.post(
    "/service-requests/{service_request_id}/complete",
    response_model=ServiceRequestResponse,
    tags=["service-requests"],
)
async def complete_service_request(
    service_request_id: str, container: ContainerDep, client: ClientDep
) -> ServiceRequestResponse:
    """Section 101 step 16: complete only after the booking is verified — the
    status machine (domain/service_request.py) refuses this from anywhere but
    BOOKED."""
    request = await container.core.complete_service_request(
        client, service_request_id=service_request_id
    )
    return _service_request_out(request)


# --- shopping (BUILD_SPEC sections 36, 56, 98) --------------------------------
#
# Search is read-only. Creating a list and adding items are local and
# reversible (R1) — no Action. Building a cart and submitting an order go
# through the outbox (build_grocery_cart / submit_grocery_order below), the
# same shape book_appointment and prepare_send_email use; the generic
# ``/actions/{id}/execute`` and ``/actions/{id}/verify-externally`` routes
# above already commit, execute, and verify either action type.


@router.get("/shopping/search", response_model=ShoppingSearchResponse, tags=["shopping"])
async def search_shopping(
    container: ContainerDep,
    client: ClientDep,
    query: Annotated[str, Query(min_length=1)],
    store: Annotated[str, Query()] = "",
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> ShoppingSearchResponse:
    """Section 98's "search/research". Read-only."""
    results = await container.core.search_shopping(client, query=query, store=store, limit=limit)
    return ShoppingSearchResponse(
        results=[ProductResultResponse(**r.model_dump()) for r in results], total=len(results)
    )


@router.get(
    "/shopping/lists", response_model=ShoppingListListResponse, tags=["shopping"]
)
async def list_shopping_lists(
    container: ContainerDep,
    client: ClientDep,
    status: Annotated[ShoppingListStatus | None, Query()] = None,
    task_id: Annotated[str | None, Query()] = None,
) -> ShoppingListListResponse:
    lists = await container.core.list_shopping_lists(client, status=status, task_id=task_id)
    return ShoppingListListResponse(
        shopping_lists=[_shopping_list_out(item) for item in lists], total=len(lists)
    )


@router.get(
    "/shopping/lists/{list_id}", response_model=ShoppingListResponse, tags=["shopping"]
)
async def get_shopping_list(
    list_id: str, container: ContainerDep, client: ClientDep
) -> ShoppingListResponse:
    return _shopping_list_out(await container.core.get_shopping_list(client, list_id=list_id))


@router.post(
    "/shopping/lists", response_model=ShoppingListResponse, status_code=201, tags=["shopping"]
)
async def create_shopping_list(
    payload: CreateShoppingListRequest, container: ContainerDep, client: ClientDep
) -> ShoppingListResponse:
    """Open a new list. Local and reversible (R1): no approval."""
    shopping_list = await container.core.create_shopping_list(
        client,
        ShoppingListDraft(
            title=payload.title,
            store=payload.store,
            task_id=payload.task_id,
            items=[ShoppingItem(**item.model_dump()) for item in payload.items],
        ),
    )
    return _shopping_list_out(shopping_list)


@router.post(
    "/shopping/lists/{list_id}/items",
    response_model=ShoppingListResponse,
    tags=["shopping"],
)
async def add_shopping_items(
    list_id: str,
    payload: AddShoppingItemsRequest,
    container: ContainerDep,
    client: ClientDep,
) -> ShoppingListResponse:
    shopping_list = await container.core.add_shopping_items(
        client,
        list_id=list_id,
        items=[ShoppingItem(**item.model_dump()) for item in payload.items],
    )
    return _shopping_list_out(shopping_list)


@router.post(
    "/shopping/lists/{list_id}/substitutions",
    response_model=ShoppingListResponse,
    tags=["shopping"],
)
async def apply_substitution(
    list_id: str,
    payload: SubstitutionRequest,
    container: ContainerDep,
    client: ClientDep,
) -> ShoppingListResponse:
    """Section 98's substitutions — a safety surface. If this list has a live
    checkout Action, applying one refreshes that Action's payload, which
    invalidates any approval already granted for the old payload (section
    57)."""
    shopping_list = await container.core.apply_substitution(
        client, list_id=list_id, draft=SubstitutionDraft(**payload.model_dump())
    )
    return _shopping_list_out(shopping_list)


@router.post(
    "/shopping/lists/{list_id}/build-cart", response_model=ActionResponse, tags=["shopping"]
)
async def build_grocery_cart(
    list_id: str, container: ContainerDep, client: ClientDep
) -> ActionResponse:
    """Section 98's cart building — R1, automatic (BUILD_SPEC section 56):
    prepares and executes the Action in one call, no approval required."""
    action = await container.core.build_grocery_cart(client, list_id=list_id)
    return _action_out(action)


@router.post(
    "/shopping/lists/{list_id}/checkout", response_model=ActionResponse, tags=["shopping"]
)
async def submit_grocery_order(
    list_id: str, container: ContainerDep, client: ClientDep
) -> ActionResponse:
    """Section 98's approval-gated checkout — R3, always approved (BUILD_SPEC
    section 56). Only prepares the Action; approve via
    ``/approvals/{id}/decide``, then run it via ``/actions/{id}/execute``."""
    action = await container.core.submit_grocery_order(client, list_id=list_id)
    return _action_out(action)


# --- bills and payees (BUILD_SPEC sections 72, 99) ---------------------------
#
# Section 99: "Bills first. Payments last." These routes record what is owed.
# Paying goes through the action outbox, so it inherits approval, idempotency,
# verification, audit, and the emergency stop rather than re-deriving any.


def _payee_out(payee: Payee) -> PayeeResponse:
    return PayeeResponse(**payee.model_dump(), is_approved=payee.is_approved)


def _bill_out(bill: Bill) -> BillResponse:
    return BillResponse(**bill.model_dump(), is_payable=bill.is_payable)


@router.get("/payees", response_model=PayeeListResponse, tags=["bills"])
async def list_payees(container: ContainerDep, client: ClientDep) -> PayeeListResponse:
    payees = [_payee_out(p) for p in await container.core.list_payees(client)]
    return PayeeListResponse(payees=payees, total=len(payees))


@router.post("/payees", status_code=201, tags=["bills"])
async def record_payee(
    payload: CreatePayeeRequest, container: ContainerDep, client: ClientDep
) -> dict[str, Any]:
    """Propose a payee. Section 72: a new payee always requires approval, so
    this returns the action awaiting a decision, not a usable payee."""
    action = await container.core.record_payee(client, PayeeDraft(**payload.model_dump()))
    return {"action_id": action.id, "status": str(action.status)}


@router.post("/payees/{payee_id}/approve", response_model=PayeeResponse, tags=["bills"])
async def approve_payee(
    payee_id: str, container: ContainerDep, client: ClientDep
) -> PayeeResponse:
    return _payee_out(await container.core.approve_payee(client, payee_id=payee_id))


@router.get("/bills", response_model=BillListResponse, tags=["bills"])
async def list_bills(
    container: ContainerDep,
    client: ClientDep,
    statuses: Annotated[list[BillStatus] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> BillListResponse:
    bills = [
        _bill_out(b)
        for b in await container.core.list_bills(client, statuses=statuses, limit=limit)
    ]
    return BillListResponse(bills=bills, total=len(bills))


@router.get("/bills/{bill_id}", response_model=BillResponse, tags=["bills"])
async def get_bill(
    bill_id: str, container: ContainerDep, client: ClientDep
) -> BillResponse:
    return _bill_out(await container.core.get_bill(client, bill_id=bill_id))


@router.post("/bills", response_model=BillResponse, status_code=201, tags=["bills"])
async def record_bill(
    payload: CreateBillRequest, container: ContainerDep, client: ClientDep
) -> BillResponse:
    """Record something owed. This tracks a debt; it pays nothing."""
    bill = await container.core.record_bill(client, BillDraft(**payload.model_dump()))
    return _bill_out(bill)


@router.post("/bills/{bill_id}/payment", status_code=201, tags=["bills"])
async def prepare_bill_payment(
    bill_id: str, container: ContainerDep, client: ClientDep
) -> dict[str, Any]:
    """Prepare a payment. Always returns an action needing approval — R4 is
    never policy-relaxable (section 56)."""
    action = await container.core.prepare_bill_payment(client, bill_id=bill_id)
    return {"action_id": action.id, "status": str(action.status)}


@router.post("/bills/{bill_id}/settle", response_model=BillResponse, tags=["bills"])
async def settle_bill(
    bill_id: str,
    payload: SettleBillRequest,
    container: ContainerDep,
    client: ClientDep,
) -> BillResponse:
    bill = await container.core.settle_bill(
        client, bill_id=bill_id, external_reference=payload.external_reference
    )
    return _bill_out(bill)


# --- workflow templates (BUILD_SPEC sections 73, 100) -------------------------


def _template_out(template: WorkflowTemplate) -> WorkflowTemplateResponse:
    return WorkflowTemplateResponse(**template.model_dump())


@router.get(
    "/workflow-templates", response_model=WorkflowTemplateListResponse, tags=["routines"]
)
async def list_workflow_templates(
    container: ContainerDep,
    client: ClientDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> WorkflowTemplateListResponse:
    templates = [
        _template_out(t)
        for t in await container.core.list_workflow_templates(client, limit=limit)
    ]
    return WorkflowTemplateListResponse(templates=templates, total=len(templates))


@router.get(
    "/workflow-templates/due", response_model=WorkflowTemplateListResponse, tags=["routines"]
)
async def list_due_routines(
    container: ContainerDep,
    client: ClientDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> WorkflowTemplateListResponse:
    """Scheduled routines whose time has come (section 55's due-work lease,
    reused rather than a second scheduler)."""
    templates = [
        _template_out(t) for t in await container.core.due_routines(client, limit=limit)
    ]
    return WorkflowTemplateListResponse(templates=templates, total=len(templates))


@router.post(
    "/workflow-templates",
    response_model=WorkflowTemplateResponse,
    status_code=201,
    tags=["routines"],
)
async def save_workflow_template(
    payload: SaveWorkflowTemplateRequest, container: ContainerDep, client: ClientDep
) -> WorkflowTemplateResponse:
    """Create or revise a template — a permitted self-change (section 73). The
    name determines identity, so saving an existing name revises it."""
    template = await container.core.save_workflow_template(
        client, WorkflowTemplateDraft(**payload.model_dump())
    )
    return _template_out(template)


@router.delete("/workflow-templates/{template_id}", status_code=204, tags=["routines"])
async def delete_workflow_template(
    template_id: str, container: ContainerDep, client: ClientDep
) -> None:
    await container.core.delete_workflow_template(client, template_id=template_id)


# --- search (BUILD_SPEC section 19) ------------------------------------------


@router.get("/search", tags=["search"])
async def universal_search(
    container: ContainerDep,
    client: ClientDep,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> dict[str, Any]:
    """Case-insensitive substring search across ten of section 19's twelve
    categories (domain/search.py explains the two still missing)."""
    results = await container.core.search(client, query=q, limit=limit)
    return {
        "people": [_person_out(p).model_dump() for p in results.people],
        "preferences": [_preference_out(p).model_dump() for p in results.preferences],
        "tasks": [_task_out(t).model_dump() for t in results.tasks],
        "providers": [_entity_out(e).model_dump() for e in results.providers],
        "assets": [_entity_out(e).model_dump() for e in results.assets],
        "appointments": [_appointment_out(a).model_dump() for a in results.appointments],
        "memories": [_memory_out(m).model_dump() for m in results.memories],
        "documents": [_document_out(d).model_dump() for d in results.documents],
        "knowledge": [_knowledge_out(k).model_dump() for k in results.knowledge],
        "bills": [_bill_out(b).model_dump() for b in results.bills],
    }


# --- configuration ---


@router.get("/config/providers", tags=["config"])
async def list_providers(
    container: ContainerDep, _config_client: ConfiguringClientDep
) -> dict[str, Any]:
    """Provider schemas plus current status.

    The Console renders its configuration forms from ``definition``, so adding
    a provider needs no frontend change.
    """
    statuses = {s.id: s for s in container.config.list_status()}
    return {
        "providers": [
            {
                "definition": definition.model_dump(),
                "status": statuses[definition.id].model_dump(),
            }
            for definition in all_providers()
        ]
    }


@router.get("/config/providers/{provider_id}", tags=["config"])
async def get_provider_config(
    provider_id: str, container: ContainerDep, _config_client: ConfiguringClientDep
) -> dict[str, Any]:
    definition = get_provider(provider_id)
    if definition is None:
        raise NotFoundError(f"unknown provider {provider_id!r}", provider=provider_id)
    return {
        "definition": definition.model_dump(),
        "status": container.config.get_status(provider_id).model_dump(),
    }


@router.put("/config/providers/{provider_id}", tags=["config"])
async def update_provider_config(
    provider_id: str,
    payload: UpdateProviderRequest,
    container: ContainerDep,
    _config_client: ConfiguringClientDep,
) -> dict[str, Any]:
    """Apply a configuration change.

    Secret fields are routed to the SecretStore on the way in and are never
    echoed back — the response reports only ``configured`` and a fingerprint.
    """
    status = container.config.update_provider(provider_id, payload.model_dump())
    _publish_config_changed(container, provider=provider_id)
    return {"status": status.model_dump()}


@router.post(
    "/config/providers/{provider_id}/test",
    response_model=TestProviderResponse,
    tags=["config"],
)
async def test_provider(
    provider_id: str, container: ContainerDep, _config_client: ConfiguringClientDep
) -> TestProviderResponse:
    """Run the provider's health check.

    ElevenLabs (phase 5), the local voice adapters (phase 6), and calendar/
    email (phase 7) have real adapters and are actually called here. Every
    other provider still ships no adapter, so this reports honestly that one
    is not implemented yet rather than returning a fake success. A Test
    button that lies is worse than one that says "not yet".
    """
    definition = get_provider(provider_id)
    if definition is None:
        raise NotFoundError(f"unknown provider {provider_id!r}", provider=provider_id)

    if provider_id in ("elevenlabs", "local_tts", "local_asr"):
        return await _test_voice_provider(container, provider_id)
    if provider_id in ("calendar", "email"):
        return await _test_calendar_or_email(container, provider_id)
    if provider_id == "browser":
        return await _test_browser(container)

    status = container.config.get_status(provider_id)
    message = (
        f"{definition.display_name} has no adapter yet "
        f"(arrives in phase {definition.available_in_phase})."
    )
    report = container.config.record_health(
        provider_id, healthy=False, message=message, reason="adapter_not_implemented"
    )
    return TestProviderResponse(
        provider=provider_id,
        healthy=False,
        state=str(status.state),
        message=message,
        checked_at=report.checked_at,
    )


async def _test_voice_provider(container: Container, provider_id: str) -> TestProviderResponse:
    """Actually call the named voice provider (ElevenLabs, local TTS, or
    local ASR) when it is enabled; report "not configured" rather than a
    health check result when it is not — the user has not turned it on, so
    nothing was attempted (AGENTS.md never fakes success).

    Uses ``health_for``, not the mode-aware ``health()``: the Console is
    testing the card it clicked, not whatever the active voice mode would
    currently select — testing local_tts must test local_tts even while
    Quick Cloud mode has TTS pinned to elevenlabs.
    """
    try:
        _, report = await container.voice.health_for(provider_id)
    except ProviderNotConfiguredError as exc:
        report = container.config.record_health(
            provider_id, healthy=False, message=str(exc), reason="not_configured"
        )
    status = container.config.get_status(provider_id)
    return TestProviderResponse(
        provider=provider_id,
        healthy=report.healthy,
        state=str(status.state),
        message=report.message,
        checked_at=report.checked_at,
    )


async def _test_browser(container: Container) -> TestProviderResponse:
    """Actually call the browser provider (phase 9) when it is enabled; it
    honestly detects whether a browser automation runtime is installed and
    reports that it is not integrated even if one is (AGENTS.md never fakes
    success — same pattern as the local voice adapters)."""
    try:
        report = await container.browser.health()
    except ProviderNotConfiguredError as exc:
        report = container.config.record_health(
            "browser", healthy=False, message=str(exc), reason="not_configured"
        )
    status = container.config.get_status("browser")
    return TestProviderResponse(
        provider="browser",
        healthy=report.healthy,
        state=str(status.state),
        message=report.message,
        checked_at=report.checked_at,
    )


async def _test_calendar_or_email(container: Container, provider_id: str) -> TestProviderResponse:
    """Actually call the calendar or email provider (phase 7) when it is
    enabled; report "not configured" otherwise (AGENTS.md never fakes
    success)."""
    try:
        if provider_id == "calendar":
            report = await container.calendar.health()
        else:
            _, report = await container.email.health()
    except ProviderNotConfiguredError as exc:
        report = container.config.record_health(
            provider_id, healthy=False, message=str(exc), reason="not_configured"
        )
    status = container.config.get_status(provider_id)
    return TestProviderResponse(
        provider=provider_id,
        healthy=report.healthy,
        state=str(status.state),
        message=report.message,
        checked_at=report.checked_at,
    )


@router.post(
    "/config/providers/{provider_id}/discover",
    response_model=DiscoverResponse,
    tags=["config"],
)
async def discover_provider_options(
    provider_id: str,
    container: ContainerDep,
    field: Annotated[str, Query()],
    _config_client: ConfiguringClientDep,
) -> DiscoverResponse:
    """Fetch dynamic options for a select field (voices, models, calendars).

    ElevenLabs' ``voice_id`` and ``model_id`` fields call the live adapter as
    of phase 5, so the Console's "Refresh voices" button lists whatever the
    user's account actually has rather than nothing.
    """
    definition = get_provider(provider_id)
    if definition is None:
        raise NotFoundError(f"unknown provider {provider_id!r}", provider=provider_id)
    if definition.field(field) is None:
        raise NotFoundError(
            f"provider {provider_id!r} has no field {field!r}",
            provider=provider_id,
            field=field,
        )

    if provider_id == "elevenlabs" and field in ("voice_id", "model_id"):
        return await _discover_elevenlabs(container, field)

    if provider_id in ("local_tts", "local_asr") and field == "model":
        return await _discover_local_voice(provider_id, field)

    if provider_id == "calendar" and field == "default_calendar":
        return DiscoverResponse(
            provider=provider_id,
            field=field,
            options=[],
            message=(
                "This phase's CalDAV adapter reads one calendar collection at "
                "the configured server URL; it does not enumerate a user's "
                "other calendars yet."
            ),
        )

    return DiscoverResponse(
        provider=provider_id,
        field=field,
        options=[],
        message=(
            f"Discovery for {definition.display_name} arrives in phase "
            f"{definition.available_in_phase}."
        ),
    )


async def _discover_elevenlabs(container: Container, field: str) -> DiscoverResponse:
    try:
        if field == "voice_id":
            options = [
                {"value": voice.id, "label": voice.name}
                for voice in await container.voice.list_voices()
            ]
        else:
            options = [
                {"value": model.id, "label": model.name}
                for model in await container.voice.list_models()
            ]
    except ProviderNotConfiguredError as exc:
        return DiscoverResponse(provider="elevenlabs", field=field, options=[], message=str(exc))
    return DiscoverResponse(provider="elevenlabs", field=field, options=options)


async def _discover_local_voice(provider_id: str, field: str) -> DiscoverResponse:
    """No local model list exists to discover — no ML runtime ships with this
    codebase (BUILD_SPEC section 105). Reports that honestly, independent of
    whether the provider is enabled, so a user sees why before configuring
    anything (never fakes a model list, per AGENTS.md)."""
    provider = LocalASRProvider() if provider_id == "local_asr" else LocalTTSProvider()
    _, message = await provider.health()
    return DiscoverResponse(provider=provider_id, field=field, options=[], message=message)


_AUDIO_MEDIA_TYPES = {
    "mp3_44100_128": "audio/mpeg",
    "pcm_16000": "audio/pcm",
    "pcm_24000": "audio/pcm",
}


@router.post("/voice/tts/preview", tags=["voice"])
async def preview_voice(
    payload: SynthesizeSpeechRequest,
    container: ContainerDep,
    _config_client: ConfiguringClientDep,
) -> StreamingResponse:
    """Synthesize sample text and stream the audio back for the browser to
    play (BUILD_SPEC section 27's Preview voice button and the
    ``stream_text_to_speech`` capability). Does not require Hermes, and never
    saves anything — a voice can be auditioned before it is set as default.
    """
    options = SynthesisOptions(
        voice_id=payload.voice_id,
        model_id=payload.model_id,
        output_format=payload.output_format,
        stability=payload.stability,
        similarity_boost=payload.similarity_boost,
        speed=payload.speed,
    )
    # Built outside the response body: a missing provider or invalid text
    # raises here, before any bytes are sent, so it surfaces as a normal
    # error response instead of a truncated audio stream.
    chunks = container.voice.stream(payload.text, options)
    media_type = _AUDIO_MEDIA_TYPES.get(payload.output_format or "mp3_44100_128", "audio/mpeg")
    return StreamingResponse(chunks, media_type=media_type)


@router.get("/voice/mode-status", tags=["voice"])
async def voice_mode_status(
    container: ContainerDep, _config_client: ConfiguringClientDep
) -> dict[str, Any]:
    """What the current voice mode (BUILD_SPEC section 29) has selected for
    each capability, and what would be used next if that stopped working —
    the Console's "active provider" / "fallback provider" (section 95).

    A pure readback: nothing here performs a live health check, so opening
    Configuration never fans out network calls on its own.
    """
    return container.voice.mode_status().model_dump()


_LOCAL_VOICE_PROVIDER_IDS = ("local_tts", "local_asr")


@router.post("/voice/providers/{provider_id}/load", tags=["voice"])
async def load_voice_provider(
    provider_id: str, container: ContainerDep, _config_client: ConfiguringClientDep
) -> dict[str, Any]:
    """Load a local provider's model into memory (BUILD_SPEC section 95).

    Only the local adapters implement a load/unload lifecycle; nothing here
    can succeed until a real local runtime is installed, so this reports the
    same honest "not installed" message ``Test`` does rather than pretending
    a model loaded.
    """
    if provider_id not in _LOCAL_VOICE_PROVIDER_IDS:
        raise NotFoundError(
            f"provider {provider_id!r} has no load/unload lifecycle", provider=provider_id
        )
    try:
        loaded, message = await container.voice.load(provider_id)
    except ProviderNotConfiguredError as exc:
        return {"provider": provider_id, "loaded": False, "message": str(exc)}
    return {"provider": provider_id, "loaded": loaded, "message": message}


@router.post("/voice/providers/{provider_id}/unload", tags=["voice"])
async def unload_voice_provider(
    provider_id: str, container: ContainerDep, _config_client: ConfiguringClientDep
) -> dict[str, Any]:
    if provider_id not in _LOCAL_VOICE_PROVIDER_IDS:
        raise NotFoundError(
            f"provider {provider_id!r} has no load/unload lifecycle", provider=provider_id
        )
    try:
        loaded, message = await container.voice.unload(provider_id)
    except ProviderNotConfiguredError as exc:
        return {"provider": provider_id, "loaded": False, "message": str(exc)}
    return {"provider": provider_id, "loaded": loaded, "message": message}


@router.get("/config/system", tags=["config"])
async def get_system_config(
    container: ContainerDep, _config_client: ConfiguringClientDep
) -> dict[str, Any]:
    return container.config.get_system().model_dump()


@router.put("/config/system", tags=["config"])
async def update_system_config(
    payload: UpdateSystemRequest,
    container: ContainerDep,
    _config_client: ConfiguringClientDep,
) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    updated = container.config.update_system(changes)
    # No in-process propagation needed: core.safe_mode reads the config
    # live (Container wires a callable source), which is also what carries
    # the toggle to the separately running MCP server. Assigning a bool
    # here would pin this process and defeat that.
    _publish_config_changed(container, scope="system")
    return updated.model_dump()


@router.get("/config/clients", tags=["config"])
async def list_clients() -> dict[str, Any]:
    """Client permissions, for the Console's access inspector."""
    return {"clients": [CapabilityGrant.of(c).model_dump() for c in all_clients()]}


# --- application -------------------------------------------------------------


def create_app(container: Container | None = None, settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(
        level=resolved_settings.log_level, json_output=resolved_settings.log_json
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await app.state.container.startup()
        try:
            yield
        finally:
            await app.state.container.shutdown()

    app = FastAPI(
        title="LifeOps Core",
        version="0.1.0",
        description=(
            "The portable personal domain layer behind Hermes and LifeOps Console."
        ),
        lifespan=lifespan,
    )
    app.state.container = container or Container(resolved_settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def bind_trace(request: Request, call_next: Any) -> Any:
        with trace_context(
            trace_id=request.headers.get("x-trace-id"),
            client_id=request.headers.get("x-lifeops-client"),
        ) as trace_id:
            response = await call_next(request)
            response.headers["x-trace-id"] = trace_id
            return response

    @app.middleware("http")
    async def require_console_auth(request: Request, call_next: Any) -> Any:
        """Bearer-token gate for the Console API (SECURITY.md debt #1).

        Applies only when a console password is configured; a fresh
        loopback-bound deployment stays open so first-run setup works. The
        liveness probes and the login route itself stay reachable either way.
        """
        path = request.url.path
        open_routes = (f"{API_PREFIX}/health", f"{API_PREFIX}/auth/login")
        # CORS preflights carry no credentials; they must reach the CORS
        # middleware (which sits inside this one) unchallenged.
        if request.method == "OPTIONS":
            return await call_next(request)
        if path.startswith(API_PREFIX) and path not in open_routes:
            auth = getattr(request.app.state.container, "auth", None)
            if auth is not None and auth.enabled:
                header = request.headers.get("authorization", "")
                token = header[7:].strip() if header.lower().startswith("bearer ") else None
                if not auth.validate(token):
                    return JSONResponse(
                        status_code=401,
                        content=ErrorResponse(
                            code="authentication_required",
                            message="a valid console bearer token is required",
                        ).model_dump(),
                    )
        return await call_next(request)

    @app.exception_handler(LifeOpsError)
    async def lifeops_error_handler(_: Request, exc: LifeOpsError) -> JSONResponse:
        # Domain errors are expected outcomes, not server faults. They carry a
        # stable code so both the Console and an MCP client can branch on it.
        if exc.http_status >= 500:
            logger.error("%s", exc.message, extra={"code": exc.code, **exc.details})
        else:
            logger.info("%s", exc.message, extra={"code": exc.code, **exc.details})
        return JSONResponse(
            status_code=exc.http_status,
            content=ErrorResponse(**exc.to_dict()).model_dump(),
        )

    app.include_router(router)
    app.include_router(events_router, prefix=API_PREFIX)

    @app.get("/health", tags=["system"])
    async def root_health() -> dict[str, str]:
        """Unauthenticated liveness probe for process supervisors."""
        return {"status": "ok"}

    return app
