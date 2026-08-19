"""Shopping: search, cart building, substitutions, approval-gated checkout,
and verification (BUILD_SPEC section 98), exercised against fakes end to end.

This is the suite that proves section 98's flow actually holds at the
orchestration layer, not just in the pure functions: create a list -> build a
cart (R1, automatic, no approval) -> submit for checkout (R3, always
approved) -> approve -> commit + execute -> independently verify. It also
proves section 57's binding survives a substitution applied after approval —
the specific safety property BUILD_SPEC section 98 calls out by name.

Nothing here reaches NornicDB or a real browser; ``FakeWorldRepository`` and
``FakeBrowser`` stand in for both, the same role ``FakeCalendarProvider``
plays in ``test_calendar_email_core.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lifeops.browser.fake import FakeBrowser
from lifeops.browser.service import BrowserProviderService
from lifeops.clock import FrozenClock
from lifeops.config.service import ConfigurationService
from lifeops.core import LifeOpsCore
from lifeops.domain.actions import ActionStatus, ActionType, RiskClass, risk_for_action
from lifeops.domain.people import Person
from lifeops.domain.shopping import (
    ShoppingItem,
    ShoppingListDraft,
    ShoppingListStatus,
    SubstitutionDraft,
    apply_substitution,
    build_cart_payload,
    checkout_payload,
    create,
    entity_to_shopping_list,
    shopping_list_to_entity,
)
from lifeops.errors import CapabilityDeniedError, ConflictError, NotFoundError, ValidationError
from lifeops.policy.capabilities import CODING_CLIENT, CONSOLE, HERMES, INTERACTIVE_CLIENT
from lifeops.repositories.fakes import (
    FakeActionRepository,
    FakeApprovalRepository,
    FakeAuditRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeShoppingRepository,
    FakeTaskRepository,
    FakeWaitingRepository,
    FakeWorldRepository,
)
from lifeops.secrets.local_encrypted import InMemorySecretStore

PRIMARY = "person_shopping_user"
NOW = "2026-09-01T00:00:00Z"


@pytest.fixture
def fake_browser() -> FakeBrowser:
    return FakeBrowser()


@pytest.fixture
def config_service(tmp_path: Path) -> ConfigurationService:
    secrets = InMemorySecretStore()
    return ConfigurationService(
        config_dir=tmp_path / "config", secret_store=secrets, clock=FrozenClock()
    )


@pytest.fixture
def browser_service(
    config_service: ConfigurationService, fake_browser: FakeBrowser
) -> BrowserProviderService:
    config_service.update_provider("browser", {"enabled": True})
    return BrowserProviderService(
        config=config_service,
        secret_store=InMemorySecretStore(),
        factories={"browser": lambda settings, secrets: fake_browser},
    )


@pytest.fixture
async def core(browser_service: BrowserProviderService) -> LifeOpsCore:
    people = FakePersonRepository()
    await people.upsert(
        Person(
            id=PRIMARY,
            display_name="Shopping User",
            is_primary=True,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    preferences = FakePreferenceRepository()
    world = FakeWorldRepository(preferences=preferences)
    return LifeOpsCore(
        people=people,
        preferences=preferences,
        tasks=FakeTaskRepository(),
        world=world,
        waiting=FakeWaitingRepository(),
        actions=FakeActionRepository(),
        approvals=FakeApprovalRepository(),
        audit=FakeAuditRepository(),
        shopping=FakeShoppingRepository(),
        browser=browser_service,
        clock=FrozenClock(),
    )


async def _open_list(core: LifeOpsCore, *, client=HERMES):
    return await core.create_shopping_list(
        client,
        ShoppingListDraft(
            title="Weekly groceries",
            store="fakemart",
            items=[
                ShoppingItem(name="Milk", quantity="1 gal"),
                ShoppingItem(name="Eggs", quantity="1 dozen"),
            ],
        ),
    )


class TestRiskClasses:
    """Section 56's split: cart building is free, checkout is gated."""

    def test_build_cart_is_r1_reversible(self) -> None:
        assert risk_for_action(ActionType.BUILD_GROCERY_CART) is RiskClass.R1_REVERSIBLE

    def test_submit_order_is_r3_always_approved(self) -> None:
        assert (
            risk_for_action(ActionType.SUBMIT_GROCERY_ORDER)
            is RiskClass.R3_EXTERNAL_COMMITMENT
        )


