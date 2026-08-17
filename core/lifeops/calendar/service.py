"""CalendarProviderService — selects and calls the enabled calendar backend
(BUILD_SPEC sections 63, 96), mirroring ``voice/service.py``.

Only ``caldav`` has a real adapter as of Phase 7; ``google`` is a declared
choice in the provider registry with no adapter yet (section 88: build the
schema and the disabled state honestly, never fake success), so selecting it
raises ``ProviderNotConfiguredError`` with a message that says so rather than
silently falling through to CalDAV or to the fake.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lifeops.calendar.caldav import CalDAVCalendarProvider
from lifeops.calendar.provider import CalendarProvider
from lifeops.config.provider_registry import ProviderCategory, providers_in_category
from lifeops.config.service import ConfigurationService, HealthReport
from lifeops.domain.calendar import CalendarEvent, FreeBusySlot
from lifeops.errors import ProviderNotConfiguredError
from lifeops.secrets.interface import SecretStore, secret_ref

ProviderFactory = Callable[[dict[str, Any], SecretStore], CalendarProvider]


def _build_caldav(settings: dict[str, Any], secrets: SecretStore) -> CalendarProvider:
    url = settings.get("url")
    if not url:
        raise ProviderNotConfiguredError(
            "the calendar provider has no server URL configured", provider="calendar"
        )
    username = settings.get("username") or ""
    password = secrets.get(secret_ref("calendar", "password")) or ""
    return CalDAVCalendarProvider(base_url=url, username=username, password=password)


def _build_google(settings: dict[str, Any], secrets: SecretStore) -> CalendarProvider:
    raise ProviderNotConfiguredError(
        "the Google Calendar backend has no adapter yet; use CalDAV",
        provider="calendar",
        backend="google",
    )


_DEFAULT_FACTORIES: dict[str, ProviderFactory] = {
    "caldav": _build_caldav,
    "google": _build_google,
}


class CalendarProviderService:
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

    def _build(self) -> CalendarProvider:
        for definition in providers_in_category(ProviderCategory.CALENDAR):
            status = self._config.get_status(definition.id)
            if not (status.enabled and not status.missing_required):
                continue
            backend = str(status.settings.get("backend") or "")
            factory = self._factories.get(backend)
            if factory is None:
                raise ProviderNotConfiguredError(
                    f"unknown calendar backend {backend!r}", provider="calendar"
                )
            return factory(status.settings, self._secrets)
        raise ProviderNotConfiguredError(
            "no calendar provider is enabled and fully configured yet"
        )

    async def health(self) -> HealthReport:
        provider = self._build()
        healthy, message = await provider.health()
        return self._config.record_health("calendar", healthy=healthy, message=message)

    async def list_events(self, *, start_at: str, end_at: str) -> list[CalendarEvent]:
        return await self._build().list_events(start_at=start_at, end_at=end_at)

    async def free_busy(self, *, start_at: str, end_at: str) -> list[FreeBusySlot]:
        return await self._build().free_busy(start_at=start_at, end_at=end_at)

    async def create_hold(
        self, *, subject: str, start_at: str, end_at: str, notes: str = ""
    ) -> str:
        return await self._build().create_hold(
            subject=subject, start_at=start_at, end_at=end_at, notes=notes
        )

    async def create_event(
        self,
        *,
        subject: str,
        start_at: str,
        end_at: str,
        location: str = "",
        notes: str = "",
        hold_reference: str | None = None,
    ) -> str:
        return await self._build().create_event(
            subject=subject, start_at=start_at, end_at=end_at,
            location=location, notes=notes, hold_reference=hold_reference,
        )

    async def get_event(self, external_event_id: str) -> CalendarEvent | None:
        return await self._build().get_event(external_event_id)

    async def cancel_event(self, external_event_id: str) -> None:
        await self._build().cancel_event(external_event_id)
