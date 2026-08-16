"""Composition root.

One place assembles the concrete NornicDB repositories, the secret store, the
configuration service, and LifeOpsCore. Everything downstream receives what it
needs rather than importing a global, which is what lets tests substitute the
in-memory fakes without patching module internals.
"""

from __future__ import annotations

import logging

from lifeops.clock import Clock, SystemClock
from lifeops.config.service import ConfigurationService
from lifeops.core import LifeOpsCore
from lifeops.repositories.nornic.client import NornicClient
from lifeops.repositories.nornic.people import NornicPersonRepository
from lifeops.repositories.nornic.preferences import NornicPreferenceRepository
from lifeops.repositories.nornic.tasks import NornicTaskRepository
from lifeops.secrets.local_encrypted import LocalEncryptedSecretStore
from lifeops.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class Container:
    """Owns process-lifetime resources for a LifeOps deployment."""

    def __init__(self, settings: Settings | None = None, clock: Clock | None = None) -> None:
        self.settings = settings or get_settings()
        self.clock = clock or SystemClock()
        self.settings.ensure_dirs()

        self.secret_store = LocalEncryptedSecretStore(self.settings.secrets_dir)
        self.config = ConfigurationService(
            config_dir=self.settings.config_dir,
            secret_store=self.secret_store,
            clock=self.clock,
        )

        self.nornic = NornicClient(self.settings)
        self.people = NornicPersonRepository(self.nornic)
        self.preferences = NornicPreferenceRepository(self.nornic)
        self.tasks = NornicTaskRepository(self.nornic)

        # Safe mode may be set at boot or flipped by the user from the
        # Console; the config document is authoritative once it exists.
        safe_mode = self.settings.safe_mode or self.config.get_system().safe_mode

        self.core = LifeOpsCore(
            people=self.people,
            preferences=self.preferences,
            tasks=self.tasks,
            clock=self.clock,
            safe_mode=safe_mode,
        )

    async def startup(self) -> None:
        await self.nornic.connect()
        await self.nornic.ensure_schema()

        # Bootstrap the primary person so a fresh deployment can accept a
        # preference immediately. The name is a placeholder the user renames
        # during first-run setup — asking a coding agent for it would violate
        # the GUI-driven configuration rule (BUILD_SPEC section 5).
        system = self.config.get_system()
        if not system.setup_completed:
            person = await self.core.ensure_primary_person(
                system.household_name or "Primary User"
            )
            if system.primary_person_id != person.id:
                self.config.update_system({"primary_person_id": person.id})

        logger.info("LifeOps Core started", extra={"safe_mode": self.core.safe_mode})

    async def shutdown(self) -> None:
        await self.nornic.close()

    async def health(self) -> dict[str, object]:
        """Component health for the System screen (BUILD_SPEC section 77)."""
        nornic_ok = await self.nornic.ping()
        return {
            "lifeops_core": {"healthy": True, "detail": "running"},
            "nornicdb": {
                "healthy": nornic_ok,
                "detail": self.settings.nornic_uri if nornic_ok else "unreachable",
            },
            "secret_store": {
                "healthy": True,
                "detail": f"local_encrypted ({len(self.secret_store.list_names())} secrets)",
            },
            "safe_mode": self.core.safe_mode,
        }
