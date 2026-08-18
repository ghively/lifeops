"""TelephonyProviderService — selects and calls the enabled telephony backend
(BUILD_SPEC sections 68, 88), mirroring ``calendar/service.py`` and
``email/service.py``.

``TwilioTelephonyProvider`` (``telephony/twilio.py``) is the real adapter —
see its module docstring for what "real" does and does not mean here (call
control is genuine; a destination phone number and a conversation are not,
for reasons that predate this adapter). Tests inject
``FakeTelephonyProvider`` through the ``factories`` constructor argument, the
same seam ``CalendarProviderService`` offers for CalDAV.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lifeops.config.provider_registry import ProviderCategory, providers_in_category
from lifeops.config.service import ConfigurationService, HealthReport
from lifeops.domain.telephony import CallObjective, CallResult
from lifeops.errors import ProviderNotConfiguredError
from lifeops.secrets.interface import SecretStore, secret_ref
from lifeops.telephony.provider import TelephonyProvider
from lifeops.telephony.twilio import TwilioTelephonyProvider

ProviderFactory = Callable[[dict[str, Any], SecretStore], TelephonyProvider]


def _build_twilio(settings: dict[str, Any], secrets: SecretStore) -> TelephonyProvider:
    auth_token = secrets.get(secret_ref("telephony", "auth_token"))
    if not auth_token:
        raise ProviderNotConfiguredError(
            "Twilio has no auth token configured", provider="telephony"
        )
    account_sid = settings.get("account_sid")
    from_number = settings.get("from_number")
    if not account_sid or not from_number:
        raise ProviderNotConfiguredError(
            "Twilio needs an account SID and a from number", provider="telephony"
        )
    return TwilioTelephonyProvider(
        account_sid=str(account_sid), auth_token=auth_token, from_number=str(from_number)
    )


_DEFAULT_FACTORIES: dict[str, ProviderFactory] = {"telephony": _build_twilio}


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
