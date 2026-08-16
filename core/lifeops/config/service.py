"""Configuration service (BUILD_SPEC sections 22, 25, 26).

Holds the two halves of runtime configuration:

  * Non-secret provider settings and system settings, persisted as a JSON
    document under the LifeOps state directory.
  * Secret values, delegated to the SecretStore.

Reads never return a secret. The Console is told only whether a secret is
configured and, when useful, its fingerprint.

Provider settings live in a config document rather than in NornicDB because
they must be readable before a database connection exists — the Console has to
render "NornicDB: unreachable" without first reaching NornicDB.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from lifeops.clock import Clock, SystemClock, now_iso
from lifeops.config.provider_registry import (
    ProviderDefinition,
    ProviderState,
    all_providers,
    get_provider,
)
from lifeops.config.validation import missing_required, validate_update
from lifeops.errors import ConfigurationError, NotFoundError
from lifeops.secrets.interface import SecretStore, secret_ref

_DOCUMENT_VERSION = 1


class SecretStatus(BaseModel):
    """What the Console is allowed to know about a stored secret."""

    model_config = ConfigDict(extra="forbid")

    configured: bool
    fingerprint: str | None = None


class HealthReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    healthy: bool
    checked_at: str
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class ProviderStatus(BaseModel):
    """One provider as the Console sees it."""

    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str
    category: str
    summary: str
    state: ProviderState
    enabled: bool
    available_in_phase: int
    # Never contains secret values; secret fields appear in `secrets` instead.
    settings: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, SecretStatus] = Field(default_factory=dict)
    missing_required: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    last_health: HealthReport | None = None


class SystemConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = "LifeOps"
    timezone: str = "UTC"
    household_name: str = ""
    primary_person_id: str | None = None
    local_url: str | None = None
    setup_completed: bool = False
    safe_mode: bool = False


class ConfigurationService:
    def __init__(
        self,
        *,
        config_dir: Path,
        secret_store: SecretStore,
        clock: Clock | None = None,
    ) -> None:
        self._path = config_dir / "lifeops.config.json"
        self._secrets = secret_store
        self._clock = clock or SystemClock()
        self._document: dict[str, Any] | None = None
        config_dir.mkdir(parents=True, exist_ok=True)

    # --- persistence --------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        if self._document is not None:
            return self._document
        if not self._path.exists():
            self._document = {
                "version": _DOCUMENT_VERSION,
                "system": SystemConfig().model_dump(),
                "providers": {},
                "health": {},
            }
            return self._document
        try:
            data = json.loads(self._path.read_text())
        except json.JSONDecodeError as exc:
            raise ConfigurationError(
                "LifeOps configuration file is corrupt", path=str(self._path)
            ) from exc
        data.setdefault("system", SystemConfig().model_dump())
        data.setdefault("providers", {})
        data.setdefault("health", {})
        self._document = data
        return data

    def _save(self, document: dict[str, Any]) -> None:
        fd, tmp_name = tempfile.mkstemp(
            dir=self._path.parent, prefix=".lifeops-config-", suffix=".tmp"
        )
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as handle:
                json.dump(document, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self._path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        self._document = document

    # --- system config ------------------------------------------------------

    def get_system(self) -> SystemConfig:
        return SystemConfig(**self._load()["system"])

    def update_system(self, changes: dict[str, Any]) -> SystemConfig:
        current = self.get_system().model_dump()
        unknown = set(changes) - set(current)
        if unknown:
            raise ConfigurationError(
                f"unknown system settings: {sorted(unknown)}", unknown=sorted(unknown)
            )
        current.update(changes)
        updated = SystemConfig(**current)

        document = dict(self._load())
        document["system"] = updated.model_dump()
        self._save(document)
        return updated

    # --- provider config ----------------------------------------------------

    def _provider_settings(self, provider_id: str) -> dict[str, Any]:
        return dict(self._load()["providers"].get(provider_id, {}))

    def _stored_secret_names(self, provider: ProviderDefinition) -> set[str]:
        return {
            field.name
            for field in provider.secret_fields
            if self._secrets.exists(secret_ref(provider.id, field.name))
        }

    def _effective_settings(self, provider: ProviderDefinition) -> dict[str, Any]:
        """Stored values layered over schema defaults."""
        effective: dict[str, Any] = {
            field.name: field.default
            for field in provider.fields
            if not field.is_secret
        }
        effective.update(self._provider_settings(provider.id))
        return effective

    def _state_of(
        self,
        provider: ProviderDefinition,
        settings: dict[str, Any],
        stored_secrets: set[str],
        health: HealthReport | None,
    ) -> tuple[ProviderState, list[str]]:
        missing = missing_required(provider, settings, stored_secrets)
        enabled = bool(settings.get("enabled", False))

        if missing:
            # Missing settings outrank the enabled flag: a provider that
            # cannot work should not read as merely "off".
            return ProviderState.NOT_CONFIGURED, missing
        if not enabled:
            return ProviderState.DISABLED, missing
        if health is None:
            return ProviderState.CONFIGURED, missing
        return (
            ProviderState.HEALTHY if health.healthy else ProviderState.UNHEALTHY
        ), missing

    def get_status(self, provider_id: str) -> ProviderStatus:
        provider = get_provider(provider_id)
        if provider is None:
            raise NotFoundError(f"unknown provider {provider_id!r}", provider=provider_id)

        settings = self._effective_settings(provider)
        stored_secrets = self._stored_secret_names(provider)
        health = self.get_health(provider_id)
        state, missing = self._state_of(provider, settings, stored_secrets, health)

        return ProviderStatus(
            id=provider.id,
            display_name=provider.display_name,
            category=str(provider.category),
            summary=provider.summary,
            state=state,
            enabled=bool(settings.get("enabled", False)),
            available_in_phase=provider.available_in_phase,
            settings=settings,
            secrets={
                field.name: SecretStatus(
                    configured=field.name in stored_secrets,
                    fingerprint=self._secrets.fingerprint(
                        secret_ref(provider.id, field.name)
                    ),
                )
                for field in provider.secret_fields
            },
            missing_required=missing,
            capabilities=list(provider.capabilities),
            last_health=health,
        )

    def list_status(self) -> list[ProviderStatus]:
        return [self.get_status(p.id) for p in all_providers()]

    def update_provider(self, provider_id: str, submitted: dict[str, Any]) -> ProviderStatus:
        """Apply a partial configuration update.

        Secret values are handed to the SecretStore and are never written into
        the configuration document. Sending an empty string for a secret field
        clears it.
        """
        provider = get_provider(provider_id)
        if provider is None:
            raise NotFoundError(f"unknown provider {provider_id!r}", provider=provider_id)

        stored_secrets = self._stored_secret_names(provider)
        validated = validate_update(provider, submitted, known_secrets=stored_secrets)

        for field_name, value in validated.secrets.items():
            self._secrets.set(secret_ref(provider.id, field_name), value)

        # An explicitly empty secret is a deletion request.
        for field in provider.secret_fields:
            if field.name in submitted and field.name not in validated.secrets:
                submitted_value = submitted[field.name]
                if submitted_value in (None, ""):
                    self._secrets.delete(secret_ref(provider.id, field.name))

        if validated.settings:
            document = dict(self._load())
            providers = dict(document["providers"])
            merged = dict(providers.get(provider_id, {}))
            merged.update(validated.settings)
            providers[provider_id] = merged
            document["providers"] = providers
            self._save(document)

        return self.get_status(provider_id)

    def get_secret(self, provider_id: str, field_name: str) -> str | None:
        """Read a provider secret.

        For adapter code only. No API route returns this value.
        """
        return self._secrets.get(secret_ref(provider_id, field_name))

    # --- health -------------------------------------------------------------

    def get_health(self, provider_id: str) -> HealthReport | None:
        raw = self._load()["health"].get(provider_id)
        return HealthReport(**raw) if raw else None

    def record_health(
        self, provider_id: str, *, healthy: bool, message: str = "", **details: Any
    ) -> HealthReport:
        report = HealthReport(
            healthy=healthy,
            checked_at=now_iso(self._clock),
            message=message,
            details=details,
        )
        document = dict(self._load())
        health = dict(document["health"])
        health[provider_id] = report.model_dump()
        document["health"] = health
        self._save(document)
        return report
