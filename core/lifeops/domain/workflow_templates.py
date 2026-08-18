"""Workflow templates and routines (BUILD_SPEC sections 73, 100).

A template is a named, reusable shape of work — "book an electrician", "weekly
review" — that Hermes may create and revise itself, because section 73 puts
routine templates and workflow templates on the permitted side of the line.

Steps are a real list, not a JSON string packed into a facts bag. Phases 7 and
9 projected their entities as world nodes and encoded list fields into single
strings, which works but makes the contents unqueryable; a template's steps
are exactly the thing a later phase will want to search across, so this gets
its own repository. See CLAUDE.md's note on that debt.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from lifeops.errors import ValidationError
from lifeops.ids import new_ulid_id, slug_id

PREFIX_TEMPLATE = "template"

#: A template with more steps than this is a program, and a program belongs in
#: code where it can be reviewed — not in a record an agent revises itself.
MAX_STEPS = 40


class TriggerKind(StrEnum):
    """How a routine starts.

    ``SCHEDULE`` reuses the Phase 4 due-work lease rather than adding a
    scheduler; section 55 says store continuation state in NornicDB and warns
    explicitly against introducing a workflow engine.
    """

    MANUAL = "manual"
    SCHEDULE = "schedule"
    EVENT = "event"


class WorkflowStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=0)
    description: str = Field(min_length=1, max_length=500)
    #: The action this step prepares, when it prepares one. Named rather than
    #: embedded so a template can never smuggle in an action type that does
    #: not exist or that the caller may not perform.
    action_type: str | None = None


class WorkflowTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str | None = None
    steps: list[WorkflowStep] = Field(default_factory=list)

    trigger: TriggerKind = TriggerKind.MANUAL
    #: For SCHEDULE triggers: when this should next run. The due-work worker
    #: reads it the same way it reads a waiting item's next_action_at.
    next_run_at: str | None = None
    enabled: bool = True

    created_at: str
    updated_at: str
    created_by_client: str | None = None

    @staticmethod
    def make_id(name: str) -> str:
        return slug_id(PREFIX_TEMPLATE, name)

    @staticmethod
    def new_id() -> str:
        return new_ulid_id(PREFIX_TEMPLATE)


class WorkflowTemplateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    steps: list[WorkflowStep] = Field(default_factory=list)
    trigger: TriggerKind = TriggerKind.MANUAL
    next_run_at: str | None = None
    #: Present so a routine can be paused. Without it every save rebuilt the
    #: template with the model default, so editing a disabled routine silently
    #: switched it back on — a paused routine that resumes itself is worse
    #: than one that cannot be paused at all.
    enabled: bool = True


def validate_steps(steps: list[WorkflowStep]) -> list[WorkflowStep]:
    """Normalise step ordering, refusing a template that is really a program."""
    if len(steps) > MAX_STEPS:
        raise ValidationError(
            f"a template may have at most {MAX_STEPS} steps; beyond that it is "
            "a program and belongs in reviewed code",
            field="steps",
        )
    ordered = sorted(steps, key=lambda step: step.order)
    return [step.model_copy(update={"order": index}) for index, step in enumerate(ordered)]


def validate_trigger(trigger: TriggerKind, next_run_at: str | None) -> None:
    """A scheduled routine without a time never runs, and says nothing about it."""
    if trigger is TriggerKind.SCHEDULE and not next_run_at:
        raise ValidationError(
            "a scheduled routine needs a next_run_at, or it will never run",
            field="next_run_at",
        )
