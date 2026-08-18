"""BrowserWorker abstraction (BUILD_SPEC sections 22, 98).

Everything that searches a site, builds a cart, or submits an order goes
through this Protocol, the same discipline ``voice/provider.py`` uses for
TTS/ASR: LifeOps Core, ``ShoppingService``, and the Console never call a
specific browser automation library directly.

Section 98 says "separate browser contexts" — an isolation requirement, not a
suggestion: different sites must not share a context, so a shopping session
cannot read a billing session's cookies. That requirement is stated on every
call here that touches a site (``store`` names the context to use); an
implementation that shared cookies across ``store`` values would violate the
Protocol's contract even though nothing in its Python signature could catch
that mechanically.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lifeops.domain.shopping import CartResult, OrderResult, ProductResult, ShoppingItem


@runtime_checkable
class BrowserWorker(Protocol):
    """One authenticated browsing session driver.

    No ``run_script`` or ``execute_js`` here — same reasoning
    ``mcp/server.py`` gives for refusing ``run_cypher``: a generic browser-
    automation escape hatch cannot carry the outbox's idempotency or the
    approval gate, and LifeOps can (section 7).
    """

    async def health(self) -> tuple[bool, str]:
        """(healthy, message) — never raises for an ordinary unavailability."""
        ...

    async def search(self, query: str, *, store: str = "", limit: int = 10) -> list[ProductResult]:
        """Section 98's "search/research". Read-only: opens a context, looks,
        and reports what it found. Never adds anything to a cart."""
        ...

    async def build_cart(
        self, *, store: str, items: list[ShoppingItem]
    ) -> CartResult:
        """Section 98's "cart building" — reversible, commits nothing
        (BUILD_SPEC section 56: R1). The worker never substitutes on its
        own, whatever ``substitution_allowed`` says: a substitution changes
        what an approval covers, so it travels back via
        ``CartResult.unavailable_items`` and is applied through
        ``apply_substitution``, where section 57's payload binding forces a
        fresh human approval. ``substitution_allowed`` is the *permission*
        that flow checks, not licence for the worker to act alone."""
        ...

    async def submit_order(
        self, *, store: str, cart_reference: str, items: list[ShoppingItem]
    ) -> OrderResult:
        """Section 98's approval-gated checkout (BUILD_SPEC section 56: R3).
        Called only after LifeOps Core has committed a ``submit_grocery_order``
        Action — this method has no notion of approval itself."""
        ...

    async def confirm_cart(self, *, store: str, cart_reference: str) -> tuple[bool, str]:
        """Independently re-check that a cart still exists (BUILD_SPEC section
        6: an accepted request is a claim, not evidence)."""
        ...

    async def confirm_order(self, *, store: str, order_reference: str) -> tuple[bool, str]:
        """Independently re-check that an order was actually placed."""
        ...
