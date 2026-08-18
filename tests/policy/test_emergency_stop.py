"""Emergency stop and safe mode, proven (BUILD_SPEC sections 83, 84, 99).

Section 99 lists "emergency stop proven" as a precondition for ever enabling
payments in Phase 10. "Proven" here means: every external action type is
actually refused while safe mode is engaged, everything section 83 allows
still works, and engaging it preserves state exactly as section 84 requires
(nothing deleted, the audit log still records, previously prepared actions
stay readable).

This suite enumerates ``ActionType`` directly rather than hard-coding a list,
so a future action type that forgets to declare a capability
(``capability_for_action``) or lands outside ``SAFE_MODE_BLOCKED`` fails this
test instead of silently shipping unprotected.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lifeops.clock import FrozenClock
from lifeops.config.service import ConfigurationService
from lifeops.core import LifeOpsCore
from lifeops.domain.actions import ActionDraft, ActionStatus, ActionType
from lifeops.domain.memory import MemoryDraft
from lifeops.domain.people import Person
from lifeops.domain.preferences import PreferenceDraft
from lifeops.domain.tasks import TaskDraft, TaskState, TaskUpdate
from lifeops.domain.waiting import WaitingDraft
from lifeops.errors import SafeModeError
from lifeops.policy.capabilities import CONSOLE, HERMES, SAFE_MODE_BLOCKED, capability_for_action
from lifeops.repositories.fakes import (
    FakeActionRepository,
    FakeApprovalRepository,
    FakeAuditRepository,
    FakeMemoryRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
    FakeWaitingRepository,
)
from lifeops.secrets.local_encrypted import InMemorySecretStore

PRIMARY = "person_emergency_stop_user"
NOW = "2026-08-17T00:00:00Z"


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock()


@pytest.fixture
async def core(clock: FrozenClock) -> LifeOpsCore:
    """A full LifeOpsCore — every repository the action outbox needs, plus
    memory and audit — backed entirely by in-memory fakes."""
    people = FakePersonRepository()
    await people.upsert(
        Person(
            id=PRIMARY,
            display_name="Emergency Stop User",
            is_primary=True,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    return LifeOpsCore(
        people=people,
        preferences=FakePreferenceRepository(),
        tasks=FakeTaskRepository(),
        memory=FakeMemoryRepository(),
        waiting=FakeWaitingRepository(),
        actions=FakeActionRepository(),
        approvals=FakeApprovalRepository(),
        audit=FakeAuditRepository(),
        clock=clock,
    )


# --- section 83: every external action type is refused ----------------------


class TestEveryActionTypeIsBlocked:
    """BUILD_SPEC section 83's disable list, checked against the actual
    enum rather than a hand-copied subset of it."""

    def test_action_type_enum_is_not_empty(self) -> None:
        # A guard against the enumeration below silently checking nothing.
        assert len(list(ActionType)) > 0

    def test_every_action_type_declares_a_capability(self) -> None:
        # capability_for_action raises for anything undeclared — a new action
        # type reaching this point without a mapping is a policy gap, not
        # something to skip quietly.
        for action_type in ActionType:
            capability_for_action(str(action_type))

    def test_every_action_type_capability_is_safe_mode_blocked(self) -> None:
        # The property the rest of this class relies on: nothing in the
        # action outbox is exempt from safe mode. A new action type whose
        # capability is NOT in SAFE_MODE_BLOCKED would fail here, forcing a
        # deliberate decision instead of an accidental gap.
        for action_type in ActionType:
            capability = capability_for_action(str(action_type))
            assert capability in SAFE_MODE_BLOCKED, (
                f"{action_type} spends {capability}, which safe mode does not block"
            )

    async def test_prepare_action_refuses_every_action_type_in_safe_mode(
        self, core: LifeOpsCore
    ) -> None:
        core.safe_mode = True
        for action_type in ActionType:
            with pytest.raises(SafeModeError) as exc:
                await core.prepare_action(HERMES, ActionDraft(type=action_type))
            assert exc.value.details["capability"] == str(
                capability_for_action(str(action_type))
            )

    async def test_prepare_action_refuses_even_for_a_client_without_the_capability(
        self, core: LifeOpsCore
    ) -> None:
        # Safe mode is checked before the capability grant (BUILD_SPEC
        # section 83's guarantee is unconditional, not "unless the caller
        # happens to be under-privileged already").
        core.safe_mode = True
        with pytest.raises(SafeModeError):
            await core.prepare_action(
                CONSOLE, ActionDraft(type=ActionType.COMMIT_PAYMENT)
            )

    async def test_actions_flow_normally_once_safe_mode_is_off(
        self, core: LifeOpsCore
    ) -> None:
        core.safe_mode = False
        action = await core.prepare_action(
            HERMES, ActionDraft(type=ActionType.SEND_EMAIL, payload={"to": "a@b.com"})
        )
        assert action.status in (ActionStatus.PREPARED, ActionStatus.NEEDS_APPROVAL)


# --- section 83: everything it allows keeps working --------------------------


class TestSafeModeAllowsWhatSection83Names:
    async def test_reads_still_work(self, core: LifeOpsCore) -> None:
        core.safe_mode = True
        person = await core.get_person(HERMES)
        assert person.id == PRIMARY

    async def test_preference_reads_and_writes_still_work(self, core: LifeOpsCore) -> None:
        core.safe_mode = True
        await core.save_preference(HERMES, PreferenceDraft(key="k", value="after 10am"))
        prefs = await core.get_preferences(HERMES)
        assert [p.value for p in prefs] == ["after 10am"]

    async def test_memory_search_still_works(self, core: LifeOpsCore) -> None:
        core.safe_mode = True
        await core.remember(HERMES, MemoryDraft(content="Gene prefers mornings"))
        results = await core.recall(HERMES, query="mornings")
        assert len(results) == 1

    async def test_tasks_still_work(self, core: LifeOpsCore) -> None:
        core.safe_mode = True
        task = await core.create_task(HERMES, TaskDraft(title="Call the vet"))
        assert task.id
        updated = await core.update_task(
            HERMES, task_id=task.id, update=TaskUpdate(state=TaskState.READY)
        )
        assert updated.state == TaskState.READY
        assert len(await core.list_tasks(HERMES)) == 1

    async def test_console_inspection_still_works(self, core: LifeOpsCore) -> None:
        # "Console inspection" — reading the audit log and prepared actions —
        # is exactly what section 84 says must survive an emergency stop.
        core.safe_mode = True
        records = await core.read_audit(CONSOLE)
        assert records == []
        assert await core.list_actions(CONSOLE) == []


# --- section 84: engaging it preserves state ---------------------------------


class TestEngagingSafeModePreservesState:
    async def test_previously_prepared_actions_remain_readable(
        self, core: LifeOpsCore
    ) -> None:
        core.safe_mode = False
        action = await core.prepare_action(
            HERMES, ActionDraft(type=ActionType.SEND_EMAIL, payload={"to": "a@b.com"})
        )

        core.safe_mode = True
        fetched = await core.get_action(CONSOLE, action_id=action.id)
        assert fetched.id == action.id
        assert fetched.status == action.status
        assert [a.id for a in await core.list_actions(CONSOLE)] == [action.id]

    async def test_nothing_is_deleted_by_engaging_safe_mode(
        self, core: LifeOpsCore
    ) -> None:
        core.safe_mode = False
        task = await core.create_task(HERMES, TaskDraft(title="Renew passport"))
        await core.save_preference(HERMES, PreferenceDraft(key="k", value="v"))
        await core.remember(HERMES, MemoryDraft(content="Passport expires in March"))

        core.safe_mode = True

        assert (await core.get_task(HERMES, task_id=task.id)).id == task.id
        assert len(await core.get_preferences(HERMES)) == 1
        assert len(await core.recall(HERMES, query="passport")) == 1

    async def test_audit_log_still_records_while_safe_mode_is_engaged(
        self, core: LifeOpsCore
    ) -> None:
        # An audit record written before safe mode was engaged...
        pre_task = await core.create_task(HERMES, TaskDraft(title="Before safe mode"))
        pre_item = await core.create_waiting_item(
            HERMES, WaitingDraft(task_id=pre_task.id, subject="a provider")
        )
        before = await core.read_audit(CONSOLE)
        assert any(r.target == pre_item.id for r in before)

        core.safe_mode = True

        # ...is still there, and permitted work keeps writing new ones.
        still_there = await core.read_audit(CONSOLE)
        assert any(r.target == pre_item.id for r in still_there)

        post_task = await core.create_task(HERMES, TaskDraft(title="During safe mode"))
        post_item = await core.create_waiting_item(
            HERMES, WaitingDraft(task_id=post_task.id, subject="another provider")
        )
        after = await core.read_audit(CONSOLE)
        assert any(r.target == post_item.id for r in after)
        assert len(after) == len(before) + 1

    async def test_denied_action_attempts_write_nothing(self, core: LifeOpsCore) -> None:
        # A refused prepare_action must not leave a half-written Action
        # behind — section 84's "preserve state" cuts both ways: it means
        # nothing existing is lost, and nothing spurious is added either.
        core.safe_mode = True
        with pytest.raises(SafeModeError):
            await core.prepare_action(
                HERMES, ActionDraft(type=ActionType.BOOK_APPOINTMENT)
            )
        assert await core.list_actions(CONSOLE) == []


# --- persistence across restart ----------------------------------------------


class TestSafeModePersistsAcrossRestart:
    """Section 84 requires a real control, not a flag that resets the moment
    the process does. ``safe_mode`` lives in the config document
    (``ConfigurationService``), not only in ``LifeOpsCore`` instance state —
    this proves a fresh service reading the same config directory sees it."""

    def test_safe_mode_survives_reloading_the_config_service(
        self, tmp_path: Path
    ) -> None:
        secrets = InMemorySecretStore()
        clock = FrozenClock()

        first = ConfigurationService(
            config_dir=tmp_path / "config", secret_store=secrets, clock=clock
        )
        assert first.get_system().safe_mode is False
        first.update_system({"safe_mode": True})

        # A brand new service instance, as a process restart would create,
        # pointed at the same on-disk config directory.
        second = ConfigurationService(
            config_dir=tmp_path / "config", secret_store=secrets, clock=clock
        )
        assert second.get_system().safe_mode is True

    def test_turning_safe_mode_off_also_persists(self, tmp_path: Path) -> None:
        secrets = InMemorySecretStore()
        clock = FrozenClock()

        first = ConfigurationService(
            config_dir=tmp_path / "config", secret_store=secrets, clock=clock
        )
        first.update_system({"safe_mode": True})
        first.update_system({"safe_mode": False})

        second = ConfigurationService(
            config_dir=tmp_path / "config", secret_store=secrets, clock=clock
        )
        assert second.get_system().safe_mode is False


class TestSafeModeReachesOtherProcesses:
    """The HTTP and MCP servers are separate processes over one config file.

    Section 84's emergency stop is pressed in the Console (the HTTP process)
    and must stop Hermes (the MCP process) — a snapshot taken at boot, or a
    config cache that never invalidates, leaves the one surface no human is
    watching running with the old answer until its next restart.
    """

    def test_a_toggle_by_one_service_is_seen_by_a_long_lived_other(
        self, tmp_path: Path
    ) -> None:
        secrets = InMemorySecretStore()
        clock = FrozenClock()

        console_side = ConfigurationService(
            config_dir=tmp_path / "config", secret_store=secrets, clock=clock
        )
        mcp_side = ConfigurationService(
            config_dir=tmp_path / "config", secret_store=secrets, clock=clock
        )
        # The MCP-side service has already read (and cached) the document,
        # as a long-running server would have.
        assert mcp_side.get_system().safe_mode is False

        console_side.update_system({"safe_mode": True})
        assert mcp_side.get_system().safe_mode is True

        console_side.update_system({"safe_mode": False})
        assert mcp_side.get_system().safe_mode is False

    async def test_core_with_a_live_source_blocks_without_restart(
        self, tmp_path: Path, core: LifeOpsCore
    ) -> None:
        secrets = InMemorySecretStore()
        config = ConfigurationService(
            config_dir=tmp_path / "config",
            secret_store=secrets,
            clock=FrozenClock(),
        )
        core.safe_mode = lambda: config.get_system().safe_mode

        # Another process (here: another service over the same file) engages
        # the stop; this core must refuse on its very next check.
        other = ConfigurationService(
            config_dir=tmp_path / "config",
            secret_store=secrets,
            clock=FrozenClock(),
        )
        other.update_system({"safe_mode": True})
        with pytest.raises(SafeModeError):
            await core.prepare_action(
                HERMES, ActionDraft(type=ActionType.BOOK_APPOINTMENT)
            )
