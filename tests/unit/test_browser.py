"""RealBrowserWorker (BUILD_SPEC sections 66, 88, 98).

Two kinds of assertion here: pure, always-run checks of the sanitisation and
"no site adapter" honesty logic (no browser needed), and genuine end-to-end
checks against a real Chromium — health() actually launching, and two
different contexts genuinely not sharing cookies (section 66's isolation
requirement). The latter group skips cleanly if Playwright/Chromium is not
available in the environment running the suite, rather than mocking around
it — a mock would prove nothing about whether the adapter actually works.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from lifeops.browser.real import (
    RealBrowserWorker,
    _local_chromium_executable,
    _profile_dirname,
)
from lifeops.domain.shopping import ShoppingItem
from lifeops.errors import ProviderError


def _playwright_available() -> bool:
    try:
        import playwright.async_api  # noqa: F401
    except ImportError:
        return False
    return True


requires_playwright = pytest.mark.skipif(
    not _playwright_available(), reason="playwright is not installed in this environment"
)


class TestProfileDirname:
    def test_sanitises_unsafe_characters(self) -> None:
        assert _profile_dirname("Kroger.com/store?1") == "kroger-com-store-1"

    def test_empty_name_falls_back_to_default(self) -> None:
        assert _profile_dirname("   ") == "default"

    def test_is_never_a_path_traversal(self) -> None:
        assert "/" not in _profile_dirname("../../etc/passwd")
        assert ".." not in _profile_dirname("../../etc/passwd")


class TestLocalChromiumExecutable:
    def test_env_override_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "/custom/chrome")
        assert _local_chromium_executable() == "/custom/chrome"

    def test_falls_back_to_none_when_nothing_is_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE", raising=False)
        monkeypatch.setattr(
            "lifeops.browser.real._KNOWN_PREINSTALLED_CHROMIUM", Path("/nope/does-not-exist")
        )
        assert _local_chromium_executable() is None


class TestHealthWithoutPlaywrightInstalled:
    async def test_reports_honestly_when_the_import_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import builtins

        real_import = builtins.__import__

        def _fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "playwright.async_api":
                raise ImportError("no module named playwright")
            return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(builtins, "__import__", _fake_import)
        healthy, message = await RealBrowserWorker().health()
        assert healthy is False
        assert "not installed" in message


@requires_playwright
class TestHealthAgainstARealBrowser:
    async def test_reports_healthy_when_chromium_actually_launches(self) -> None:
        healthy, message = await RealBrowserWorker().health()
        assert healthy is True
        assert "launched" in message

    async def test_reports_unhealthy_honestly_when_launch_fails(self) -> None:
        worker = RealBrowserWorker()
        # An executable that cannot possibly exist — the launch must fail,
        # and health() must report that rather than raising.
        worker._launch = _always_fail  # type: ignore[method-assign]
        healthy, message = await worker.health()
        assert healthy is False
        assert message


async def _always_fail(playwright: object) -> object:
    raise RuntimeError("simulated launch failure")


@requires_playwright
class TestContextIsolation:
    """BUILD_SPEC section 66: "separate persistent browser contexts" — two
    different context names must never share cookies. Proven here against a
    real Chromium, not asserted about a mock's internal bookkeeping."""

    async def test_two_contexts_do_not_share_cookies(self) -> None:
        from playwright.async_api import async_playwright

        with tempfile.TemporaryDirectory() as tmp:
            worker = RealBrowserWorker(profile_root=Path(tmp))
            async with async_playwright() as playwright:
                context_a = await worker._open_context(playwright, "kroger")
                context_b = await worker._open_context(playwright, "walmart")
                try:
                    await context_a.add_cookies(
                        [{"name": "session", "value": "kroger-only", "url": "http://example.com"}]
                    )
                    cookies_a = await context_a.cookies("http://example.com")
                    cookies_b = await context_b.cookies("http://example.com")
                    assert [c["name"] for c in cookies_a] == ["session"]
                    assert cookies_b == []
                finally:
                    await context_a.close()
                    await context_b.close()

    async def test_context_names_land_in_distinct_profile_directories(self) -> None:
        from playwright.async_api import async_playwright

        with tempfile.TemporaryDirectory() as tmp:
            profile_root = Path(tmp)
            worker = RealBrowserWorker(profile_root=profile_root)
            async with async_playwright() as playwright:
                context_a = await worker._open_context(playwright, "kroger")
                context_b = await worker._open_context(playwright, "walmart")
                await context_a.close()
                await context_b.close()
            assert sorted(p.name for p in profile_root.iterdir()) == ["kroger", "walmart"]


class TestNoSiteAdapterConfigured:
    """No retailer is wired up yet (see the module docstring) — every
    shopping method must say so specifically, not fail generically."""

    async def test_search_raises_a_specific_provider_error(self) -> None:
        with pytest.raises(ProviderError, match="no site automation is configured"):
            await RealBrowserWorker().search("milk", store="kroger")

    async def test_build_cart_raises_a_specific_provider_error(self) -> None:
        with pytest.raises(ProviderError, match="kroger"):
            await RealBrowserWorker().build_cart(
                store="kroger", items=[ShoppingItem(name="milk")]
            )

    async def test_submit_order_raises_a_specific_provider_error(self) -> None:
        with pytest.raises(ProviderError, match="kroger"):
            await RealBrowserWorker().submit_order(
                store="kroger", cart_reference="cart-1", items=[ShoppingItem(name="milk")]
            )

    async def test_confirm_cart_returns_false_rather_than_raising(self) -> None:
        ok, message = await RealBrowserWorker().confirm_cart(
            store="kroger", cart_reference="cart-1"
        )
        assert ok is False
        assert "kroger" in message

    async def test_confirm_order_returns_false_rather_than_raising(self) -> None:
        ok, message = await RealBrowserWorker().confirm_order(
            store="kroger", order_reference="order-1"
        )
        assert ok is False
        assert "kroger" in message
