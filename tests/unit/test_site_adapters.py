"""Site adapters for Amazon and Instacart (BUILD_SPEC section 98).

Three kinds of assertion, deliberately separated:

*Pure.* Registration, and the label parsing Instacart needs — no browser, no
network, always run.

*Honest-gap.* The methods that refuse rather than guess. These matter more
than usual: the gap they encode is "we will not automate a checkout we have
never run", and a future change that quietly fills one in with speculative
selectors should break a test rather than ship money-spending code.

*Live.* Real searches against the real sites, behind ``LIFEOPS_LIVE_SITE_TESTS=1``.
They are opt-in because a unit suite that reaches the public internet fails
for reasons that have nothing to do with the change under test — and because
these two sites answer a datacenter address differently from a home one. The
selectors they cover were verified by hand on 2026-08-19; this is how that
verification gets repeated when a site changes.
"""

from __future__ import annotations

import os

import pytest

from lifeops.browser.real import _SITE_ADAPTERS
from lifeops.browser.sites import SITE_ADAPTERS, AmazonSiteAdapter, InstacartSiteAdapter
from lifeops.browser.sites.base import SiteAdapter
from lifeops.browser.sites.instacart import _NOISE, _PRICE
from lifeops.domain.shopping import ShoppingItem
from lifeops.errors import ProviderError

_LIVE = os.environ.get("LIFEOPS_LIVE_SITE_TESTS") == "1"
_live_only = pytest.mark.skipif(
    not _LIVE, reason="set LIFEOPS_LIVE_SITE_TESTS=1 to run tests that hit the real sites"
)


class TestRegistration:
    def test_both_retailers_are_registered(self) -> None:
        assert set(SITE_ADAPTERS) == {"amazon", "instacart"}

    def test_the_worker_sees_them(self) -> None:
        """``real.py`` copies the registry at import; the copy must not drift."""
        assert set(_SITE_ADAPTERS) == set(SITE_ADAPTERS)

    def test_each_satisfies_the_protocol(self) -> None:
        for adapter in SITE_ADAPTERS.values():
            assert isinstance(adapter, SiteAdapter)

    def test_a_store_key_matches_its_adapter(self) -> None:
        """The key is also the on-disk profile directory name, so a mismatch
        would isolate a store from its own cookies."""
        for key, adapter in SITE_ADAPTERS.items():
            assert adapter.store == key


class TestInstacartLabelParsing:
    """Instacart packs price, badges, and name into one accessible label."""

    def test_extracts_the_labelled_price(self) -> None:
        raw = "Best seller Current price: $7.99 $799 Lucerne Whole Milk 128 fl oz"
        assert _PRICE.search(raw).group(1) == "$7.99"

    def test_strips_badges_and_duplicated_price_text(self) -> None:
        raw = "Best seller Current price: $7.99 $799 Lucerne Whole Milk 128 fl oz"
        assert _NOISE.sub("", raw).strip(" -–—").startswith("Lucerne Whole Milk")

    def test_handles_a_discounted_label(self) -> None:
        raw = (
            "Current price: $6.99 $699 Original Price: $7.99  $7.99  13% off "
            "Clover Sonoma Organic Whole Milk"
        )
        assert _PRICE.search(raw).group(1) == "$6.99"
        assert "Clover Sonoma" in _NOISE.sub("", raw)

    def test_a_label_with_no_price_yields_none(self) -> None:
        assert _PRICE.search("Lucerne Whole Milk 128 fl oz") is None

    def test_retailer_is_read_from_the_href(self) -> None:
        adapter = InstacartSiteAdapter()
        assert adapter._retailer_of("/products/7079-milk?retailerSlug=safeway") == "from safeway"
        assert adapter._retailer_of("/products/7079-milk") is None


class TestHonestGaps:
    """What these adapters refuse to do, and why the refusal is the feature.

    None of these touch a browser: each refuses before it would need one,
    so the refusal cannot be an accident of an unavailable runtime.
    """

    async def test_amazon_will_not_check_out(self) -> None:
        with pytest.raises(ProviderError, match="signed-in session"):
            await AmazonSiteAdapter().submit_order(
                None, "amazon-cart:1", [ShoppingItem(name="milk")]
            )

    async def test_amazon_will_not_claim_an_unverifiable_order(self) -> None:
        ok, message = await AmazonSiteAdapter().confirm_order(None, "order-1")
        assert ok is False
        assert "signed-in session" in message

    async def test_instacart_says_it_has_no_guest_cart(self) -> None:
        with pytest.raises(ProviderError, match="no guest cart"):
            await InstacartSiteAdapter().build_cart(None, [ShoppingItem(name="milk")])

    async def test_instacart_will_not_check_out(self) -> None:
        with pytest.raises(ProviderError, match="signed-in account"):
            await InstacartSiteAdapter().submit_order(
                None, "cart-1", [ShoppingItem(name="milk")]
            )

    async def test_instacart_confirmations_report_rather_than_raise(self) -> None:
        for ok, message in (
            await InstacartSiteAdapter().confirm_cart(None, "cart-1"),
            await InstacartSiteAdapter().confirm_order(None, "order-1"),
        ):
            assert ok is False
            assert "signed-in account" in message


@_live_only
class TestAgainstTheRealSites:
    """Opt-in. Proves the recorded selectors still match what ships."""

    async def _worker(self):
        import tempfile
        from pathlib import Path

        from lifeops.browser.real import RealBrowserWorker

        return RealBrowserWorker(
            headless=True, timeout_s=45.0, profile_root=Path(tempfile.mkdtemp())
        )

    async def test_amazon_search_returns_named_priced_results(self) -> None:
        results = await (await self._worker()).search("paper towels", store="amazon", limit=3)
        assert results, "Amazon returned no results — the result-card selector likely changed"
        assert all(r.name for r in results)
        assert any(r.price for r in results)
        assert all(r.url and "/dp/" in r.url for r in results if r.url)

    async def test_instacart_search_returns_named_results(self) -> None:
        results = await (await self._worker()).search("milk", store="instacart", limit=3)
        assert results, "Instacart returned no results — the product-link selector likely changed"
        assert all(r.name for r in results)
        # A price is not guaranteed for every tile, but a page where none of
        # them carries one means the label format moved.
        assert any(r.price for r in results)

    async def test_amazon_cart_round_trips_through_a_fresh_browser(self) -> None:
        """Section 66's persistence, exercised for real: the cart is built in
        one browser and re-read by another, sharing only the on-disk profile."""
        worker = await self._worker()
        cart = await worker.build_cart(store="amazon", items=[ShoppingItem(name="paper towels")])
        assert cart.cart_reference.startswith("amazon-cart:")
        ok, message = await worker.confirm_cart(
            store="amazon", cart_reference=cart.cart_reference
        )
        assert ok is True
        assert "Amazon cart" in message
