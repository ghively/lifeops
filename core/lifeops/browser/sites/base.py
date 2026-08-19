"""The site-adapter contract (BUILD_SPEC section 98).

``BrowserWorker`` is the abstraction LifeOps Core talks to; a ``SiteAdapter``
is one retailer's half of it. ``RealBrowserWorker`` owns the browser — launch,
per-store persistent profile, isolation — and an adapter owns nothing but
knowledge of one site's pages. It is handed an open, already-isolated
``BrowserContext`` and never creates or closes one.

That split is deliberate. Section 66's isolation requirement ("a shopping
session cannot read a billing session's cookies") is enforced once, in the
worker, rather than re-argued in every adapter — an adapter physically
cannot reach another store's profile because it is never given a handle to
one.

Two rules every adapter here follows, both from the Protocol in
``browser/provider.py`` rather than from anything site-specific:

*Never substitute.* An out-of-stock item comes back in
``CartResult.unavailable_items`` and is resolved through
``apply_substitution``, where section 57's payload binding forces a fresh
human approval. An adapter that quietly bought the nearest equivalent would
be changing what a human approved, after they approved it.

*Never claim what was not observed.* A method reports what the page actually
showed. Where a site cannot be driven without credentials this repository
does not have, the adapter raises a specific error naming what is missing —
it does not guess at selectors it has never run. That is the standard the
module docstring in ``browser/real.py`` sets, and unverified checkout
automation next to a payment-capable action loop is the worst possible place
to lower it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from lifeops.domain.shopping import CartResult, OrderResult, ProductResult, ShoppingItem

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext


@runtime_checkable
class SiteAdapter(Protocol):
    """One retailer's automation, driven inside a context the worker owns."""

    #: The ``store`` value this adapter answers to. It is also the profile
    #: directory name, so two adapters must never share one.
    store: str

    async def search(
        self, context: BrowserContext, query: str, *, limit: int = 10
    ) -> list[ProductResult]:
        """Read-only. Opens a page, looks, adds nothing to any cart."""
        ...

    async def build_cart(
        self, context: BrowserContext, items: list[ShoppingItem]
    ) -> CartResult:
        """Reversible (section 56: R1). Commits nothing and pays nothing."""
        ...

    async def submit_order(
        self, context: BrowserContext, cart_reference: str, items: list[ShoppingItem]
    ) -> OrderResult:
        """Approval-gated checkout (R3). Called only after LifeOps Core has
        committed the Action — an adapter has no notion of approval itself."""
        ...

    async def confirm_cart(
        self, context: BrowserContext, cart_reference: str
    ) -> tuple[bool, str]:
        """Re-read the cart from the site (section 6: an accepted request is
        a claim, not evidence)."""
        ...

    async def confirm_order(
        self, context: BrowserContext, order_reference: str
    ) -> tuple[bool, str]:
        """Re-read the order from the site."""
        ...
