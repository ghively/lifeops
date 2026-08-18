"""Composition root.

One place assembles the concrete NornicDB repositories, the secret store, the
configuration service, and LifeOpsCore. Everything downstream receives what it
needs rather than importing a global, which is what lets tests substitute the
in-memory fakes without patching module internals.
"""

from __future__ import annotations

import logging

from lifeops.auth import ConsoleAuth
from lifeops.browser.service import BrowserProviderService
from lifeops.calendar.service import CalendarProviderService
from lifeops.clock import Clock, SystemClock
from lifeops.config.service import ConfigurationService
from lifeops.core import LifeOpsCore
from lifeops.email.service import EmailProviderService
from lifeops.events import EventBus
from lifeops.observability.activity import attach_activity_buffer, detach_activity_buffer
from lifeops.repositories.nornic.actions import NornicActionRepository
from lifeops.repositories.nornic.approvals import NornicApprovalRepository
from lifeops.repositories.nornic.audit import NornicAuditRepository
from lifeops.repositories.nornic.bills import NornicBillRepository
from lifeops.repositories.nornic.client import NornicClient
from lifeops.repositories.nornic.memory import NornicMemoryRepository
from lifeops.repositories.nornic.people import NornicPersonRepository
from lifeops.repositories.nornic.preferences import NornicPreferenceRepository
from lifeops.repositories.nornic.service_requests import (
    NornicServiceRequestRepository,
)
from lifeops.repositories.nornic.shopping import NornicShoppingRepository
from lifeops.repositories.nornic.tasks import NornicTaskRepository
from lifeops.repositories.nornic.waiting import NornicWaitingRepository
from lifeops.repositories.nornic.workflow_templates import (
    NornicWorkflowTemplateRepository,
)
from lifeops.repositories.nornic.world import NornicWorldRepository
from lifeops.secrets.local_encrypted import LocalEncryptedSecretStore
from lifeops.settings import Settings, get_settings
from lifeops.telephony.service import TelephonyProviderService
from lifeops.voice.service import VoiceService
from lifeops.worker.due_work import DueWorkWorker

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
        self.auth = ConsoleAuth(
            secret_store=self.secret_store, settings=self.settings, clock=self.clock
        )
        # Phase 5: the ElevenLabs quick path. Composes configuration and
        # secrets into calls against an external speech API; it never touches
        # NornicDB or the world model LifeOpsCore owns.
        self.voice = VoiceService(config=self.config, secret_store=self.secret_store)
        # Phase 7: the calendar and email quick paths (BUILD_SPEC section 96).
        # Composes configuration and secrets into calls against an external
        # calendar/mail server; LifeOpsCore holds these too (unlike voice) so
        # every booking and send still passes through its capability checks
        # and the Action outbox rather than calling out directly.
        self.calendar = CalendarProviderService(
            config=self.config, secret_store=self.secret_store
        )
        self.email = EmailProviderService(config=self.config, secret_store=self.secret_store)
        # Phase 8 (BUILD_SPEC section 97). No real backend is wired — section
        # 88 forbids adding a telephony SDK dependency or asking for a
        # credential — so this stays honestly disabled until a later phase
        # adds a factory (telephony/service.py).
        self.telephony = TelephonyProviderService(
            config=self.config, secret_store=self.secret_store
        )
        # Phase 9 (BUILD_SPEC sections 66, 98). A real Playwright/Chromium
        # adapter is wired (browser/real.py — see its module docstring for
        # the AGENTS.md dependency justification); it needs no credential,
        # so this stays gated purely on the Console's "enabled" toggle,
        # honestly disabled by default per section 88.
        self.browser = BrowserProviderService(
            config=self.config, secret_store=self.secret_store
        )
        self.events = EventBus()
        # Ephemeral view of recent semantic operations for the Activity screen.
        # Not the audit log — it dies with the process (observability/activity.py).
        self.activity = attach_activity_buffer()

        self.nornic = NornicClient(self.settings)
        self.people = NornicPersonRepository(self.nornic)
        self.preferences = NornicPreferenceRepository(self.nornic)
        self.tasks = NornicTaskRepository(self.nornic)
        self.memory = NornicMemoryRepository(self.nornic)
        self.world = NornicWorldRepository(self.nornic)
        self.waiting = NornicWaitingRepository(self.nornic)
        self.actions = NornicActionRepository(self.nornic)
        self.approvals = NornicApprovalRepository(self.nornic)
        self.audit = NornicAuditRepository(self.nornic)
        self.bills = NornicBillRepository(self.nornic)
        self.shopping = NornicShoppingRepository(self.nornic)
        self.service_requests = NornicServiceRequestRepository(self.nornic)
        self.templates = NornicWorkflowTemplateRepository(self.nornic)

        # Safe mode may be set at boot or flipped by the user from the
        # Console; the config document is authoritative once it exists.
        # Passed as a callable, not a snapshot: the HTTP and MCP servers are
        # separate processes over the same config file, and the emergency
        # stop must reach a running MCP server without a restart. The config
        # service invalidates its cache on file change, so this is one stat
        # per capability check.
        def safe_mode() -> bool:
            return self.settings.safe_mode or self.config.get_system().safe_mode

        self.core = LifeOpsCore(
            people=self.people,
            preferences=self.preferences,
            tasks=self.tasks,
            memory=self.memory,
            world=self.world,
            waiting=self.waiting,
            actions=self.actions,
            approvals=self.approvals,
            audit=self.audit,
            bills=self.bills,
            shopping=self.shopping,
            service_requests=self.service_requests,
            templates=self.templates,
            calendar=self.calendar,
            email=self.email,
            telephony=self.telephony,
            browser=self.browser,
            clock=self.clock,
            safe_mode=safe_mode,
            events=self.events,
            # Resolved here, not left CWD-relative: the MCP server's working
            # directory is whatever its client launched it with.
            change_request_dir=str(self.settings.change_requests_path),
        )

        # BUILD_SPEC section 55: a small in-process worker, not a queue or a
        # process supervisor. It holds no state of its own — everything it
        # needs is read back from NornicDB every tick (section 93: work
        # survives a LifeOps restart because there is nothing else to lose).
        self.due_work_worker = DueWorkWorker(
            self.core,
            poll_interval_s=self.settings.due_work_poll_interval_s,
            batch_limit=self.settings.due_work_batch_limit,
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

        if self.settings.due_work_enabled:
            self.due_work_worker.start()

        logger.info("LifeOps Core started", extra={"safe_mode": self.core.safe_mode})

    async def shutdown(self) -> None:
        await self.due_work_worker.stop()
        detach_activity_buffer(self.activity)
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
