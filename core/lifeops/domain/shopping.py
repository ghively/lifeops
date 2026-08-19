"""ShoppingList — grocery cart, substitutions, and checkout (BUILD_SPEC
sections 36, 56, 60, 98).

Section 98 asks for search/research, cart building, substitutions,
approval-gated checkout, and verification. Two of those are Actions the
outbox already knows how to drive — ``build_grocery_cart`` (R1, section 56:
"a cart is reversible and commits nothing") and ``submit_grocery_order`` (R3,
"Shopping checkout" — always approved) — declared in ``domain/actions.py``
before this phase existed, precisely so this module has no risk policy of its
own to invent.

A ``ShoppingList`` is projected into the world graph the same way Phase 7
projects an ``Appointment``: one node, current state as string facts (NornicDB
property values cannot be maps), read and written through the existing
``WorldRepository`` rather than a dedicated one. Items and substitutions are
the *plan*; the exact request each Action carries is a separate, point-in-time
payload built from that plan — the same split ``AppointmentService`` draws
between a held appointment and the ``book_appointment`` Action.

Section 57's binding is the reason that split matters here specifically.
``apply_substitution`` never rewrites a live checkout Action itself — that is
``LifeOpsCore.apply_substitution``'s job, because only ``ActionService`` can
recompute a payload hash and know whether an approval must be invalidated.
This module only produces the new plan and the new payload; it holds no
Action or Approval state to get out of sync.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from lifeops.domain.world import WorldEntity, WorldEntityType
from lifeops.errors import NotFoundError, ValidationError
from lifeops.ids import new_shopping_list_id


class ShoppingListStatus(StrEnum):
    """The section 98 lifecycle. Distinct BUILDING/BUILT and
    SUBMITTING/SUBMITTED pairs mirror ``ActionStatus``'s EXECUTING/EXECUTED
    split (section 6): an outbound request is not yet its result.
    """

    DRAFT = "draft"
    CART_BUILDING = "cart_building"
    CART_BUILT = "cart_built"
    CART_FAILED = "cart_failed"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    VERIFIED = "verified"
    FAILED = "failed"
    CANCELLED = "cancelled"


#: A list in one of these states has nothing left to do to it — the same
#: distinction ``TERMINAL_APPOINTMENT_STATUSES`` draws.
TERMINAL_SHOPPING_STATUSES: frozenset[ShoppingListStatus] = frozenset(
    {ShoppingListStatus.VERIFIED, ShoppingListStatus.CANCELLED}
)

_MAX_ITEMS = 60
_MAX_ITEM_NAME = 200


class ShoppingItem(BaseModel):
    """One line of the list. ``substitution_allowed`` defaults true because a
    grocery run that fails outright on the first out-of-stock item is not
    what section 98's "substitutions" step is for; a caller listing an item
    that must ship exactly as named sets it false.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=_MAX_ITEM_NAME)
    quantity: str = Field(default="1", max_length=50)
    notes: str = Field(default="", max_length=300)
    substitution_allowed: bool = True
    #: Filled in only once ``apply_substitution`` has actually acted on this
    #: item — distinct from ``substitution_allowed``, which is permission, not
    #: history.
    substituted_with: str | None = None
    substitution_reason: str | None = None
    estimated_price: str | None = None


class ShoppingList(BaseModel):
    """One grocery run LifeOps is driving (section 98)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    store: str = ""
    task_id: str | None = None
    status: ShoppingListStatus = ShoppingListStatus.DRAFT
    items: list[ShoppingItem] = Field(default_factory=list)

    #: The provider's own identifiers, once the browser worker has acted.
    cart_reference: str | None = None
    order_reference: str | None = None
    #: The Action outbox entries driving this list (section 60) — kept so the
    #: Console can find "what is this list waiting on", and so
    #: ``apply_substitution`` knows which live checkout Action, if any, needs
    #: its payload refreshed.
    cart_action_id: str | None = None
    checkout_action_id: str | None = None
    total_estimate: str | None = None

    created_at: str
    updated_at: str
    created_by_client: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_SHOPPING_STATUSES

    @staticmethod
    def make_id() -> str:
        return new_shopping_list_id()


class ShoppingListDraft(BaseModel):
    """Input shape for opening a new list."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    store: str = Field(default="", max_length=200)
    task_id: str | None = None
    items: list[ShoppingItem] = Field(default_factory=list)


class SubstitutionDraft(BaseModel):
    """Section 98's "substitutions" — applied to one already-listed item by
    name, never by inventing a new line the human never saw."""

    model_config = ConfigDict(extra="forbid")

    item_name: str = Field(min_length=1, max_length=_MAX_ITEM_NAME)
    substituted_with: str = Field(min_length=1, max_length=_MAX_ITEM_NAME)
    reason: str = Field(default="", max_length=300)


class ProductResult(BaseModel):
    """One candidate the browser worker found (section 98's "search/research")."""

    model_config = ConfigDict(extra="forbid")

    name: str
    price: str | None = None
    availability: str | None = None
    url: str | None = None


