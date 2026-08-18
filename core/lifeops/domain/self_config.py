"""Hermes self-configuration and its boundary (BUILD_SPEC 73, 74, 100).

Section 100 is one sentence long in effect: *"Protected changes create Code
Change Requests."* Hermes may tune the parts of itself that describe how it
works — skills, routines, reminders, workflow templates. It may not touch the
parts that decide what it is *allowed* to do.

Section 73 draws that line explicitly, and this module encodes exactly its two
lists rather than a paraphrase. The distinction is not about difficulty: a
one-line edit to approval validation is more dangerous than a rewritten
workflow template, so the classification is by *what the change governs*, not
by how large it is.

When a change lands on the protected side, section 74 says what happens — a
Code Change Request is written to ``changes/requests/`` and nothing is
applied. Not partially applied, not applied with a warning. A coding agent
makes protected changes; Hermes does not.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from lifeops.errors import ValidationError
from lifeops.ids import new_ulid_id

PREFIX_CHANGE_REQUEST = "changereq"


class SelfConfigTarget(StrEnum):
    """What a self-change is aimed at.

    Section 73's permitted list, verbatim. Anything not here is protected by
    default — an unknown target is not a reason to allow a change, it is a
    reason to refuse one.

    Seven names, but not seven mechanisms — section 73 gives none of them a
    schema, and building one apiece would be exactly the "infrastructure for
    a hypothetical problem" section 105 warns against, on top of duplicating
    machinery that already exists elsewhere:

    * ``ROUTINE_TEMPLATE``, ``CRON_JOB``, and ``REMINDER`` are all a named,
      reusable shape of work with an optional schedule — precisely what
      ``domain.workflow_templates.WorkflowTemplate`` already is (a manual
      routine, a scheduled routine, a scheduled one-off reminder). Building
      three parallel entities that only differ by trigger cadence would also
      be the second scheduler/workflow engine section 55 explicitly warns
      against. ``LifeOpsCore.save_workflow_template`` is the one apply path
      for all three, whatever the caller calls the thing it is saving.
    * ``WORKFLOW_TEMPLATE`` is that same mechanism under its literal name.
    * ``PREFERENCE`` already has a full, independent apply path —
      ``LifeOpsCore.save_preference`` — predating section 73 entirely
      (Phase 2). Nothing new is needed for it here.
    * ``SKILL`` and ``NON_CRITICAL_PROMPT`` name content that lives in
      Hermes's own runtime (a skill file Hermes's own skill-loading
      mechanism reads; a prompt string Hermes's own runtime assembles) —
      storing either in NornicDB would duplicate Hermes's storage and drift
      from whatever Hermes actually loads, and CLAUDE.md's rule against
      building a second agent runtime cuts against LifeOps owning it.
      ``propose_self_change`` is the complete apply path for these two:
      once it does not raise, Hermes applies the change through its own
      mechanism; LifeOps's job is only to gate the decision, not to store
      the artifact.
    """

    SKILL = "skill"
    PREFERENCE = "preference"
    ROUTINE_TEMPLATE = "routine_template"
    CRON_JOB = "cron_job"
    REMINDER = "reminder"
    NON_CRITICAL_PROMPT = "non_critical_prompt"
    WORKFLOW_TEMPLATE = "workflow_template"


#: Section 73's "Hermes may not modify" list, verbatim.
#:
#: Kept as strings rather than an enum because these name *code and policy*,
#: not domain objects — there is no ``AuthorizationCode`` model, and inventing
#: one to hold a refusal reason would be modelling the wrong thing.
PROTECTED_COMPONENTS: tuple[str, ...] = (
    "authorization code",
    "approval validation",
    "payment code",
    "secret-store implementation",
    "database migrations",
    "MCP authentication",
    "container/runtime security",
    "browser security",
    "CI protection",
    "backup security",
)

#: Things a self-change may never do regardless of its declared target, because
#: each is a way to turn a permitted change into a protected one. A routine
#: that grants itself a capability is not a routine change.
FORBIDDEN_EFFECTS: tuple[str, ...] = (
    "grant_capability",
    "revoke_capability",
    "modify_client_identity",
    "read_secret",
    "write_secret",
    "disable_safe_mode",
    "disable_emergency_stop",
    "modify_approval_rules",
)


class ChangeRequest(BaseModel):
    """A Code Change Request (section 74's schema, field for field)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    component: str
    problem: str
    observed_behavior: str
    desired_behavior: str

    task_ids: list[str] = Field(default_factory=list)
    trace_ids: list[str] = Field(default_factory=list)
    failure_count: int = 0

    risk: str
    suggested_acceptance_tests: list[str] = Field(default_factory=list)

    created_at: str
    requested_by: str

    @staticmethod
    def make_id() -> str:
        return new_ulid_id(PREFIX_CHANGE_REQUEST)


class SelfConfigProposal(BaseModel):
    """A change Hermes wants to make to itself."""

    model_config = ConfigDict(extra="forbid")

    target: SelfConfigTarget
    name: str = Field(min_length=1, max_length=200)
    #: What the change actually does, as a free-form document. Validated for
    #: effects rather than schema: the point is what it *causes*.
    definition: dict[str, str] = Field(default_factory=dict)
    effects: list[str] = Field(default_factory=list)
    rationale: str | None = None


# --- pure rules ---------------------------------------------------------------


def classify(component: str) -> bool:
    """Whether a named component is protected (section 73).

    Substring matching, deliberately generous. A caller naming
    "the approval validation module" must be caught as surely as one naming
    "approval validation" — under-matching here means a protected change is
    applied, and over-matching only means a change request is written for
    something that could have been applied directly.
    """
    needle = component.strip().lower()
    if not needle:
        raise ValidationError("a component must be named", field="component")
    # Both sides are lowered. The list is written in the spec's own casing
    # ("MCP authentication", "CI protection"), and comparing it raw against a
    # lowered needle silently failed to protect exactly those two.
    return any(
        protected in needle or needle in protected
        for protected in (entry.lower() for entry in PROTECTED_COMPONENTS)
    )


def forbidden_effects(proposal: SelfConfigProposal) -> list[str]:
    """Effects a self-change may never have, whatever it calls itself."""
    declared = {effect.strip().lower() for effect in proposal.effects}
    return sorted(declared & set(FORBIDDEN_EFFECTS))


def check_permitted(proposal: SelfConfigProposal) -> None:
    """Raise unless this proposal is one Hermes may apply itself.

    Two ways to fail, and the messages differ on purpose: "that component is
    protected" tells the caller to file a change request, while "that effect
    is forbidden" tells it the change is wrong regardless of route.
    """
    offending = forbidden_effects(proposal)
    if offending:
        raise ValidationError(
            f"a self-change may never {', '.join(offending)}; this is not a "
            "matter of which route it takes",
            field="effects",
            effects=offending,
        )
    if classify(proposal.name):
        raise ValidationError(
            f"{proposal.name!r} names a protected component (section 73); "
            "file a code change request instead of applying it",
            field="name",
            component=proposal.name,
        )
