"""EmailProviderService — selects and calls the enabled email backend
(BUILD_SPEC section 64), mirroring ``calendar/service.py`` and
``voice/service.py``."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lifeops.config.provider_registry import ProviderCategory, providers_in_category
from lifeops.config.service import ConfigurationService, HealthReport
from lifeops.domain.email import EmailMessage, EmailSendDraft, EmailThread
from lifeops.email.imap_smtp import ImapSmtpEmailProvider
from lifeops.email.provider import EmailProvider
from lifeops.errors import ProviderNotConfiguredError
from lifeops.secrets.interface import SecretStore, secret_ref

ProviderFactory = Callable[[dict[str, Any], SecretStore], EmailProvider]


def _build_imap_smtp(settings: dict[str, Any], secrets: SecretStore) -> EmailProvider:
    imap_host = settings.get("imap_host")
    smtp_host = settings.get("smtp_host")
    username = settings.get("username")
    if not (imap_host and smtp_host and username):
        raise ProviderNotConfiguredError(
            "the email provider is missing a host or username", provider="email"
        )
    password = secrets.get(secret_ref("email", "password")) or ""
    return ImapSmtpEmailProvider(
        imap_host=imap_host,
        imap_port=int(settings.get("imap_port") or 993),
        smtp_host=smtp_host,
        smtp_port=int(settings.get("smtp_port") or 587),
        username=username,
        password=password,
        from_address=settings.get("from_address") or username,
    )


_DEFAULT_FACTORIES: dict[str, ProviderFactory] = {"email": _build_imap_smtp}


class EmailProviderService:
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

    def _active_provider_id(self) -> str | None:
        for definition in providers_in_category(ProviderCategory.EMAIL):
            if definition.id not in self._factories:
                continue
            status = self._config.get_status(definition.id)
            if status.enabled and not status.missing_required:
                return definition.id
        return None

    def _build(self) -> tuple[str, EmailProvider]:
        provider_id = self._active_provider_id()
        if provider_id is None:
            raise ProviderNotConfiguredError(
                "no email provider is enabled and fully configured yet"
            )
        status = self._config.get_status(provider_id)
        return provider_id, self._factories[provider_id](status.settings, self._secrets)

    async def health(self) -> tuple[str, HealthReport]:
        provider_id, provider = self._build()
        healthy, message = await provider.health()
        report = self._config.record_health(provider_id, healthy=healthy, message=message)
        return provider_id, report

    async def search(self, query: str, *, limit: int = 25) -> list[EmailMessage]:
        _, provider = self._build()
        return await provider.search(query, limit=limit)

    async def read_thread(self, thread_id: str) -> EmailThread:
        _, provider = self._build()
        return await provider.read_thread(thread_id)

    async def send(self, draft: EmailSendDraft) -> str:
        _, provider = self._build()
        return await provider.send(draft)

    async def confirm_sent(self, message_id: str) -> bool:
        _, provider = self._build()
        return await provider.confirm_sent(message_id)
