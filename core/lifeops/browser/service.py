"""BrowserProviderService — selects and calls the enabled browser worker
(BUILD_SPEC sections 22, 98), mirroring ``calendar/service.py``.

Only one provider id exists in the registry (``browser``), so there is no
backend selector the way ``calendar`` has caldav/google — just "enabled" or
not. ``RealBrowserWorker`` is the only adapter, and it reports its own honest
"not installed" health (section 88: never fake success) until a real browser
runtime is wired in.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lifeops.browser.provider import BrowserWorker
from lifeops.browser.real import RealBrowserWorker
from lifeops.config.provider_registry import ProviderCategory, providers_in_category
from lifeops.config.service import ConfigurationService, HealthReport
from lifeops.domain.shopping import CartResult, OrderResult, ProductResult, ShoppingItem
from lifeops.errors import ProviderNotConfiguredError
from lifeops.secrets.interface import SecretStore

WorkerFactory = Callable[[dict[str, Any], SecretStore], BrowserWorker]


def _build_real(settings: dict[str, Any], secrets: SecretStore) -> BrowserWorker:
    return RealBrowserWorker(
        endpoint=settings.get("endpoint"),
        headless=bool(settings.get("headless", True)),
        timeout_s=float(settings.get("timeout_s") or 30),
    )


_DEFAULT_FACTORIES: dict[str, WorkerFactory] = {"browser": _build_real}


class BrowserProviderService:
    def __init__(
        self,
        *,
        config: ConfigurationService,
        secret_store: SecretStore,
        factories: dict[str, WorkerFactory] | None = None,
    ) -> None:
        self._config = config
        self._secrets = secret_store
        self._factories = factories if factories is not None else _DEFAULT_FACTORIES

    def _build(self) -> BrowserWorker:
        for definition in providers_in_category(ProviderCategory.BROWSER):
            status = self._config.get_status(definition.id)
            factory = self._factories.get(definition.id)
            if factory is None or not (status.enabled and not status.missing_required):
                continue
            return factory(status.settings, self._secrets)
        raise ProviderNotConfiguredError(
            "no browser provider is enabled and fully configured yet", provider="browser"
        )

    async def health(self) -> HealthReport:
        worker = self._build()
        healthy, message = await worker.health()
        return self._config.record_health("browser", healthy=healthy, message=message)

    async def search(self, query: str, *, store: str = "", limit: int = 10) -> list[ProductResult]:
        return await self._build().search(query, store=store, limit=limit)

    async def build_cart(self, *, store: str, items: list[ShoppingItem]) -> CartResult:
        return await self._build().build_cart(store=store, items=items)

    async def submit_order(
        self, *, store: str, cart_reference: str, items: list[ShoppingItem]
    ) -> OrderResult:
        return await self._build().submit_order(
            store=store, cart_reference=cart_reference, items=items
        )

    async def confirm_cart(self, *, store: str, cart_reference: str) -> tuple[bool, str]:
        return await self._build().confirm_cart(store=store, cart_reference=cart_reference)

    async def confirm_order(self, *, store: str, order_reference: str) -> tuple[bool, str]:
        return await self._build().confirm_order(store=store, order_reference=order_reference)