class TestDomainRules:
    def test_create_normalises_title_and_store(self) -> None:
        shopping_list = create(
            ShoppingListDraft(title="  Groceries  ", store=" fakemart "),
            now=NOW,
            client_id="hermes-personal",
        )
        assert shopping_list.title == "Groceries"
        assert shopping_list.store == "fakemart"
        assert shopping_list.status is ShoppingListStatus.DRAFT

    def test_apply_substitution_updates_the_matching_item(self) -> None:
        shopping_list = create(
            ShoppingListDraft(title="List", items=[ShoppingItem(name="Milk")]),
            now=NOW,
            client_id="hermes-personal",
        )
        updated = apply_substitution(
            shopping_list,
            SubstitutionDraft(
                item_name="milk", substituted_with="Oat milk", reason="out of stock"
            ),
            now=NOW,
        )
        assert updated.items[0].substituted_with == "Oat milk"
        assert updated.items[0].substitution_reason == "out of stock"

    def test_apply_substitution_refuses_an_unknown_item(self) -> None:
        shopping_list = create(
            ShoppingListDraft(title="List", items=[ShoppingItem(name="Milk")]),
            now=NOW,
            client_id="hermes-personal",
        )
        with pytest.raises(NotFoundError):
            apply_substitution(
                shopping_list,
                SubstitutionDraft(item_name="Bread", substituted_with="Bagels"),
                now=NOW,
            )

    def test_apply_substitution_refuses_a_disallowed_item(self) -> None:
        shopping_list = create(
            ShoppingListDraft(
                title="List",
                items=[ShoppingItem(name="Milk", substitution_allowed=False)],
            ),
            now=NOW,
            client_id="hermes-personal",
        )
        with pytest.raises(ValidationError):
            apply_substitution(
                shopping_list,
                SubstitutionDraft(item_name="Milk", substituted_with="Oat milk"),
                now=NOW,
            )

    def test_checkout_payload_carries_substitutions_for_the_approval_screen(self) -> None:
        """Section 58: the approval screen must show what will actually
        happen — a substituted item, not the original silently swapped."""
        shopping_list = create(
            ShoppingListDraft(title="List", items=[ShoppingItem(name="Milk")]),
            now=NOW,
            client_id="hermes-personal",
        )
        shopping_list = apply_substitution(
            shopping_list,
            SubstitutionDraft(item_name="Milk", substituted_with="Oat milk"),
            now=NOW,
        )
        payload = checkout_payload(shopping_list)
        assert payload["items"][0]["substituted_with"] == "Oat milk"

    def test_world_projection_round_trips(self) -> None:
        shopping_list = create(
            ShoppingListDraft(
                title="List", store="fakemart", items=[ShoppingItem(name="Milk", quantity="2")]
            ),
            now=NOW,
            client_id="hermes-personal",
        )
        entity = shopping_list_to_entity(shopping_list)
        restored = entity_to_shopping_list(entity)
        assert restored == shopping_list


class TestCapability:
    async def test_a_client_without_shopping_checkout_cannot_search(
        self, core: LifeOpsCore
    ) -> None:
        with pytest.raises(CapabilityDeniedError):
            await core.search_shopping(CODING_CLIENT, query="milk")

    async def test_a_client_without_shopping_checkout_cannot_create_a_list(
        self, core: LifeOpsCore
    ) -> None:
        with pytest.raises(CapabilityDeniedError):
            await _open_list(core, client=INTERACTIVE_CLIENT)


class TestSearch:
    async def test_search_returns_the_browsers_results(self, core: LifeOpsCore) -> None:
        results = await core.search_shopping(HERMES, query="milk", store="fakemart")
        assert results
        assert "milk" in results[0].name.lower()


class TestCartBuildIsAutomatic:
    """Section 56: a cart is reversible and commits nothing, so no approval."""

    async def test_build_grocery_cart_requires_no_approval(self, core: LifeOpsCore) -> None:
        shopping_list = await _open_list(core)
        action = await core.build_grocery_cart(HERMES, list_id=shopping_list.id)
        # No human step required: prepare + commit + execute happen in one call.
        assert action.status is ActionStatus.EXECUTED
        assert await core.list_pending_approvals(CONSOLE) == []

    async def test_build_grocery_cart_refuses_an_empty_list(self, core: LifeOpsCore) -> None:
        shopping_list = await core.create_shopping_list(
            HERMES, ShoppingListDraft(title="Empty", store="fakemart")
        )
        with pytest.raises(ValidationError):
            await core.build_grocery_cart(HERMES, list_id=shopping_list.id)

    async def test_verifying_the_cart_marks_the_list_built(self, core: LifeOpsCore) -> None:
        shopping_list = await _open_list(core)
        action = await core.build_grocery_cart(HERMES, list_id=shopping_list.id)
        verified = await core.verify_action_externally(HERMES, action_id=action.id)
        assert verified.status is ActionStatus.VERIFIED

        updated = await core.get_shopping_list(HERMES, list_id=shopping_list.id)
        assert updated.status is ShoppingListStatus.CART_BUILT
        assert updated.cart_reference == verified.external_reference


