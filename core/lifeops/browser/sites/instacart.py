"""Instacart site adapter (BUILD_SPEC section 98).

Instacart was the retailer the user named, and the reason recorded for
choosing a deterministic per-site adapter over letting a model browse and
check out against raw page content: that shape puts untrusted page text next
to a payment-capable action loop, which is a prompt-injection problem no
amount of prompting fixes.

Read off a live page from the deploying host on 2026-08-19:

    search   https://www.instacart.com/store/s?k=<query> renders 48
             ``a[href*="/products/"]`` anchors without any sign-in. Each
             carries the product name, a "Current price: $x.xx" prefix, and
             a ``retailerSlug`` query parameter naming which store it came
             from.

Unlike Amazon, Instacart has no guest cart: adding anything requires an
account *and* a chosen retailer and postcode. So this adapter is honestly
asymmetric — the read half is real and verified, the write half reports what
it needs instead of guessing. ``search`` alone is still worth having: it is
section 98's "search/research" step, it is the half Hermes can use safely,
and it commits nothing.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import quote_plus

from lifeops.domain.shopping import CartResult, OrderResult, ProductResult, ShoppingItem
from lifeops.errors import ProviderError

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext

_BASE = "https://www.instacart.com"
_SEARCH_URL = _BASE + "/store/s?k={query}"
_PRODUCT_LINK = 'a[href*="/products/"]'

#: Instacart prefixes the accessible label with the price it is rendering,
#: e.g. "Current price: $7.99 $799 Lucerne Whole Milk 128 fl oz". The price
#: is captured from the labelled form; the unlabelled "$799" beside it is a
#: presentational duplicate and is not a real amount.
_PRICE = re.compile(r"Current price:\s*(\$[\d,]+\.\d{2})")
_NOISE = re.compile(
    r"(Best seller|Current price:.*?(?=[A-Z])|Original Price:.*?(?=[A-Z])|\d+% off)"
)

_SIGN_IN_REQUIRED = (
    "Instacart has no guest cart: building or submitting one needs a "
    "signed-in account with a chosen retailer and delivery postcode. "
    "Search works without any of that and is available now."
)


class InstacartSiteAdapter:
    """Instacart storefront search. Read-only until an account exists."""

    store = "instacart"

    async def search(
        self, context: BrowserContext, query: str, *, limit: int = 10
    ) -> list[ProductResult]:
        page = await context.new_page()
        try:
            await page.goto(
                _SEARCH_URL.format(query=quote_plus(query)),
                wait_until="domcontentloaded",
            )
            # The storefront is client-rendered; the anchors do not exist at
            # domcontentloaded. Wait for the first one rather than a fixed
            # sleep, and treat its absence as "no results" — an empty search
            # is a legitimate answer, not a provider failure.
            try:
                await page.wait_for_selector(_PRODUCT_LINK, timeout=20000)
            except Exception:
                return []
            links = page.locator(_PRODUCT_LINK)
            results: list[ProductResult] = []
            seen: set[str] = set()
            for index in range(await links.count()):
                if len(results) >= max(limit, 0):
                    break
                link = links.nth(index)
                href = await link.get_attribute("href") or ""
                if not href or href in seen:
                    # The same product appears in several carousels on one
                    # page; the href is what makes them the same product.
                    continue
                seen.add(href)
                raw = (await link.inner_text()).replace("\n", " ").strip()
                if not raw:
                    continue
                price_match = _PRICE.search(raw)
                name = _NOISE.sub("", raw).strip(" -–—")
                # A stripped-empty label means the anchor was an image tile
                # whose text lives elsewhere; without a name there is no
                # product to report.
                if not name:
                    continue
                results.append(
                    ProductResult(
                        name=name,
                        price=price_match.group(1) if price_match else None,
                        availability=self._retailer_of(href),
                        url=_BASE + href if href.startswith("/") else href,
                    )
                )
            return results
        finally:
            await page.close()

    @staticmethod
    def _retailer_of(href: str) -> str | None:
        """Which store the result came from. Instacart is a marketplace, so
        "in stock" is meaningless without naming whose shelf it is on."""
        match = re.search(r"retailerSlug=([\w-]+)", href)
        return f"from {match.group(1)}" if match else None

    async def build_cart(
        self, context: BrowserContext, items: list[ShoppingItem]
    ) -> CartResult:
        raise ProviderError(_SIGN_IN_REQUIRED, provider="browser")

    async def submit_order(
        self, context: BrowserContext, cart_reference: str, items: list[ShoppingItem]
    ) -> OrderResult:
        raise ProviderError(_SIGN_IN_REQUIRED, provider="browser")

    async def confirm_cart(
        self, context: BrowserContext, cart_reference: str
    ) -> tuple[bool, str]:
        return False, _SIGN_IN_REQUIRED

    async def confirm_order(
        self, context: BrowserContext, order_reference: str
    ) -> tuple[bool, str]:
        return False, _SIGN_IN_REQUIRED
