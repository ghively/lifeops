"""RealBrowserWorker (BUILD_SPEC sections 66, 88, 98).

Playwright is a new dependency; AGENTS.md requires a written justification
before adding one:

    Problem:              browser/real.py raised on every method regardless
                           of whether a runtime was installed, and health()
                           reported "not integrated" even when Chromium was
                           reachable — a real capability reported as absent,
                           which is exactly the dishonesty section 88's
                           never-fake-success rule exists to prevent, just
                           pointed the other direction.
    Existing capability:  none. No code anywhere in this repository can
                           launch or drive a browser; Hermes's own web tools
                           are read-only search/extraction (section 65), not
                           authenticated interaction with a dynamic site.
    Why it is required:   section 98's shopping flow and section 66's
                           "separate persistent browser contexts" both
                           presuppose an actual browser process. Unlike
                           CalDAV or IMAP there is no protocol to speak
                           instead — driving a real site requires a real
                           browser.
    Operational cost:     one Chromium process per call
                           (``BrowserProviderService`` rebuilds the worker on
                           every call, same as every other provider, so
                           config changes take effect without a restart) plus
                           Chromium's own footprint. The binary ships
                           pre-installed in this environment; no download
                           step is added.
    Removal plan:         delete this module and the ``playwright``
                           dependency. ``BrowserWorker`` is a ``Protocol``,
                           so nothing else in the codebase imports Playwright
                           directly — removing this file is the whole
                           removal.

What this makes real: launching Chromium and reporting whether that
genuinely worked (``health()``), and per-context persistent, isolated
browser profiles on disk (``_open_context``) — section 66's "separate
persistent browser contexts" requirement, actually enforced: two different
context names get two different on-disk profile directories that share no
cookies (``tests/unit/test_browser.py`` proves this against a real browser,
not a mock).

What this does NOT make real: searching or checking out on any actual
shopping site. That needs site-specific automation — a login flow, a page
structure, selectors — per retailer, and no retailer is named anywhere in
this codebase. Inventing one here would mean shipping scraping logic never
tested against a live site, for a store nobody chose, which is precisely
the kind of speculative build BUILD_SPEC section 105 warns against. The
five shopping methods below therefore report a specific, honest gap — "no
site adapter for store X" — through ``_SITE_ADAPTERS``, the extension point
a real site integration would register itself into. Nothing else in this
module needs to change to add one.
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lifeops.browser.sites import SITE_ADAPTERS
from lifeops.domain.shopping import CartResult, OrderResult, ProductResult, ShoppingItem
from lifeops.errors import ProviderError

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Playwright


def _default_profile_root() -> Path:
    """Mirrors ``settings._default_state_dir``'s XDG rule without importing
    it: a browser-runtime detail stays independent of the composition root,
    the same way ``RealBrowserWorker`` is built fresh from stored Console
    fields rather than from ``Settings`` (``browser/service.py``)."""
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "lifeops" / "browser-profiles"


#: Playwright resolves its own bundled Chromium build by default, which is
#: right for a normal deployment that ran ``playwright install``. Some
#: environments (this one included) instead pre-install a specific Chromium
#: binary at a fixed path and skip that step; ``PLAYWRIGHT_CHROMIUM_EXECUTABLE``
#: lets an operator point at one explicitly, and the well-known path such
#: environments use is checked as a fallback before deferring to Playwright's
#: own resolution.
_KNOWN_PREINSTALLED_CHROMIUM = Path("/opt/pw-browsers/chromium")


def _local_chromium_executable() -> str | None:
    override = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    if override:
        return override
    if _KNOWN_PREINSTALLED_CHROMIUM.exists():
        return str(_KNOWN_PREINSTALLED_CHROMIUM)
    return None


_UNSAFE_NAME_CHARS = re.compile(r"[^a-z0-9_-]+")


def _profile_dirname(name: str) -> str:
    """A context name (a ``store`` value), made safe as a single path
    segment — never used to build a URL or a shell command, only a
    directory name under ``profile_root``."""
    cleaned = _UNSAFE_NAME_CHARS.sub("-", name.strip().lower()).strip("-")
    return cleaned or "default"


#: Site-specific shopping automation, keyed by ``store``. Empty: no retailer
#: has been chosen yet (see the module docstring's "what this does NOT make
#: real"). Populate this to make ``search``/``build_cart``/``submit_order``
#: work for a real store.
#: Populated from ``browser.sites``. Kept as a module-level name because
#: that is the extension point this module's docstring names and tests
#: monkeypatch; the adapters themselves live one package down so a retailer's
#: page structure never mixes with browser-lifecycle code.
_SITE_ADAPTERS: dict[str, Any] = dict(SITE_ADAPTERS)


class RealBrowserWorker:
    """BUILD_SPEC sections 66, 98 — a real Playwright-driven Chromium,
    constructed fresh from stored Console settings on every call (mirrors
    every other provider, e.g. ``ElevenLabsTTSProvider``), so a changed
    endpoint, headless mode, or timeout takes effect without a restart.

    Cross-call persistence therefore has to live on disk, not on this
    instance: each context gets its own profile directory under
    ``profile_root``, and Playwright's ``launch_persistent_context`` reloads
    whatever cookies and local storage a previous call left there. Two
    different context names never share a directory — the isolation section
    66 asks for.
    """

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        headless: bool = True,
        timeout_s: float = 30.0,
        profile_root: Path | None = None,
    ) -> None:
        self._endpoint = endpoint or None
        self._headless = headless
        self._timeout_s = timeout_s
        self._profile_root = profile_root or _default_profile_root()

    async def health(self) -> tuple[bool, str]:
        """Actually launches Chromium (or connects to the configured remote
        endpoint) and closes it again — the genuine check section 88 asks
        for, not a runtime-importability guess. Never raises: any failure is
        reported through the return tuple, matching the Protocol."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return False, (
                "the playwright package is not installed in this "
                "environment (pip install playwright)"
            )
        try:
            async with async_playwright() as playwright:
                browser = await self._launch(playwright)
                await browser.close()
        except Exception as exc:  # noqa: BLE001 - reporting the failure, not handling it
            return False, f"chromium could not be launched: {exc}"
        if self._endpoint:
            return True, f"connected to the browser at {self._endpoint}"
        return True, "chromium launched successfully"

    async def _launch(self, playwright: Playwright) -> Browser:
        if self._endpoint:
            return await playwright.chromium.connect_over_cdp(self._endpoint)
        return await playwright.chromium.launch(
            headless=self._headless, executable_path=_local_chromium_executable()
        )

    async def _open_context(self, playwright: Playwright, name: str) -> BrowserContext:
        """A persistent, isolated context for ``name`` (a ``store`` value).

        A local launch gets an on-disk profile directory unique to ``name``,
        so cookies and login state persist between calls without this
        Python object staying alive. A remote CDP endpoint gets a fresh
        in-memory context per call instead — profile persistence for a
        remote browser is that server's responsibility, not this adapter's.
        """
        if self._endpoint:
            browser = await playwright.chromium.connect_over_cdp(self._endpoint)
            context = await browser.new_context()
            # The CDP connection outlives the context unless something drops
            # it — this branch used to connect a browser it never closed, a
            # pre-planted leak for the first site adapter (2026-08-18 audit,
            # P2). Closing the context is the caller's contract; the browser
            # connection rides along with it.
            context.on(
                "close",
                lambda _context: asyncio.get_running_loop().create_task(
                    browser.close()
                ),
            )
        else:
            profile_dir = self._profile_root / _profile_dirname(name)
            profile_dir.mkdir(parents=True, exist_ok=True)
            context = await playwright.chromium.launch_persistent_context(
                str(profile_dir),
                headless=self._headless,
                executable_path=_local_chromium_executable(),
            )
        context.set_default_timeout(self._timeout_s * 1000)
        return context

    def _session(self, store: str) -> _BrowserSession:
        """Playwright + one isolated per-store context, closed on exit.

        Every shopping method needs the identical three-step dance, and each
        step has a failure mode that leaks a Chromium process if the next one
        raises. Writing it once means an adapter that throws mid-cart still
        tears the browser down.
        """
        return _BrowserSession(self, store)

    def _no_site_adapter_error(self, store: str) -> ProviderError:
        return ProviderError(
            f"no site automation is configured for store {store!r} — LifeOps "
            "has a real browser runtime now, but no site-specific adapter "
            "for this store yet (see browser/real.py's _SITE_ADAPTERS)",
            provider="browser",
        )

    def _no_site_adapter_message(self, store: str) -> str:
        return (
            f"no site automation is configured for store {store!r} — nothing "
            "to confirm against"
        )

    async def search(
        self, query: str, *, store: str = "", limit: int = 10
    ) -> list[ProductResult]:
        if store not in _SITE_ADAPTERS:
            raise self._no_site_adapter_error(store)
        async with self._session(store) as context:
            return await _SITE_ADAPTERS[store].search(context, query, limit=limit)

    async def build_cart(self, *, store: str, items: list[ShoppingItem]) -> CartResult:
        if store not in _SITE_ADAPTERS:
            raise self._no_site_adapter_error(store)
        async with self._session(store) as context:
            return await _SITE_ADAPTERS[store].build_cart(context, items)

    async def submit_order(
        self, *, store: str, cart_reference: str, items: list[ShoppingItem]
    ) -> OrderResult:
        if store not in _SITE_ADAPTERS:
            raise self._no_site_adapter_error(store)
        async with self._session(store) as context:
            return await _SITE_ADAPTERS[store].submit_order(context, cart_reference, items)

    async def confirm_cart(self, *, store: str, cart_reference: str) -> tuple[bool, str]:
        if store not in _SITE_ADAPTERS:
            return False, self._no_site_adapter_message(store)
        async with self._session(store) as context:
            return await _SITE_ADAPTERS[store].confirm_cart(context, cart_reference)

    async def confirm_order(self, *, store: str, order_reference: str) -> tuple[bool, str]:
        if store not in _SITE_ADAPTERS:
            return False, self._no_site_adapter_message(store)
        async with self._session(store) as context:
            return await _SITE_ADAPTERS[store].confirm_order(context, order_reference)