class TestCheckoutRequiresApproval:
    """Section 56's "Shopping checkout" — R3, always approval."""

    async def _built_cart(self, core: LifeOpsCore):
        shopping_list = await _open_list(core)
        action = await core.build_grocery_cart(HERMES, list_id=shopping_list.id)
        await core.verify_action_externally(HERMES, action_id=action.id)
        return await core.get_shopping_list(HERMES, list_id=shopping_list.id)

    async def test_submit_grocery_order_cannot_execute_before_approval(
        self, core: LifeOpsCore
    ) -> None:
        built = await self._built_cart(core)
        action = await core.submit_grocery_order(HERMES, list_id=built.id)
        assert action.status is ActionStatus.NEEDS_APPROVAL
        with pytest.raises(ConflictError):
            await core.execute_action(HERMES, action_id=action.id)

    async def test_submit_grocery_order_refuses_a_list_with_no_built_cart(
        self, core: LifeOpsCore
    ) -> None:
        shopping_list = await _open_list(core)
        with pytest.raises(ValidationError):
            await core.submit_grocery_order(HERMES, list_id=shopping_list.id)

    async def test_the_full_checkout_flow_submits_and_independently_verifies(
        self, core: LifeOpsCore
    ) -> None:
        built = await self._built_cart(core)
        action = await core.submit_grocery_order(HERMES, list_id=built.id)

        pending = await core.list_pending_approvals(CONSOLE)
        assert len(pending) == 1
        await core.decide_approval(CONSOLE, approval_id=pending[0].id, approved=True)

        executed = await core.execute_action(HERMES, action_id=action.id)
        assert executed.status is ActionStatus.EXECUTED

        # Executed is a claim, not a fact (section 6) — the list is not
        # VERIFIED yet.
        still_submitting = await core.get_shopping_list(HERMES, list_id=built.id)
        assert still_submitting.status is not ShoppingListStatus.VERIFIED

        verified = await core.verify_action_externally(HERMES, action_id=action.id)
        assert verified.status is ActionStatus.VERIFIED

        final = await core.get_shopping_list(HERMES, list_id=built.id)
        assert final.status is ShoppingListStatus.VERIFIED
        assert final.order_reference == verified.external_reference

    async def test_only_hermes_and_the_console_may_check_out(self, core: LifeOpsCore) -> None:
        built = await self._built_cart(core)
        with pytest.raises(CapabilityDeniedError):
            await core.submit_grocery_order(INTERACTIVE_CLIENT, list_id=built.id)


class TestApproveActionIsConsoleOnly:
    async def test_hermes_cannot_approve_its_own_checkout(self, core: LifeOpsCore) -> None:
        shopping_list = await _open_list(core)
        cart_action = await core.build_grocery_cart(HERMES, list_id=shopping_list.id)
        await core.verify_action_externally(HERMES, action_id=cart_action.id)
        built = await core.get_shopping_list(HERMES, list_id=shopping_list.id)
        checkout_action = await core.submit_grocery_order(HERMES, list_id=built.id)
        pending = await core.list_pending_approvals(CONSOLE)

        with pytest.raises(CapabilityDeniedError):
            await core.decide_approval(HERMES, approval_id=pending[0].id, approved=True)
        assert checkout_action.status is ActionStatus.NEEDS_APPROVAL


