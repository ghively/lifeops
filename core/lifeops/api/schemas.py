"""HTTP request and response shapes for LifeOps Console."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from lifeops.domain.preferences import PreferenceSource
from lifeops.domain.tasks import TaskPriority, TaskState


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