class CartResult(BaseModel):
    """What the browser worker reports after building a cart."""

    model_config = ConfigDict(extra="forbid")

    cart_reference: str
    total_estimate: str | None = None
    unavailable_items: list[str] = Field(default_factory=list)


class OrderResult(BaseModel):
    """What the browser worker reports after submitting an order."""

    model_config = ConfigDict(extra="forbid")

    order_reference: str
    total: str | None = None


# --- pure rules ---------------------------------------------------------------


def create(draft: ShoppingListDraft, *, now: str, client_id: str) -> ShoppingList:
    if len(draft.items) > _MAX_ITEMS:
        raise ValidationError(
            f"a shopping list may carry at most {_MAX_ITEMS} items", field="items"
        )
    return ShoppingList(
        id=ShoppingList.make_id(),
        title=draft.title.strip(),
        store=draft.store.strip(),
        task_id=draft.task_id,
        items=list(draft.items),
        created_at=now,
        updated_at=now,
        created_by_client=client_id,
    )


def add_items(shopping_list: ShoppingList, items: list[ShoppingItem], *, now: str) -> ShoppingList:
    """Append items to a list still being assembled.

    Refuses once a cart exists: changing the plan after the cart has been
    built is what ``apply_substitution`` is for, not a silent item add that
    the built cart never saw.
    """
    if shopping_list.status is not ShoppingListStatus.DRAFT:
        raise ValidationError(
            f"shopping list {shopping_list.id} is {shopping_list.status}; "
            "items can only be added while it is still a draft",
            shopping_list_id=shopping_list.id,
        )
    combined = [*shopping_list.items, *items]
    if len(combined) > _MAX_ITEMS:
        raise ValidationError(
            f"a shopping list may carry at most {_MAX_ITEMS} items", field="items"
        )
    updated = shopping_list.model_copy(deep=True)
    updated.items = combined
    updated.updated_at = now
    return updated


def apply_substitution(
    shopping_list: ShoppingList, draft: SubstitutionDraft, *, now: str
) -> ShoppingList:
    """Record a substitution against an already-listed item.

    Pure: this only updates the plan. Whether a live checkout Action's
    payload — and therefore its approval binding — must be refreshed is
    decided by the caller, which holds the Action state this module does not.
    """
    matched = False
    updated = shopping_list.model_copy(deep=True)
    for item in updated.items:
        if item.name.strip().lower() == draft.item_name.strip().lower():
            if not item.substitution_allowed:
                raise ValidationError(
                    f"{item.name!r} does not allow substitutions",
                    field="item_name",
                )
            item.substituted_with = draft.substituted_with.strip()
            item.substitution_reason = draft.reason.strip() or None
            matched = True
    if not matched:
        raise NotFoundError(
            f"no item named {draft.item_name!r} on shopping list {shopping_list.id}",
            shopping_list_id=shopping_list.id,
            item_name=draft.item_name,
        )
    updated.updated_at = now
    return updated


def build_cart_payload(shopping_list: ShoppingList) -> dict[str, Any]:
    """The exact request a ``build_grocery_cart`` Action carries (section 58:
    the approval screen shows exactly what will happen — here, nothing needs
    approving, but the shape stays identical to ``checkout_payload`` so one
    executor can read both)."""
    return {
        "shopping_list_id": shopping_list.id,
        "store": shopping_list.store,
        "items": [item.model_dump(mode="json") for item in shopping_list.items],
    }


def checkout_payload(shopping_list: ShoppingList) -> dict[str, Any]:
    """The exact request a ``submit_grocery_order`` Action carries.

    Includes every substitution applied so far, because section 58's approval
    screen must show the human what they are actually authorising — a
    substituted item, not the original one silently swapped after the fact.
    """
    return {
        "shopping_list_id": shopping_list.id,
        "store": shopping_list.store,
        "cart_reference": shopping_list.cart_reference,
        "items": [item.model_dump(mode="json") for item in shopping_list.items],
        "total_estimate": shopping_list.total_estimate,
    }


def mark_cart_building(shopping_list: ShoppingList, *, action_id: str, now: str) -> ShoppingList:
    updated = shopping_list.model_copy(deep=True)
    updated.status = ShoppingListStatus.CART_BUILDING
    updated.cart_action_id = action_id
    updated.updated_at = now
    return updated


def mark_cart_built(
    shopping_list: ShoppingList,
    *,
    cart_reference: str,
    total_estimate: str | None,
    now: str,
) -> ShoppingList:
    updated = shopping_list.model_copy(deep=True)
    updated.status = ShoppingListStatus.CART_BUILT
    updated.cart_reference = cart_reference
    if total_estimate is not None:
        updated.total_estimate = total_estimate
    updated.updated_at = now
    return updated


def mark_cart_failed(shopping_list: ShoppingList, *, now: str) -> ShoppingList:
    updated = shopping_list.model_copy(deep=True)
    updated.status = ShoppingListStatus.CART_FAILED
    updated.updated_at = now
    return updated


