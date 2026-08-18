"""Hermes self-configuration and its boundary (BUILD_SPEC 73, 74, 100).

Section 100 in effect reduces to one sentence — *"Protected changes create
Code Change Requests."* These tests pin the line section 73 draws, and the
three ways a permitted-looking change could cross it anyway: by naming a
protected component, by declaring a forbidden effect, or by reaching the
things that make every other guarantee in this system hold.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lifeops.clock import FrozenClock
from lifeops.core import LifeOpsCore
from lifeops.domain.people import Person
from lifeops.domain.self_config import (
    PROTECTED_COMPONENTS,
    SelfConfigProposal,
    SelfConfigTarget,
    check_permitted,
    classify,
)
from lifeops.domain.workflow_templates import (
    MAX_STEPS,
    TriggerKind,
    WorkflowStep,
    WorkflowTemplateDraft,
)
from lifeops.errors import LifeOpsError, ValidationError
from lifeops.policy.capabilities import CODING_CLIENT, CONSOLE, HERMES, Capability
from lifeops.repositories.fakes import (
    FakeActionRepository,
    FakeApprovalRepository,
    FakeAuditRepository,
    FakeBillRepository,
    FakeMemoryRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
    FakeWaitingRepository,
    FakeWorkflowTemplateRepository,
    FakeWorldRepository,
)
from lifeops.settings import Settings

TS = "2026-01-01T00:00:00Z"


@pytest.fixture
async def core(tmp_path: Path) -> LifeOpsCore:
    people = FakePersonRepository()
    await people.upsert(
        Person(id="person_u", display_name="U", is_primary=True,
               created_at=TS, updated_at=TS)
    )
    return LifeOpsCore(
        people=people, preferences=FakePreferenceRepository(), tasks=FakeTaskRepository(),
        memory=FakeMemoryRepository(), world=FakeWorldRepository(),
        waiting=FakeWaitingRepository(), actions=FakeActionRepository(),
        approvals=FakeApprovalRepository(), audit=FakeAuditRepository(),
        bills=FakeBillRepository(), templates=FakeWorkflowTemplateRepository(),
        change_request_dir=str(tmp_path / "requests"), clock=FrozenClock(),
    )


class TestTheBoundary:
    @pytest.mark.parametrize("component", PROTECTED_COMPONENTS)
    def test_every_section_73_protected_component_is_classified(
        self, component: str
    ) -> None:
        assert classify(component) is True

    def test_matching_is_generous_about_phrasing(self) -> None:
        """Under-matching applies a protected change; over-matching only files
        a request for something that could have been applied directly."""
        assert classify("the approval validation module") is True
        assert classify("Payment Code") is True

    @pytest.mark.parametrize(
        "component", ["morning brief", "weekly review skill", "provider-manager"]
    )
    def test_ordinary_components_are_not_protected(self, component: str) -> None:
        assert classify(component) is False

    def test_an_unnamed_component_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            classify("   ")


class TestForbiddenEffects:
    @pytest.mark.parametrize(
        "effect",
        [
            "grant_capability",
            "revoke_capability",
            "disable_safe_mode",
            "disable_emergency_stop",
            "read_secret",
            "modify_approval_rules",
        ],
    )
    def test_a_self_change_may_never_have_these_effects(self, effect: str) -> None:
        """Each is a way to turn a permitted change into a protected one.
        A routine that grants itself a capability is not a routine change."""
        proposal = SelfConfigProposal(
            target=SelfConfigTarget.CRON_JOB, name="nightly", effects=[effect]
        )
        with pytest.raises(ValidationError) as excinfo:
            check_permitted(proposal)
        assert effect in str(excinfo.value)

    def test_a_forbidden_effect_beats_a_permitted_target(self) -> None:
        """The target says what it claims to be; the effect says what it does."""
        proposal = SelfConfigProposal(
            target=SelfConfigTarget.REMINDER,
            name="harmless reminder",
            effects=["disable_emergency_stop"],
        )
        with pytest.raises(ValidationError):
            check_permitted(proposal)

    def test_an_ordinary_change_passes(self) -> None:
        check_permitted(
            SelfConfigProposal(
                target=SelfConfigTarget.ROUTINE_TEMPLATE, name="morning brief"
            )
        )


class TestTemplates:
    async def test_hermes_may_manage_its_own_templates(self, core: LifeOpsCore) -> None:
        saved = await core.save_workflow_template(
            HERMES,
            WorkflowTemplateDraft(
                name="Book an electrician",
                steps=[
                    WorkflowStep(order=5, description="Book it"),
                    WorkflowStep(order=1, description="Collect a quote"),
                ],
            ),
        )
        # Order is normalised, so a template revised piecemeal stays coherent.
        assert [s.order for s in saved.steps] == [0, 1]
        assert [s.description for s in saved.steps] == ["Collect a quote", "Book it"]

    async def test_a_client_without_the_capability_cannot(
        self, core: LifeOpsCore
    ) -> None:
        assert Capability.SELF_CONFIGURE not in CODING_CLIENT.capabilities
        with pytest.raises(LifeOpsError) as excinfo:
            await core.save_workflow_template(
                CODING_CLIENT, WorkflowTemplateDraft(name="whatever")
            )
        assert excinfo.value.code == "capability_denied"

    async def test_a_template_named_for_a_protected_component_is_refused(
        self, core: LifeOpsCore
    ) -> None:
        with pytest.raises(ValidationError):
            await core.save_workflow_template(
                HERMES, WorkflowTemplateDraft(name="approval validation")
            )

    async def test_a_scheduled_routine_needs_a_time(self, core: LifeOpsCore) -> None:
        with pytest.raises(ValidationError):
            await core.save_workflow_template(
                HERMES,
                WorkflowTemplateDraft(name="nightly", trigger=TriggerKind.SCHEDULE),
            )

    async def test_a_template_that_is_really_a_program_is_refused(
        self, core: LifeOpsCore
    ) -> None:
        steps = [
            WorkflowStep(order=i, description=f"Step {i}") for i in range(MAX_STEPS + 1)
        ]
        with pytest.raises(ValidationError):
            await core.save_workflow_template(
                HERMES, WorkflowTemplateDraft(name="epic", steps=steps)
            )


class TestCodeChangeRequests:
    async def test_a_request_is_written_to_the_repository(
        self, core: LifeOpsCore, tmp_path: Path
    ) -> None:
        """Section 74: persisted under changes/requests/. A coding agent reads
        the repository, not the user's database."""
        request = await core.request_code_change(
            HERMES,
            component="approval validation",
            problem="Approvals expire before the user can read them",
            observed_behavior="30 minute TTL",
            desired_behavior="configurable TTL",
            risk="medium",
            suggested_acceptance_tests=["an expired approval authorises nothing"],
        )
        written = tmp_path / "requests" / f"{request.id}.json"
        assert written.exists()

        payload = json.loads(written.read_text())
        # Section 74's schema, field for field.
        for field in (
            "component", "problem", "observed_behavior", "desired_behavior",
            "task_ids", "trace_ids", "failure_count", "risk",
            "suggested_acceptance_tests",
        ):
            assert field in payload
        assert payload["component"] == "approval validation"

    async def test_filing_a_request_does_not_apply_the_change(
        self, core: LifeOpsCore
    ) -> None:
        """The whole point of section 100: a protected change is written down,
        not partially applied and not applied with a warning."""
        await core.request_code_change(
            HERMES, component="payment code", problem="p",
            observed_behavior="o", desired_behavior="d", risk="high",
        )
        # The protected component is still protected afterwards.
        with pytest.raises(ValidationError):
            check_permitted(
                SelfConfigProposal(target=SelfConfigTarget.SKILL, name="payment code")
            )

    async def test_the_refusal_is_audited(self, core: LifeOpsCore) -> None:
        """Section 62 must answer 'why did Hermes do that?' for a refusal too."""
        await core.request_code_change(
            HERMES, component="secret-store implementation", problem="p",
            observed_behavior="o", desired_behavior="d", risk="high",
        )
        records = await core.read_audit(CONSOLE, limit=10)
        filed = [r for r in records if r.intent == "request_code_change"]
        assert filed
        assert filed[0].details.get("protected") == "True"


