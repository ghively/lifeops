"""Capability enforcement (BUILD_SPEC sections 34, 35, 83).

Authority comes from the declared client identity, never from a model name and
never from what the caller asks for.
"""

from __future__ import annotations

import pytest

from lifeops.core import LifeOpsCore
from lifeops.domain.preferences import PreferenceDraft
from lifeops.domain.tasks import TaskDraft, TaskState, TaskUpdate
from lifeops.errors import CapabilityDeniedError, SafeModeError
from lifeops.policy import (
    CODING_CLIENT,
    CONSOLE,
    HERMES,
    INTERACTIVE_CLIENT,
    Capability,
    UnknownClientPolicy,
    all_clients,
    require,
    resolve_client,
)
from lifeops.policy.capabilities import SAFE_MODE_BLOCKED


class TestClientResolution:
    def test_known_clients_resolve(self) -> None:
        assert resolve_client("hermes-personal").client_id == "hermes-personal"
        assert resolve_client("claude-code").client_id == "claude-code"

    def test_resolution_is_case_insensitive(self) -> None:
        assert resolve_client("Hermes-Personal").client_id == "hermes-personal"

    def test_missing_identity_does_not_become_hermes(self) -> None:
        # Defaulting to the most privileged identity would make the manifest
        # decorative.
        assert resolve_client(None).client_id != HERMES.client_id

    def test_unknown_identity_can_be_refused(self) -> None:
        with pytest.raises(CapabilityDeniedError):
            resolve_client("totally-unknown", unknown=UnknownClientPolicy.DENY)

    def test_a_missing_identity_is_refused_under_deny_never_defaulted(self) -> None:
        """SECURITY.md: "Over MCP a missing identity is refused, never
        defaulted." The MCP server resolves with DENY, so an empty --client
        and an unset env var must fail loudly, not silently become the
        default identity — the 2026-08-18 audit found this branch missing."""
        with pytest.raises(CapabilityDeniedError):
            resolve_client(None, unknown=UnknownClientPolicy.DENY)
        with pytest.raises(CapabilityDeniedError):
            resolve_client("", unknown=UnknownClientPolicy.DENY)

    def test_unknown_identity_falls_back_to_the_least_privileged_default(self) -> None:
        fallback = resolve_client("totally-unknown")
        assert fallback.client_id == INTERACTIVE_CLIENT.client_id
        assert not fallback.has(Capability.FINANCIAL_PAYMENT)


class TestManifest:
    def test_only_the_console_may_move_money(self) -> None:
        # Phase 10 (sections 72, 99) grants FINANCIAL_PAYMENT, and grants it
        # to exactly one client. Section 72 requires that credentials are
        # never exposed to Hermes and that every payment and every new payee
        # is approved by a human; the narrowest way to guarantee both is for
        # the capability to exist only where a human is present.
        #
        # Hermes can read what is owed and tell the user a bill is due. It
        # holds no path from a model's reasoning to money moving.
        assert CONSOLE.has(Capability.FINANCIAL_PAYMENT)
        for client in all_clients():
            if client.client_id == CONSOLE.client_id:
                continue
            assert not client.has(Capability.FINANCIAL_PAYMENT), client.client_id

    def test_the_payment_capability_is_not_a_way_around_approval(self) -> None:
        # Holding FINANCIAL_PAYMENT lets the Console *prepare* a payment. It
        # still cannot commit one without an approval, and APPROVE_ACTION is
        # Console-only precisely so no agent approves its own.
        for client in all_clients():
            if client.has(Capability.APPROVE_ACTION):
                assert client.client_id == CONSOLE.client_id

    def test_only_hermes_and_the_console_may_book_or_message_externally(self) -> None:
        # Section 96: Hermes is the client that reads a calendar and drafts an
        # email on the user's behalf, and the Console is the user acting
        # directly — both need to *prepare* these Actions. Neither capability
        # is a way around approval: BOOK_APPOINTMENT actions still require
        # APPROVE_ACTION (Console-only) before they can execute.
        for client in (HERMES, CONSOLE):
            assert client.has(Capability.BOOK_APPOINTMENT), client.client_id
            assert client.has(Capability.SEND_EXTERNAL_MESSAGE), client.client_id
        for client in (INTERACTIVE_CLIENT, CODING_CLIENT):
            assert not client.has(Capability.BOOK_APPOINTMENT), client.client_id
            assert not client.has(Capability.SEND_EXTERNAL_MESSAGE), client.client_id

    def test_only_hermes_and_the_console_may_shop(self) -> None:
        # Section 98: Hermes builds and submits carts on the user's behalf,
        # and the Console is the user acting directly — both need to *prepare*
        # these Actions. SHOPPING_CHECKOUT is not a way around approval:
        # submit_grocery_order is R3 and always needs APPROVE_ACTION
        # (Console-only) before execute_action may run it.
        for client in (HERMES, CONSOLE):
            assert client.has(Capability.SHOPPING_CHECKOUT), client.client_id
        for client in (INTERACTIVE_CLIENT, CODING_CLIENT):
            assert not client.has(Capability.SHOPPING_CHECKOUT), client.client_id

    def test_coding_agent_cannot_rewrite_the_users_preferences(self) -> None:
        # Its job is the repository, not the user's life.
        assert not CODING_CLIENT.has(Capability.WRITE_PREFERENCE)
        assert not CODING_CLIENT.has(Capability.UPDATE_TASK)

    def test_coding_agent_can_still_read_and_file_tasks(self) -> None:
        assert CODING_CLIENT.has(Capability.READ_WORLD)
        assert CODING_CLIENT.has(Capability.READ_PREFERENCES)
        assert CODING_CLIENT.has(Capability.READ_TASKS)
        assert CODING_CLIENT.has(Capability.CREATE_TASK)

    def test_only_the_console_administers_configuration(self) -> None:
        assert CONSOLE.has(Capability.MANAGE_CONFIGURATION)
        for client in (HERMES, INTERACTIVE_CLIENT, CODING_CLIENT):
            assert not client.has(Capability.MANAGE_CONFIGURATION), client.client_id

    def test_only_the_console_approves_actions(self) -> None:
        # An agent approving its own action would defeat the whole gate.
        assert CONSOLE.has(Capability.APPROVE_ACTION)
        for client in (HERMES, INTERACTIVE_CLIENT, CODING_CLIENT):
            assert not client.has(Capability.APPROVE_ACTION), client.client_id

    def test_client_identities_are_immutable(self) -> None:
        # A grant that could be mutated at runtime would let any code path
        # quietly widen a client's authority.
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            CODING_CLIENT.capabilities = frozenset()  # type: ignore[misc]


