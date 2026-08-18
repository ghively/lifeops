"""RealBrowserWorker (BUILD_SPEC sections 88, 98).

This exists so the ``BrowserWorker`` abstraction has a real-adapter shape to
select once a browser runtime is installed — not to ship a working automated
browser. AGENTS.md requires a written justification for any new dependency,
and a browser automation runtime (playwright, selenium, puppeteer) is exactly
the kind of large, speculative install BUILD_SPEC section 105 forbids adding
before a concrete need calls for it; this codebase adds none of them.

Instead this adapter *detects* whether a runtime it could call is importable
and reports the honest result through ``health()`` — "not installed" when it
genuinely is not — exactly the pattern ``voice/local.py`` established for the
local speech runtimes. Every other method never fabricates a result: it raises
with that same message, exactly as ``api/http.py``'s ``test_provider`` already
does for every provider that has no adapter (BUILD_SPEC section 88 — never
fake success).

No browser is ever launched here. Endpoint, headless mode, and navigation
timeout are Console fields (``config/provider_registry.py``'s ``browser``
provider); this module only decides whether it could possibly use whatever
the user configures.
"""

from __future__ import annotations

from lifeops.domain.shopping import CartResult, OrderResult, ProductResult, ShoppingItem
from lifeops.errors import ProviderError
from lifeops.runtime import detect_runtime

#: Real, commonly installed package names a browser-automation adapter could
#: eventually be written against. Detecting them is useful even though no
#: adapter exists yet — same reasoning as ``voice/local.py``'s
#: ``ASR_RUNTIME_CANDIDATES``.
BROWSER_RUNTIME_CANDIDATES: tuple[str, ...] = ("playwright", "selenium")



class RealBrowserWorker:
    """BUILD_SPEC section 98 — authenticated browsing for sites without a
    usable API. Constructed fresh from stored Console settings, like
    ``ElevenLabsTTSProvider``, so a changed endpoint or timeout takes effect
    on the next call without a process restart.
    """

    _RUNTIME_CANDIDATES = BROWSER_RUNTIME_CANDIDATES

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        headless: bool = True,
        timeout_s: float = 30.0,
    ) -> None:
        self._endpoint = endpoint
        self._headless = headless
        self._timeout_s = timeout_s

    def _runtime_missing_message(self) -> str:
        return (
            "no browser automation runtime installed (expected one of: "
            f"{', '.join(self._RUNTIME_CANDIDATES)}) — BUILD_SPEC section 98"
        )

    async def health(self) -> tuple[bool, str]:
        runtime = detect_runtime(self._RUNTIME_CANDIDATES)
        if runtime is None:
            return False, self._runtime_missing_message()
        if not self._endpoint:
            return False, f"{runtime} is installed but no remote browser endpoint is set"
        return False, (
            f"{runtime} is installed but LifeOps has no adapter wired to it "
            "yet — being importable is not the same as being integrated"
        )

    async def search(
        self, query: str, *, store: str = "", limit: int = 10
    ) -> list[ProductResult]:
        _, message = await self.health()
        raise ProviderError(message, provider="browser")

    async def build_cart(self, *, store: str, items: list[ShoppingItem]) -> CartResult:
        _, message = await self.health()
        raise ProviderError(message, provider="browser")

    async def submit_order(
        self, *, store: str, cart_reference: str, items: list[ShoppingItem]
    ) -> OrderResult:
        _, message = await self.health()
        raise ProviderError(message, provider="browser")

    async def confirm_cart(self, *, store: str, cart_reference: str) -> tuple[bool, str]:
        _, message = await self.health()
        raise ProviderError(message, provider="browser")

    async def confirm_order(self, *, store: str, order_reference: str) -> tuple[bool, str]:
        _, message = await self.health()
        raise ProviderError(message, provider="browser")
