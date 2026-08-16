"""Task domain model and state machine (BUILD_SPEC sections 14 and 53).

Two rules live here and are enforced by LifeOps rather than trusted to a model:

1. Only legal state transitions are accepted. An LLM that proposes
   CAPTURED -> COMPLETED gets an error, not a silently rewritten task.

2. A task whose work happens in the outside world reaches COMPLETED only
   through VERIFYING, and only with evidence attached. "The model said it
   booked the appointment" is not evidence.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from lifeops.errors import InvalidTransitionError, VerificationRequiredError
from lifeops.ids import new_task_id


class TaskState(StrEnum):
    CAPTURED = "CAPTURED"
    PLANNED = "PLANNED"
    READY = "READY"
    EXECUTING = "EXECUTING"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class VerificationState(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"


#: States from which no further transition is allowed.
TERMINAL_STATES: frozenset[TaskState] = frozenset(
    {TaskState.COMPLETED, TaskState.CANCELLED}
)

#: States meaning "LifeOps or Hermes is actively carrying this".
ACTIVE_STATES: frozenset[TaskState] = frozenset(
    {
        TaskState.EXECUTING,
        TaskState.WAITING_EXTERNAL,
        TaskState.NEEDS_APPROVAL,
        TaskState.VERIFYING,
    }
)

#: States that require a human before work can continue (BUILD_SPEC 12).
ATTENTION_STATES: frozenset[TaskState] = frozenset(
    {TaskState.NEEDS_APPROVAL, TaskState.BLOCKED, TaskState.FAILED}
)

# The transition table is exhaustive and explicit. A lookup miss is a denial,
# never a default-allow.
_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.CAPTURED: frozenset(
        {TaskState.PLANNED, TaskState.READY, TaskState.BLOCKED, TaskState.CANCELLED}
    ),
    TaskState.PLANNED: frozenset(
        {
            TaskState.READY,
            TaskState.CAPTURED,
            TaskState.BLOCKED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.READY: frozenset(
        {
            TaskState.EXECUTING,
            TaskState.PLANNED,
            TaskState.BLOCKED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.EXECUTING: frozenset(
        {
            TaskState.WAITING_EXTERNAL,
            TaskState.NEEDS_APPROVAL,
            TaskState.VERIFYING,
            TaskState.COMPLETED,
            TaskState.BLOCKED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.WAITING_EXTERNAL: frozenset(
        {
            TaskState.EXECUTING,
            TaskState.NEEDS_APPROVAL,
            TaskState.VERIFYING,
            TaskState.BLOCKED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.NEEDS_APPROVAL: frozenset(
        {
            TaskState.EXECUTING,
            TaskState.BLOCKED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.VERIFYING: frozenset(
        {
            TaskState.COMPLETED,
            TaskState.WAITING_EXTERNAL,
            TaskState.BLOCKED,
            TaskState.FAILED,
        }
    ),
    TaskState.BLOCKED: frozenset(
        {
            TaskState.READY,
            TaskState.PLANNED,
            TaskState.EXECUTING,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }
    ),
    # A failure is recoverable: the user or Hermes may retry it. It is not a
    # terminal state, but it cannot jump straight back to COMPLETED.
    TaskState.FAILED: frozenset(
        {TaskState.READY, TaskState.PLANNED, TaskState.CANCELLED}
    ),
    TaskState.COMPLETED: frozenset(),
    TaskState.CANCELLED: frozenset(),
}


def allowed_transitions(state: TaskState) -> frozenset[TaskState]:
    return _TRANSITIONS[state]


def transition_table() -> dict[str, list[str]]:
    """The full transition map, serialised for the Console.

    This is the authoritative copy of the table the Tasks screen renders; the
    Console must not keep its own (kimi.md Phase 1 debts — the duplicated table
    in ``console/src/services/lifeops.ts`` was free to drift).
    """
    return {
        str(state): sorted(str(target) for target in targets)
        for state, targets in _TRANSITIONS.items()
    }


def can_transition(current: TaskState, target: TaskState) -> bool:
    return target in _TRANSITIONS[current]


class Task(BaseModel):
    """A durable unit of work.

    Tasks outlive the conversation that created them. That is the whole point
    of storing them in LifeOps rather than in an agent's context window.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str | None = None
    state: TaskState = TaskState.CAPTURED
    priority: TaskPriority = TaskPriority.MEDIUM

    created_at: str
    updated_at: str
    due_at: str | None = None

    owner_entity_id: str | None = None
    # Which MCP client identity is currently carrying the task. Answers
    # "which client changed this?" in the audit trail (BUILD_SPEC 62).
    assigned_client: str | None = None
    current_action: str | None = None
    waiting_item_id: str | None = None

    # True when completion depends on the outside world agreeing that it
    # happened. Set at creation; only a privileged transition may clear it.
    verification_required: bool = False
    verification_state: VerificationState = VerificationState.NOT_REQUIRED
    verification_evidence: str | None = None

    related_entity_ids: list[str] = Field(default_factory=list)
    source: str | None = None
    created_by_client: str | None = None

    @property
    def needs_attention(self) -> bool:
        return self.state in ATTENTION_STATES

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @staticmethod
    def make_id() -> str:
        return new_task_id()