class TestRequire:
    def test_permitted_capability_passes(self) -> None:
        require(HERMES, Capability.WRITE_PREFERENCE)

    def test_denied_capability_raises_with_context(self) -> None:
        with pytest.raises(CapabilityDeniedError) as exc:
            require(CODING_CLIENT, Capability.WRITE_PREFERENCE)
        assert exc.value.details["client_id"] == "claude-code"
        assert exc.value.details["capability"] == "write_preference"

    def test_safe_mode_blocks_external_capabilities(self) -> None:
        for capability in SAFE_MODE_BLOCKED:
            with pytest.raises(SafeModeError):
                require(CONSOLE, capability, safe_mode=True)

    def test_safe_mode_leaves_reads_and_tasks_alone(self) -> None:
        for capability in (
            Capability.READ_WORLD,
            Capability.READ_PREFERENCES,
            Capability.READ_TASKS,
            Capability.CREATE_TASK,
        ):
            require(HERMES, capability, safe_mode=True)

    def test_safe_mode_is_checked_before_the_grant(self) -> None:
        # An emergency stop must not be defeated by holding the capability.
        with pytest.raises(SafeModeError):
            require(CONSOLE, Capability.SEND_EXTERNAL_MESSAGE, safe_mode=True)


class TestEnforcementThroughCore:
    """The manifest has to bite at the operation, not just in isolation."""

    async def test_coding_agent_is_refused_a_preference_write(
        self, core: LifeOpsCore
    ) -> None:
        with pytest.raises(CapabilityDeniedError):
            await core.save_preference(
                CODING_CLIENT, PreferenceDraft(key="k", value="v")
            )

    async def test_coding_agent_may_read_preferences(self, core: LifeOpsCore) -> None:
        await core.save_preference(HERMES, PreferenceDraft(key="k", value="v"))
        prefs = await core.get_preferences(CODING_CLIENT)
        assert [p.value for p in prefs] == ["v"]

    async def test_coding_agent_may_create_a_task(self, core: LifeOpsCore) -> None:
        task = await core.create_task(CODING_CLIENT, TaskDraft(title="Call dentist"))
        assert task.created_by_client == "claude-code"

    async def test_coding_agent_is_refused_a_task_update(
        self, core: LifeOpsCore
    ) -> None:
        task = await core.create_task(HERMES, TaskDraft(title="Call dentist"))
        with pytest.raises(CapabilityDeniedError):
            await core.update_task(
                CODING_CLIENT, task_id=task.id, update=TaskUpdate(state=TaskState.READY)
            )

    async def test_safe_mode_does_not_block_phase_zero_work(
        self, core: LifeOpsCore
    ) -> None:
        core.safe_mode = True
        await core.save_preference(HERMES, PreferenceDraft(key="k", value="v"))
        await core.create_task(HERMES, TaskDraft(title="Still works"))
        assert len(await core.list_tasks(HERMES)) == 1
