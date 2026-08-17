"""TelephonyProviderService — selects and calls the enabled telephony backend
(BUILD_SPEC sections 68, 88), mirroring ``calendar/service.py`` and
``email/service.py``.

Unlike those two, ``_DEFAULT_FACTORIES`` is empty. Section 88 and the phase 8
build instructions are explicit: no telephony SDK dependency is added, and the
transport stays abstract rather than shipping a real adapter with nothing
genuine behind it. Enabling the ``telephony`` provider in the Console therefore
still raises ``ProviderNotConfiguredError`` when something tries to place a
call — an honest "not implemented yet", never a faked success (AGENTS.md).
Tests inject ``FakeTelephonyProvider`` through the ``factories`` constructor
argument, the same seam ``CalendarProviderService`` offers for CalDAV.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lifeops.config.provider_registry import ProviderCategory, providers_in_category
from lifeops.config.service import ConfigurationService, HealthReport
from lifeops.domain.telephony import CallObjective, CallResult
from lifeops.errors import ProviderNotConfiguredError
from lifeops.secrets.interface import SecretStore
from lifeops.telephony.provider import TelephonyProvider

ProviderFactory = Callable[[dict[str, Any], SecretStore], TelephonyProvider]

#: No real backend is wired in this phase (see module docstring). Kept as a
#: named, empty constant — rather than inlined — so the reason is visible at
#: the definition site, not just in prose above it.
_DEFAULT_FACTORIES: dict[str, ProviderFactory] = {}


class TelephonyProviderService:
    def __init__(
        self,
        *,
        config: ConfigurationService,
        secret_store: SecretStore,
        factories: dict[str, ProviderFactory] | None = None,
    ) -> None:
        self._config = config
        self._secrets = secret_store
        self._factories = factories if factories is not None else _DEFAULT_FACTORIES

    def _build(self) -> TelephonyProvider:
        for definition in providers_in_category(ProviderCategory.TELEPHONY):
            if definition.id not in self._factories:
                continue
            status = self._config.get_status(definition.id)
            if status.enabled and not status.missing_required:
                return self._factories[definition.id](status.settings, self._secrets)
        raise ProviderNotConfiguredError(
            "no telephony provider is enabled and fully configured yet"
        )

    async def health(self) -> HealthReport:
        provider = self._build()
        healthy, message = await provider.health()
        return self._config.record_health("telephony", healthy=healthy, message=message)

    async def dial(self, objective: CallObjective) -> CallResult:
        return await self._build().dial(objective)

    async def hangup(self, external_reference: str) -> None:
        await self._build().hangup(external_reference)

    async def send_dtmf(self, external_reference: str, digits: str) -> None:
        await self._build().send_dtmf(external_reference, digits)

    async def get_status(self, external_reference: str) -> CallResult | None:
        return await self._build().get_status(external_reference)
