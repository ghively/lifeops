"""FakeBrowser — deterministic in-memory browser worker for tests
(BUILD_SPEC sections 88, 98).

Development and CI use this and nothing else (AGENTS.md, section 88): no test
ever launches a real browser. It is not offered as a selectable provider — a
user cannot "configure" their way into using it — it exists purely for test
wiring, the same role ``calendar/fake.py`` and ``voice/fake.py`` play for
their categories.

Each ``store`` gets its own cart/order counters and item sets, modelling
section 98's "separate browser contexts" at the level this fake can actually
verify: a cart built for one store is never visible to another.
"""

from __future__ import annotations

import itertools

from lifeops.domain.shopping import CartResult, OrderResult, ProductResult, ShoppingItem
from lifeops.errors import NotFoundError


class FakeBrowser:
    """In-memory browser worker. Every item not explicitly marked
    unavailable is treated as in stock."""

    def __init__(self) -> None:
        self.healthy = True
        self._counter = itertools.count(1)
        self._unavailable_names: set[str] = set()
        #: store -> cart_reference -> items
        self._carts: dict[str, dict[str, list[ShoppingItem]]] = {}
        #: store -> order_reference -> cart_reference
        self._orders: dict[str, dict[str, str]] = {}

    def mark_unavailable(self, item_name: str) -> None:
        """Test hook: make ``build_cart`` report an item as needing a
        substitution rather than silently satisfying it."""
        self._unavailable_names.add(item_name.strip().lower())

    async def health(self) -> tuple[bool, str]:
        return self.healthy, "fake browser worker" if self.healthy else "forced unhealthy"

    async def search(
        self, query: str, *, store: str = "", limit: int = 10
    ) -> list[ProductResult]:
        return [
            ProductResult(name=f"{query} (result {i})", price="4.99", availability="in_stock")
            for i in range(1, min(limit, 3) + 1)
        ]

    async def build_cart(self, *, store: str, items: list[ShoppingItem]) -> CartResult:
        cart_reference = f"cart-{next(self._counter)}"
        unavailable = [
            item.name for item in items if item.name.strip().lower() in self._unavailable_names
        ]
        self._carts.setdefault(store, {})[cart_reference] = list(items)
        return CartResult(
            cart_reference=cart_reference,
            total_estimate=f"{len(items) * 4.99:.2f}",
            unavailable_items=unavailable,
        )

    async def submit_order(
        self, *, store: str, cart_reference: str, items: list[ShoppingItem]
    ) -> OrderResult:
        if cart_reference not in self._carts.get(store, {}):
            raise NotFoundError(
                f"no such cart at {store!r}: {cart_reference}",
                store=store,
                cart_reference=cart_reference,
            )
        order_reference = f"order-{next(self._counter)}"
        self._orders.setdefault(store, {})[order_reference] = cart_reference
        return OrderResult(order_reference=order_reference, total=f"{len(items) * 4.99:.2f}")

    async def confirm_cart(self, *, store: str, cart_reference: str) -> tuple[bool, str]:
        if cart_reference in self._carts.get(store, {}):
            return True, f"confirmed cart at {store}: {cart_reference}"
        return False, f"no cart {cart_reference!r} found at {store}"

    async def confirm_order(self, *, store: str, order_reference: str) -> tuple[bool, str]:
        if order_reference in self._orders.get(store, {}):
            return True, f"confirmed order at {store}: {order_reference}"
        return False, f"no order {order_reference!r} found at {store}"