def mark_submitting(shopping_list: ShoppingList, *, action_id: str, now: str) -> ShoppingList:
    updated = shopping_list.model_copy(deep=True)
    updated.status = ShoppingListStatus.SUBMITTING
    updated.checkout_action_id = action_id
    updated.updated_at = now
    return updated


def mark_submitted(
    shopping_list: ShoppingList, *, order_reference: str, now: str
) -> ShoppingList:
    updated = shopping_list.model_copy(deep=True)
    updated.status = ShoppingListStatus.SUBMITTED
    updated.order_reference = order_reference
    updated.updated_at = now
    return updated


def mark_verified(shopping_list: ShoppingList, *, now: str) -> ShoppingList:
    updated = shopping_list.model_copy(deep=True)
    updated.status = ShoppingListStatus.VERIFIED
    updated.updated_at = now
    return updated


def mark_failed(shopping_list: ShoppingList, *, now: str) -> ShoppingList:
    updated = shopping_list.model_copy(deep=True)
    updated.status = ShoppingListStatus.FAILED
    updated.updated_at = now
    return updated


def cancel_submission(shopping_list: ShoppingList, *, now: str) -> ShoppingList:
    """Return a SUBMITTING list to CART_BUILT.

    A declined or failed checkout is not the end of the groceries: the cart
    still exists, only the order did not go out. Without this exit,
    SUBMITTING wedged the list forever — every operation refuses a
    SUBMITTING list, and nothing else moved it.
    """
    if shopping_list.status is not ShoppingListStatus.SUBMITTING:
        raise ValidationError(
            f"shopping list {shopping_list.id} is {shopping_list.status}; only "
            "a SUBMITTING list has a submission to cancel",
            shopping_list_id=shopping_list.id,
            status=str(shopping_list.status),
        )
    updated = shopping_list.model_copy(deep=True)
    updated.status = ShoppingListStatus.CART_BUILT
    updated.checkout_action_id = None
    updated.updated_at = now
    return updated


# --- world graph projection ----------------------------------------------------
#
# Same discipline as ``domain/calendar.py``'s ``appointment_to_entity`` /
# ``entity_to_appointment``: facts are flat strings (NornicDB property values
# cannot be maps), ``None`` is omitted rather than written as the literal
# string "None", and items/list fields are JSON-encoded into single facts —
# this bypasses ``validate_facts``' 500-character bound deliberately, the same
# way the Phase 7 flows do, because a real grocery list is exactly the
# structured content that generic bound exists to keep *out* of the bag.

_LIST_SCALAR_FACT_FIELDS: tuple[str, ...] = (
    "store",
    "task_id",
    "status",
    "cart_reference",
    "order_reference",
    "cart_action_id",
    "checkout_action_id",
    "total_estimate",
)


# NOTE: the two converters below are no longer the storage path for
# shopping lists. That moved to a dedicated repository, and the World screen
# projects the real record in Cypher (``repositories/nornic/world.py``).
# They survive because unit tests still exercise the shapes; nothing in
# production calls them.
def shopping_list_to_entity(shopping_list: ShoppingList) -> WorldEntity:
    import json

    facts = {
        field: str(getattr(shopping_list, field))
        for field in _LIST_SCALAR_FACT_FIELDS
        if getattr(shopping_list, field) is not None
    }
    facts["items_json"] = json.dumps(
        [item.model_dump(mode="json") for item in shopping_list.items], sort_keys=True
    )
    return WorldEntity(
        id=shopping_list.id,
        entity_type=WorldEntityType.SHOPPING_LIST,
        display_name=shopping_list.title,
        facts=facts,
        created_at=shopping_list.created_at,
        updated_at=shopping_list.updated_at,
        created_by_client=shopping_list.created_by_client,
    )


def entity_to_shopping_list(entity: WorldEntity) -> ShoppingList:
    """The inverse of ``shopping_list_to_entity``. Raises on a malformed
    entity rather than guessing at a status."""
    import json

    if entity.entity_type is not WorldEntityType.SHOPPING_LIST:
        raise ValidationError(f"{entity.id} is not a shopping list", entity_id=entity.id)
    facts = entity.facts
    items_raw = facts.get("items_json")
    try:
        items = [ShoppingItem(**item) for item in (json.loads(items_raw) if items_raw else [])]
        return ShoppingList(
            id=entity.id,
            title=entity.display_name,
            store=facts.get("store", ""),
            task_id=facts.get("task_id"),
            status=ShoppingListStatus(facts.get("status", ShoppingListStatus.DRAFT)),
            items=items,
            cart_reference=facts.get("cart_reference"),
            order_reference=facts.get("order_reference"),
            cart_action_id=facts.get("cart_action_id"),
            checkout_action_id=facts.get("checkout_action_id"),
            total_estimate=facts.get("total_estimate"),
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            created_by_client=entity.created_by_client,
        )
    except (ValueError, TypeError) as exc:
        raise ValidationError(
            f"shopping list {entity.id} has a malformed fact: {exc}", entity_id=entity.id
        ) from None
