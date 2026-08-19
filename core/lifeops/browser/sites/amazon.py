"""Amazon site adapter (BUILD_SPEC section 98).

Every selector below was read off a live page from the deploying host on
2026-08-19 and is recorded here with what it returned, so a future failure
reads as "the site changed" rather than "was this ever true?":

    search       div[data-component-type="s-search-result"]   48 cards for
                 "paper towels"; data-asin carries the product id, h2 the
                 title, span.a-price span.a-offscreen the price
    cart add     #add-to-cart-button on /dp/<ASIN>            present, and a
                 click took #nav-cart-count from 0 to 1 with no account
    cart read    #sc-subtotal-amount-activecart               "EUR 6.02"

Amazon's guest cart is why ``build_cart`` is real here. Adding to a cart
needs no sign-in, so the whole reversible half of section 98 — search, cart,
re-confirm — is genuinely exercisable and was exercised. Checkout is not:
see ``submit_order``.

**Locale.** Amazon serves currency and availability by the *browser's*
apparent location, not by any setting here — from a datacenter host it may
answer in EUR even on amazon.com. Prices are therefore passed through
verbatim as the site rendered them, symbol included, and never parsed into
a number. ``validate_amount`` exists precisely because a mis-parsed price is
worse than an unparsed one, and nothing downstream should infer a currency
this adapter did not see.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from lifeops.domain.shopping import CartResult, OrderResult, ProductResult, ShoppingItem
from lifeops.errors import ProviderError

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page

_BASE = "https://www.amazon.com"
_SEARCH_URL = _BASE + "/s?k={query}"
_PRODUCT_URL = _BASE + "/dp/{asin}"
_CART_URL = _BASE + "/gp/cart/view.html"

_RESULT_CARD = 'div[data-component-type="s-search-result"]'
_PRICE = "span.a-price span.a-offscreen"
_ADD_TO_CART = "#add-to-cart-button"
_CART_COUNT = "#nav-cart-count"
_CART_SUBTOTAL = "#sc-subtotal-amount-activecart"

#: Amazon's own product identifier. Used as the cart reference because it is
#: the only durable handle a guest session has — a guest cart lives in a
#: cookie and has no server-side id to quote back.
_ASIN = re.compile(r"^[A-Z0-9]{10}$")


async def _text(scope: object, selector: str) -> str | None:
    """First match's text, or None. Playwright raises on an empty locator;
    a missing optional field is not an error, so it is asked for by count."""
    locator = scope.locator(selector).first  # type: ignore[attr-defined]
    if await locator.count() == 0:
        return None
    value = (await locator.inner_text()).strip()
    return value or None


class AmazonSiteAdapter:
    """Amazon.com, driven as a guest unless the store profile is signed in."""

    store = "amazon"

    async def search(
        self, context: BrowserContext, query: str, *, limit: int = 10
    ) -> list[ProductResult]:
        page = await context.new_page()
        try:
            await page.goto(
                _SEARCH_URL.format(query=query.replace(" ", "+")),
                wait_until="domcontentloaded",
            )
            # Amazon renders results server-side, but sponsored rails and
            # lazy images keep mutating the DOM afterwards. Waiting for the
            # first card is enough and avoids networkidle, which on this page
            # effectively never fires.
            try:
                await page.wait_for_selector(_RESULT_CARD, timeout=15000)
            except Exception:
                return []
            cards = page.locator(_RESULT_CARD)
            results: list[ProductResult] = []
            for index in range(min(await cards.count(), max(limit, 0))):
                card = cards.nth(index)
                name = await _text(card, "h2")
                if not name:
                    # A card with no title is a rail or an ad slot, not a
                    # product. Skipping beats emitting a nameless result.
                    continue
                asin = await card.get_attribute("data-asin")
                results.append(
                    ProductResult(
                        name=name,
                        price=await _text(card, _PRICE),
                        availability=await _text(card, "span.a-color-price"),
                        url=_PRODUCT_URL.format(asin=asin) if asin else None,
                    )
                )
            return results
        finally:
            await page.close()

    async def build_cart(
        self, context: BrowserContext, items: list[ShoppingItem]
    ) -> CartResult:
        """Search each item, add the first real match, report what missed.

        The first search hit is taken deliberately rather than "the best"
        one: ranking a substitute is a judgement that belongs to the human
        the approval gate exists for. An item that yields nothing comes back
        in ``unavailable_items`` untouched — this adapter never swaps one
        product for another, whatever ``substitution_allowed`` says.
        """
        page = await context.new_page()
        unavailable: list[str] = []
        added = 0
        try:
            for item in items:
                asin = await self._first_asin(page, item.name)
                if asin is None:
                    unavailable.append(item.name)
                    continue
                if await self._add_to_cart(page, asin):
                    added += 1
                else:
                    unavailable.append(item.name)
            if added == 0:
                raise ProviderError(
                    "nothing could be added to the Amazon cart"
                    + (f" — no result for: {', '.join(unavailable)}" if unavailable else ""),
                    provider="browser",
                )
            subtotal, count = await self._read_cart(page)
            return CartResult(
                # A guest cart has no server-side identifier, so the count is
                # the only thing that can be re-checked later. It is labelled
                # rather than dressed up as an id it is not.
                cart_reference=f"amazon-cart:{count}",
                total_estimate=subtotal,
                unavailable_items=unavailable,
            )
        finally:
            await page.close()

    async def _first_asin(self, page: Page, query: str) -> str | None:
        await page.goto(
            _SEARCH_URL.format(query=query.replace(" ", "+")),
            wait_until="domcontentloaded",
        )
        try:
            await page.wait_for_selector(_RESULT_CARD, timeout=15000)
        except Exception:
            return None
        cards = page.locator(_RESULT_CARD)
        for index in range(min(await cards.count(), 5)):
            asin = await cards.nth(index).get_attribute("data-asin")
            if asin and _ASIN.match(asin):
                return asin
        return None

    async def _add_to_cart(self, page: Page, asin: str) -> bool:
        await page.goto(_PRODUCT_URL.format(asin=asin), wait_until="domcontentloaded")
        button = page.locator(_ADD_TO_CART)
        if await button.count() == 0:
            # No buy box: the listing exists but nothing is sellable on it
            # right now. That is an unavailable item, not a failure.
            return False
        await button.first.click()
        await page.wait_for_load_state("domcontentloaded")
        return True

    async def _read_cart(self, page: Page) -> tuple[str | None, str]:
        await page.goto(_CART_URL, wait_until="domcontentloaded")
        subtotal = await _text(page, _CART_SUBTOTAL)
        count = await _text(page, _CART_COUNT)
        return subtotal, (count or "0")

    async def confirm_cart(
        self, context: BrowserContext, cart_reference: str
    ) -> tuple[bool, str]:
        """Re-read the cart from Amazon rather than trusting what
        ``build_cart`` returned (section 6)."""
        page = await context.new_page()
        try:
            subtotal, count = await self._read_cart(page)
            if count in ("", "0"):
                return False, "the Amazon cart is empty"
            return True, f"{count} item(s) in the Amazon cart, subtotal {subtotal or 'unknown'}"
        finally:
            await page.close()

    async def submit_order(
        self, context: BrowserContext, cart_reference: str, items: list[ShoppingItem]
    ) -> OrderResult:
        """Not implemented, on purpose — and this is the honest kind of gap.

        Checkout needs a signed-in Amazon session with an address and a
        payment method. This repository holds no such credential and will
        never prompt for one (CLAUDE.md rule 3), so the sequence from
        "Proceed to checkout" to "Place your order" has never been run here.

        Writing those selectors from documentation, next to an action that
        spends money, is exactly the speculative build BUILD_SPEC section 105
        forbids and this module's own docstring warns against. The failure
        mode is not a broken test — it is a wrong order placed with real
        money, discovered afterwards.

        What closes it: sign this store's persistent profile in once (the
        profile at ``profile_root/amazon`` survives between calls, which is
        what section 66's persistence is for), then verify the flow against
        a real basket before it is trusted with one.
        """
        raise ProviderError(
            "Amazon checkout is not automated: it needs a signed-in session "
            "with an address and payment method, and the checkout flow has "
            "never been verified against a live account from here. The cart "
            "is built and can be reviewed and submitted by hand.",
            provider="browser",
        )

    async def confirm_order(
        self, context: BrowserContext, order_reference: str
    ) -> tuple[bool, str]:
        """Order history is behind the same sign-in ``submit_order`` needs.
        Reporting "unconfirmed" is the truthful answer; returning True
        because nothing contradicted it would be the dangerous one."""
        return False, (
            "Amazon order history requires a signed-in session — this order "
            "cannot be independently confirmed from here"
        )