class TestSubstitutionInvalidatesApproval:
    """The safety property BUILD_SPEC section 98 calls out by name: a
    substitution applied after a human approved the cart must not ride
    through on that approval (section 57's binding).

    Mirrors the pattern in ``tests/unit/test_durable_work.py::
    TestApprovalBinding`` — a material change makes the stored approval's
    payload hash stop matching the action's, so it no longer authorises it.
    """

    async def _approved_checkout(self, core: LifeOpsCore):
        shopping_list = await _open_list(core)
        cart_action = await core.build_grocery_cart(HERMES, list_id=shopping_list.id)
        await core.verify_action_externally(HERMES, action_id=cart_action.id)
        built = await core.get_shopping_list(HERMES, list_id=shopping_list.id)
        action = await core.submit_grocery_order(HERMES, list_id=built.id)
        pending = await core.list_pending_approvals(CONSOLE)
        approval = await core.decide_approval(
            CONSOLE, approval_id=pending[0].id, approved=True
        )
        return built, action, approval

    async def test_a_substitution_after_approval_blocks_execution(
        self, core: LifeOpsCore
    ) -> None:
        built, action, approval = await self._approved_checkout(core)
        assert approval.status == "approved"

        await core.apply_substitution(
            HERMES,
            list_id=built.id,
            draft=SubstitutionDraft(item_name="Milk", substituted_with="Oat milk"),
        )

        # The old approval no longer matches the action's current payload —
        # execute_action must refuse rather than let a stale yes authorise a
        # materially different order.
        with pytest.raises(ConflictError):
            await core.execute_action(HERMES, action_id=action.id)

    async def test_a_substitution_after_approval_requests_a_fresh_one(
        self, core: LifeOpsCore
    ) -> None:
        built, action, _ = await self._approved_checkout(core)
        assert await core.list_pending_approvals(CONSOLE) == []

        await core.apply_substitution(
            HERMES,
            list_id=built.id,
            draft=SubstitutionDraft(item_name="Eggs", substituted_with="Egg substitute"),
        )

        pending = await core.list_pending_approvals(CONSOLE)
        assert len(pending) == 1
        assert pending[0].action_id == action.id

        # And approving *that* one lets the substituted order execute.
        await core.decide_approval(CONSOLE, approval_id=pending[0].id, approved=True)
        executed = await core.execute_action(HERMES, action_id=action.id)
        assert executed.status is ActionStatus.EXECUTED

    async def test_a_substitution_before_checkout_exists_does_not_touch_actions(
        self, core: LifeOpsCore
    ) -> None:
        """Applying a substitution while only the cart-build action exists
        (no checkout prepared yet) must not error — there is nothing to
        refresh."""
        shopping_list = await _open_list(core)
        updated = await core.apply_substitution(
            HERMES,
            list_id=shopping_list.id,
            draft=SubstitutionDraft(item_name="Milk", substituted_with="Oat milk"),
        )
        assert updated.items[0].substituted_with == "Oat milk"


class TestBuildCartPayload:
    def test_build_cart_payload_carries_the_items(self) -> None:
        shopping_list = create(
            ShoppingListDraft(
                title="List", store="fakemart", items=[ShoppingItem(name="Milk")]
            ),
            now=NOW,
            client_id="hermes-personal",
        )
        payload = build_cart_payload(shopping_list)
        assert payload["shopping_list_id"] == shopping_list.id
        assert payload["items"][0]["name"] == "Milk"


class TestSubmittingIsRecoverable:
    """A declined or failed checkout must not wedge the list: SUBMITTING has
    an exit back to CART_BUILT, so the groceries can still be bought."""

    async def _submitting(self, core: LifeOpsCore):
        shopping_list = await _open_list(core)
        cart_action = await core.build_grocery_cart(HERMES, list_id=shopping_list.id)
        await core.verify_action_externally(HERMES, action_id=cart_action.id)
        built = await core.get_shopping_list(HERMES, list_id=shopping_list.id)
        action = await core.submit_grocery_order(HERMES, list_id=built.id)
        return built, action

    async def test_a_declined_checkout_returns_the_list_to_cart_built(
        self, core: LifeOpsCore
    ) -> None:
        built, action = await self._submitting(core)
        pending = await core.list_pending_approvals(CONSOLE)
        await core.decide_approval(CONSOLE, approval_id=pending[0].id, approved=False)

        recovered = await core.get_shopping_list(HERMES, list_id=built.id)
        assert recovered.status is ShoppingListStatus.CART_BUILT
        # And the checkout can genuinely be retried, producing a fresh
        # decidable card. The retry re-opens the SAME outbox record — the
        # idempotency-key uniqueness constraint (section 61's backstop, now
        # enforced by the fake too) forbids a second Action under one key,
        # and minting one was exactly two chances to submit one order. The
        # old expectation of a fresh id only ever passed against the
        # unconstrained fake; production would have refused the insert.
        retry = await core.submit_grocery_order(HERMES, list_id=built.id)
        assert retry.id == action.id
        assert retry.status is ActionStatus.NEEDS_APPROVAL
        assert retry.failure_reason is None
        fresh_cards = await core.list_pending_approvals(CONSOLE)
        assert [a.action_id for a in fresh_cards] == [retry.id]

    async def test_a_failed_checkout_execution_returns_the_list_to_cart_built(
        self, core: LifeOpsCore, fake_browser: FakeBrowser
    ) -> None:
        built, action = await self._submitting(core)
        pending = await core.list_pending_approvals(CONSOLE)
        await core.decide_approval(CONSOLE, approval_id=pending[0].id, approved=True)

        # The store loses the cart between approval and execution — the
        # provider raises, and the failure must land in the outbox rather
        # than escape (the old narrow catch let repository errors through).
        fake_browser._carts.clear()
        result = await core.execute_action(HERMES, action_id=action.id)
        assert result.status is ActionStatus.FAILED

        recovered = await core.get_shopping_list(HERMES, list_id=built.id)
        assert recovered.status is ShoppingListStatus.CART_BUILT