class _BrowserSession:
    """Async context manager yielding an isolated context for one store.

    ``async_playwright()`` is itself a context manager whose lifetime must
    outlive the browser it started, so both are entered here and exited in
    reverse — closing the context (which, on the CDP path, drags the browser
    connection with it via the ``close`` handler in ``_open_context``) before
    stopping Playwright.
    """

    def __init__(self, worker: RealBrowserWorker, store: str) -> None:
        self._worker = worker
        self._store = store
        self._playwright_cm: Any = None
        self._context: Any = None

    async def __aenter__(self) -> Any:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise ProviderError(
                "the playwright package is not installed in this environment "
                "(pip install playwright)",
                provider="browser",
            ) from exc
        self._playwright_cm = async_playwright()
        playwright = await self._playwright_cm.__aenter__()
        try:
            self._context = await self._worker._open_context(playwright, self._store)
        except Exception as exc:
            await self._playwright_cm.__aexit__(type(exc), exc, exc.__traceback__)
            raise ProviderError(
                f"chromium could not be started for store {self._store!r}: {exc}",
                provider="browser",
            ) from exc
        return self._context

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        try:
            if self._context is not None:
                await self._context.close()
        finally:
            if self._playwright_cm is not None:
                await self._playwright_cm.__aexit__(exc_type, exc, tb)
