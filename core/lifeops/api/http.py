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
from fastapi.responses import JSONResponse

from lifeops.api.schemas import (
    CreatePersonRequest,
    CreateTaskRequest,
    DiscoverResponse,
    ErrorResponse,
    PersonResponse,
    PreferenceListResponse,
    PreferenceResponse,
    SavePreferenceRequest,
    TaskListResponse,
    TaskResponse,
    TestProviderResponse,
    UpdateProviderRequest,
    UpdateSystemRequest,
    UpdateTaskRequest,
)
from lifeops.config.provider_registry import all_providers, get_provider
from lifeops.container import Container
from lifeops.domain.people import Person, PersonDraft
from lifeops.domain.preferences import Preference, PreferenceDraft
from lifeops.domain.tasks import Task, TaskDraft, TaskState, TaskUpdate
from lifeops.errors import LifeOpsError, NotFoundError
from lifeops.observability.logging import configure_logging, trace_context
from lifeops.policy import CapabilityGrant, ClientIdentity, all_clients, resolve_client
from lifeops.policy.capabilities import CONSOLE
from lifeops.settings import Settings, get_settings

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


# --- serialisers -------------------------------------------------------------


def _person_out(person: Person) -> PersonResponse:
    return PersonResponse(**person.model_dump())


def _preference_out(pref: Preference) -> PreferenceResponse:
    return PreferenceResponse(**pref.model_dump(), is_current=pref.is_current)


def _task_out(task: Task) -> TaskResponse:
    return TaskResponse(**task.model_dump(), needs_attention=task.needs_attention)


# --- routes ------------------------------------------------------------------

router = APIRouter(prefix=API_PREFIX)


@router.get("/health", tags=["system"])
async def health(container: ContainerDep) -> dict[str, Any]:
    return {"status": "ok", "components": await container.health()}


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


# --- configuration ---


@router.get("/config/providers", tags=["config"])
async def list_providers(container: ContainerDep) -> dict[str, Any]:
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
async def get_provider_config(provider_id: str, container: ContainerDep) -> dict[str, Any]:
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
) -> dict[str, Any]:
    """Apply a configuration change.

    Secret fields are routed to the SecretStore on the way in and are never
    echoed back — the response reports only ``configured`` and a fingerprint.
    """
    status = container.config.update_provider(provider_id, payload.model_dump())
    return {"status": status.model_dump()}


@router.post(
    "/config/providers/{provider_id}/test",
    response_model=TestProviderResponse,
    tags=["config"],
)
async def test_provider(provider_id: str, container: ContainerDep) -> TestProviderResponse:
    """Run the provider's health check.

    Phase 0 ships no provider adapters, so this reports honestly that the
    adapter is not implemented yet rather than returning a fake success. A
    Test button that lies is worse than one that says "not yet".
    """
    definition = get_provider(provider_id)
    if definition is None:
        raise NotFoundError(f"unknown provider {provider_id!r}", provider=provider_id)

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


@router.post(
    "/config/providers/{provider_id}/discover",
    response_model=DiscoverResponse,
    tags=["config"],
)
async def discover_provider_options(
    provider_id: str,
    container: ContainerDep,
    field: Annotated[str, Query()],
) -> DiscoverResponse:
    """Fetch dynamic options for a select field (voices, models, calendars)."""
    definition = get_provider(provider_id)
    if definition is None:
        raise NotFoundError(f"unknown provider {provider_id!r}", provider=provider_id)
    if definition.field(field) is None:
        raise NotFoundError(
            f"provider {provider_id!r} has no field {field!r}",
            provider=provider_id,
            field=field,
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


@router.get("/config/system", tags=["config"])
async def get_system_config(container: ContainerDep) -> dict[str, Any]:
    return container.config.get_system().model_dump()


@router.put("/config/system", tags=["config"])
async def update_system_config(
    payload: UpdateSystemRequest, container: ContainerDep
) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    updated = container.config.update_system(changes)
    # Safe mode has to take effect immediately, not on next restart.
    if "safe_mode" in changes:
        container.core.safe_mode = updated.safe_mode
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

    @app.get("/health", tags=["system"])
    async def root_health() -> dict[str, str]:
        """Unauthenticated liveness probe for process supervisors."""
        return {"status": "ok"}

    return app