class TaskDraft(BaseModel):
    """Input shape for creating a task."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=20000)
    priority: TaskPriority = TaskPriority.MEDIUM
    due_at: str | None = None
    owner_entity_id: str | None = None
    related_entity_ids: list[str] = Field(default_factory=list)
    verification_required: bool = False
    source: str | None = None
    # Tasks are captured first and planned second. Allowing an arbitrary
    # initial state here would let a caller skip the state machine entirely.
    state: TaskState = TaskState.CAPTURED


class TaskUpdate(BaseModel):
    """Input shape for updating a task. Absent fields are left untouched."""

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


def validate_transition(
    task: Task,
    target: TaskState,
    *,
    verification_evidence: str | None = None,
) -> None:
    """Raise unless ``task`` may legally move to ``target``.

    Pure and side-effect free so that both the HTTP API and the MCP tools can
    call it before writing, and tests can exercise it without a database.
    """
    current = task.state

    if current == target:
        return

    if current in TERMINAL_STATES:
        raise InvalidTransitionError(
            f"task {task.id} is {current} and cannot change state",
            task_id=task.id,
            current_state=str(current),
            target_state=str(target),
        )

    if not can_transition(current, target):
        raise InvalidTransitionError(
            f"cannot move task from {current} to {target}",
            task_id=task.id,
            current_state=str(current),
            target_state=str(target),
            allowed=sorted(str(s) for s in allowed_transitions(current)),
        )

    if target is TaskState.COMPLETED and task.verification_required:
        # BUILD_SPEC 53: external work completes on evidence, not assertion.
        evidence = verification_evidence or task.verification_evidence
        if current is not TaskState.VERIFYING:
            raise VerificationRequiredError(
                f"task {task.id} requires verification and must pass through "
                f"{TaskState.VERIFYING} before completing",
                task_id=task.id,
                current_state=str(current),
            )
        if not evidence:
            raise VerificationRequiredError(
                f"task {task.id} cannot complete without verification evidence",
                task_id=task.id,
            )


def apply_transition(
    task: Task,
    target: TaskState,
    *,
    now: str,
    verification_evidence: str | None = None,
    actor_client: str | None = None,
) -> Task:
    """Return a new Task in ``target`` state, or raise if the move is illegal."""
    validate_transition(task, target, verification_evidence=verification_evidence)

    updated = task.model_copy(deep=True)
    updated.state = target
    updated.updated_at = now
    if actor_client:
        updated.assigned_client = actor_client
    if verification_evidence:
        updated.verification_evidence = verification_evidence

    if task.verification_required:
        if target is TaskState.VERIFYING:
            updated.verification_state = VerificationState.PENDING
        elif target is TaskState.COMPLETED:
            updated.verification_state = VerificationState.VERIFIED
        elif target is TaskState.FAILED:
            updated.verification_state = VerificationState.FAILED

    if target in TERMINAL_STATES:
        updated.current_action = None

    return updated