class TestPausingARoutine:
    """A paused routine that resumes itself is worse than one that cannot be
    paused at all — the user disabled it for a reason and would not be told."""

    async def test_a_routine_can_be_paused(self, core: LifeOpsCore) -> None:
        saved = await core.save_workflow_template(
            HERMES, WorkflowTemplateDraft(name="Nightly sweep", enabled=False)
        )
        assert saved.enabled is False

    async def test_revising_a_paused_routine_leaves_it_paused(
        self, core: LifeOpsCore
    ) -> None:
        await core.save_workflow_template(
            HERMES, WorkflowTemplateDraft(name="Nightly sweep", enabled=False)
        )
        revised = await core.save_workflow_template(
            HERMES,
            WorkflowTemplateDraft(
                name="Nightly sweep", description="now with a note", enabled=False
            ),
        )
        assert revised.enabled is False

    async def test_a_paused_scheduled_routine_never_comes_due(
        self, core: LifeOpsCore
    ) -> None:
        await core.save_workflow_template(
            HERMES,
            WorkflowTemplateDraft(
                name="Nightly sweep",
                trigger=TriggerKind.SCHEDULE,
                next_run_at="2020-01-01T00:00:00Z",
                enabled=False,
            ),
        )
        assert await core.due_routines(HERMES) == []


class TestChangeRequestPathResolution:
    """The write path must not depend on the process's CWD: the MCP server's
    working directory is whatever its client launched it with, and a
    read-only deployment cannot write into the repository at all."""

    def test_explicit_override_wins(self, tmp_path: Path) -> None:
        settings = Settings(
            state_dir=tmp_path / "state", change_requests_dir=tmp_path / "explicit"
        )
        assert settings.change_requests_path == tmp_path / "explicit"

    def test_default_is_absolute_never_cwd_relative(self, tmp_path: Path) -> None:
        settings = Settings(state_dir=tmp_path / "state")
        resolved = settings.change_requests_path
        assert resolved.is_absolute()
        # Either the repository checkout's changes/requests (when writable)
        # or the state directory — both are stable regardless of CWD.
        assert resolved.name in ("requests", "change-requests")
