"""The task state machine is a safety boundary, so it is tested as one."""

from __future__ import annotations

import pytest

from lifeops.domain.tasks import (
    TERMINAL_STATES,
    Task,
    TaskState,
    VerificationState,
    allowed_transitions,
    apply_transition,
    can_transition,
    validate_transition,
)
from lifeops.errors import InvalidTransitionError, VerificationRequiredError

NOW = "2026-01-01T00:00:00Z"


def make_task(
    state: TaskState = TaskState.CAPTURED,
    *,
    verification_required: bool = False,
    evidence: str | None = None,
) -> Task:
    return Task(
        id="task_test",
        title="Test task",
        state=state,
        created_at=NOW,
        updated_at=NOW,
        verification_required=verification_required,
        verification_state=(
            VerificationState.PENDING
            if verification_required
            else VerificationState.NOT_REQUIRED
        ),
        verification_evidence=evidence,
    )


class TestTransitionTable:
    def test_every_state_has_an_entry(self) -> None:
        # A missing entry would raise KeyError at runtime rather than deny.
        for state in TaskState:
            assert isinstance(allowed_transitions(state), frozenset)

    def test_terminal_states_allow_nothing(self) -> None:
        for state in TERMINAL_STATES:
            assert allowed_transitions(state) == frozenset()

    def test_no_state_transitions_to_itself_in_the_table(self) -> None:
        for state in TaskState:
            assert state not in allowed_transitions(state)

    def test_captured_cannot_jump_to_completed(self) -> None:
        assert not can_transition(TaskState.CAPTURED, TaskState.COMPLETED)

    def test_failed_can_be_retried_but_not_completed_directly(self) -> None:
        assert can_transition(TaskState.FAILED, TaskState.READY)
        assert not can_transition(TaskState.FAILED, TaskState.COMPLETED)


class TestValidateTransition:
    def test_same_state_is_a_noop(self) -> None:
        task = make_task(TaskState.EXECUTING)
        validate_transition(task, TaskState.EXECUTING)

    def test_legal_transition_passes(self) -> None:
        validate_transition(make_task(TaskState.READY), TaskState.EXECUTING)

    def test_illegal_transition_raises(self) -> None:
        with pytest.raises(InvalidTransitionError) as exc:
            validate_transition(make_task(TaskState.CAPTURED), TaskState.COMPLETED)
        assert exc.value.details["current_state"] == "CAPTURED"
        assert "PLANNED" in exc.value.details["allowed"]

    def test_terminal_task_cannot_move(self) -> None:
        with pytest.raises(InvalidTransitionError):
            validate_transition(make_task(TaskState.COMPLETED), TaskState.READY)

    def test_cancelled_task_cannot_be_revived(self) -> None:
        with pytest.raises(InvalidTransitionError):
            validate_transition(make_task(TaskState.CANCELLED), TaskState.READY)


class TestVerificationGate:
    """BUILD_SPEC section 53: external work completes on evidence, not assertion."""

    def test_unverified_task_cannot_complete_from_executing(self) -> None:
        task = make_task(TaskState.EXECUTING, verification_required=True)
        with pytest.raises(VerificationRequiredError):
            validate_transition(task, TaskState.COMPLETED)

    def test_verifying_without_evidence_cannot_complete(self) -> None:
        task = make_task(TaskState.VERIFYING, verification_required=True)
        with pytest.raises(VerificationRequiredError):
            validate_transition(task, TaskState.COMPLETED)

    def test_verifying_with_evidence_completes(self) -> None:
        task = make_task(TaskState.VERIFYING, verification_required=True)
        validate_transition(task, TaskState.COMPLETED, verification_evidence="CONF-123")

    def test_evidence_already_on_the_task_counts(self) -> None:
        task = make_task(
            TaskState.VERIFYING, verification_required=True, evidence="CONF-9"
        )
        validate_transition(task, TaskState.COMPLETED)

    def test_task_without_verification_completes_directly(self) -> None:
        task = make_task(TaskState.EXECUTING, verification_required=False)
        validate_transition(task, TaskState.COMPLETED)


class TestApplyTransition:
    def test_returns_a_new_task_and_leaves_the_original_alone(self) -> None:
        task = make_task(TaskState.READY)
        updated = apply_transition(task, TaskState.EXECUTING, now="2026-02-02T00:00:00Z")
        assert updated.state is TaskState.EXECUTING
        assert task.state is TaskState.READY

    def test_records_the_acting_client(self) -> None:
        updated = apply_transition(
            make_task(TaskState.READY),
            TaskState.EXECUTING,
            now=NOW,
            actor_client="hermes-personal",
        )
        assert updated.assigned_client == "hermes-personal"

    def test_verification_state_tracks_the_lifecycle(self) -> None:
        task = make_task(TaskState.EXECUTING, verification_required=True)
        verifying = apply_transition(task, TaskState.VERIFYING, now=NOW)
        assert verifying.verification_state is VerificationState.PENDING

        completed = apply_transition(
            verifying, TaskState.COMPLETED, now=NOW, verification_evidence="CONF-1"
        )
        assert completed.verification_state is VerificationState.VERIFIED
        assert completed.verification_evidence == "CONF-1"

    def test_failure_marks_verification_failed(self) -> None:
        task = make_task(TaskState.VERIFYING, verification_required=True)
        failed = apply_transition(task, TaskState.FAILED, now=NOW)
        assert failed.verification_state is VerificationState.FAILED

    def test_terminal_transition_clears_current_action(self) -> None:
        task = make_task(TaskState.EXECUTING)
        task.current_action = "calling provider"
        done = apply_transition(task, TaskState.COMPLETED, now=NOW)
        assert done.current_action is None


class TestAttentionFlags:
    @pytest.mark.parametrize(
        "state",
        [TaskState.NEEDS_APPROVAL, TaskState.BLOCKED, TaskState.FAILED],
    )
    def test_states_needing_a_human(self, state: TaskState) -> None:
        assert make_task(state).needs_attention

    @pytest.mark.parametrize(
        "state", [TaskState.CAPTURED, TaskState.EXECUTING, TaskState.COMPLETED]
    )
    def test_states_not_needing_a_human(self, state: TaskState) -> None:
        assert not make_task(state).needs_attention
