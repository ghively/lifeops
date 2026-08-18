"""Calendar and email HTTP API (BUILD_SPEC sections 60, 61, 63, 64, 88, 96).

Same discipline as ``test_durable_work_api.py``: the real ``LifeOpsCore`` over
in-memory repositories and fake providers, reached through the real FastAPI
app. What is pinned here: routes, status codes, and that section 96's order —
read, hold, book through the outbox, approve, execute, independently verify —
survives the HTTP boundary. Also pins section 88: a Test button on a disabled
provider reports "not configured" rather than faking success.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager  # type: ignore[import-not-found]

from lifeops.api.http import create_app
from lifeops.calendar.fake import FakeCalendarProvider
from lifeops.calendar.service import CalendarProviderService
from lifeops.clock import FrozenClock
from lifeops.config.service import ConfigurationService
from lifeops.core import LifeOpsCore
from lifeops.domain.people import Person
from lifeops.email.fake import FakeEmailProvider
from lifeops.email.service import EmailProviderService
from lifeops.events import EventBus
from lifeops.repositories.fakes import (
    FakeActionRepository,
    FakeApprovalRepository,
    FakeAuditRepository,
    FakeMemoryRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeServiceRequestRepository,
    FakeTaskRepository,
    FakeWaitingRepository,
    FakeWorldRepository,
)
from lifeops.secrets.local_encrypted import InMemorySecretStore
from lifeops.settings import Settings

API = "/api/v1"
PRIMARY = "person_calendar_email_api_user"
HERMES_HEADERS = {"X-LifeOps-Client": "hermes-personal"}


class StubContainer:
    """A Container with fakes in place of NornicDB and every external
    provider, wired for calendar and email."""

    def __init__(self, tmp_path: Path) -> None:
        self.settings = Settings(state_dir=tmp_path / "state")
        self.settings.ensure_dirs()
        self.clock = FrozenClock()
        self.secret_store = InMemorySecretStore()
        self.config = ConfigurationService(
            config_dir=self.settings.config_dir,
            secret_store=self.secret_store,
            clock=self.clock,
        )
        self.events = EventBus()
        self.people = FakePersonRepository()
        self.preferences = FakePreferenceRepository()
        self.tasks = FakeTaskRepository()
        self.memories = FakeMemoryRepository()
        self.world = FakeWorldRepository(preferences=self.preferences)
        self.waiting = FakeWaitingRepository()
        self.actions = FakeActionRepository()
        self.approvals = FakeApprovalRepository()
        self.audit = FakeAuditRepository()

        self.fake_calendar = FakeCalendarProvider()
        self.calendar = CalendarProviderService(
            config=self.config,
            secret_store=self.secret_store,
            factories={"caldav": lambda settings, secrets: self.fake_calendar},
        )
        self.fake_email = FakeEmailProvider()
        self.email = EmailProviderService(
            config=self.config,
            secret_store=self.secret_store,
            factories={"email": lambda settings, secrets: self.fake_email},
        )

        self.core = LifeOpsCore(
            people=self.people,
            preferences=self.preferences,
            tasks=self.tasks,
            memory=self.memories,
            world=self.world,
            service_requests=FakeServiceRequestRepository(),
            waiting=self.waiting,
            actions=self.actions,
            approvals=self.approvals,
            audit=self.audit,
            calendar=self.calendar,
            email=self.email,
            clock=self.clock,
            events=self.events,
        )

    def enable_calendar(self) -> None:
        self.config.update_provider("calendar", {"enabled": True, "backend": "caldav"})

    def enable_email(self) -> None:
        self.config.update_provider(
            "email", {"enabled": True, "imap_host": "x", "smtp_host": "x", "username": "u"}
        )

    async def startup(self) -> None:
        person = Person(
            id=PRIMARY,
            display_name="Calendar Email API User",
            is_primary=True,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        await self.people.upsert(person)

    async def shutdown(self) -> None:
        return None

    async def health(self) -> dict[str, Any]:
        return {
            "lifeops_core": {"healthy": True, "detail": "running"},
            "nornicdb": {"healthy": True, "detail": "fake"},
            "secret_store": {"healthy": True, "detail": "in-memory"},
            "safe_mode": self.core.safe_mode,
        }


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[tuple[httpx.AsyncClient, StubContainer]]:
    container = StubContainer(tmp_path)
    app = create_app(container=container, settings=container.settings)  # type: ignore[arg-type]
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://lifeops.test"
        ) as http_client:
            yield http_client, container


Env = tuple[httpx.AsyncClient, "StubContainer"]


class TestProviderHonesty:
    """Section 88: never fake success for a disabled provider."""

    async def test_testing_a_disabled_calendar_provider_reports_not_configured(
        self, env: Env
    ) -> None:
        client, _ = env
        response = await client.post(f"{API}/config/providers/calendar/test")
        assert response.status_code == 200
        body = response.json()
        assert body["healthy"] is False

    async def test_testing_an_enabled_calendar_provider_calls_the_adapter(
        self, env: Env
    ) -> None:
        client, container = env
        container.enable_calendar()
        response = await client.post(f"{API}/config/providers/calendar/test")
        assert response.status_code == 200
        assert response.json()["healthy"] is True

    async def test_testing_an_enabled_email_provider_calls_the_adapter(
        self, env: Env
    ) -> None:
        client, container = env
        container.enable_email()
        response = await client.post(f"{API}/config/providers/email/test")
        assert response.status_code == 200
        assert response.json()["healthy"] is True


class TestCalendarRoutes:
    async def test_reading_the_calendar(self, env: Env) -> None:
        client, container = env
        container.enable_calendar()
        await container.fake_calendar.create_event(
            subject="Standing meeting",
            start_at="2026-09-01T09:00:00Z",
            end_at="2026-09-01T10:00:00Z",
        )
        response = await client.get(
            f"{API}/calendar/events",
            params={"start_at": "2026-09-01T00:00:00Z", "end_at": "2026-09-02T00:00:00Z"},
            headers=HERMES_HEADERS,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["events"][0]["title"] == "Standing meeting"

    async def test_the_full_booking_flow_through_http(self, env: Env) -> None:
        client, container = env
        container.enable_calendar()

        hold_response = await client.post(
            f"{API}/appointments/holds",
            json={
                "subject": "Furnace tune-up",
                "start_at": "2026-09-01T14:00:00Z",
                "end_at": "2026-09-01T15:00:00Z",
            },
            headers=HERMES_HEADERS,
        )
        assert hold_response.status_code == 201
        appointment = hold_response.json()
        assert appointment["status"] == "held"

        book_response = await client.post(
            f"{API}/appointments/{appointment['id']}/book", headers=HERMES_HEADERS
        )
        assert book_response.status_code == 200
        action = book_response.json()
        assert action["status"] == "needs_approval"

        approvals = await client.get(f"{API}/approvals")
        approval_id = approvals.json()["approvals"][0]["id"]
        decide = await client.post(
            f"{API}/approvals/{approval_id}/decide", json={"approved": True}
        )
        assert decide.status_code == 200

        executed = await client.post(
            f"{API}/actions/{action['id']}/execute", headers=HERMES_HEADERS
        )
        assert executed.status_code == 200
        assert executed.json()["status"] == "executed"

        # Not booked until independently verified (section 63's warning).
        still_held = await client.get(
            f"{API}/appointments/{appointment['id']}", headers=HERMES_HEADERS
        )
        assert still_held.json()["status"] == "held"

        verified = await client.post(
            f"{API}/actions/{action['id']}/verify-externally", headers=HERMES_HEADERS
        )
        assert verified.status_code == 200
        assert verified.json()["status"] == "verified"

        booked = await client.get(
            f"{API}/appointments/{appointment['id']}", headers=HERMES_HEADERS
        )
        assert booked.json()["status"] == "booked"
        assert booked.json()["external_event_id"] is not None

    async def test_holding_time_without_book_appointment_is_refused(
        self, env: Env
    ) -> None:
        client, container = env
        container.enable_calendar()
        response = await client.post(
            f"{API}/appointments/holds",
            json={
                "subject": "Furnace tune-up",
                "start_at": "2026-09-01T14:00:00Z",
                "end_at": "2026-09-01T15:00:00Z",
            },
            headers={"X-LifeOps-Client": "interactive-mcp"},
        )
        assert response.status_code == 403


class TestEmailRoutes:
    async def test_sending_email_prepares_an_action_and_can_be_executed(
        self, env: Env
    ) -> None:
        client, container = env
        container.enable_email()

        send = await client.post(
            f"{API}/email/send",
            json={
                "to_addresses": ["provider@example.com"],
                "subject": "Availability?",
                "body": "Do you have anything next week?",
            },
            headers=HERMES_HEADERS,
        )
        assert send.status_code == 201
        action = send.json()
        assert action["type"] == "send_email"
        assert action["status"] == "prepared"

        executed = await client.post(
            f"{API}/actions/{action['id']}/execute", headers=HERMES_HEADERS
        )
        assert executed.status_code == 200
        assert executed.json()["status"] == "executed"

        verified = await client.post(
            f"{API}/actions/{action['id']}/verify-externally", headers=HERMES_HEADERS
        )
        assert verified.status_code == 200
        assert verified.json()["status"] == "verified"

    async def test_sending_email_without_send_external_message_is_refused(
        self, env: Env
    ) -> None:
        client, _ = env
        response = await client.post(
            f"{API}/email/send",
            json={"to_addresses": ["a@example.com"], "subject": "x", "body": "y"},
            headers={"X-LifeOps-Client": "interactive-mcp"},
        )
        assert response.status_code == 403


class TestDocumentRoutes:
    async def test_creating_a_document(self, env: Env) -> None:
        client, _ = env
        response = await client.post(
            f"{API}/documents",
            json={
                "title": "ABC Electric quote",
                "source": "email",
                "source_ref": "msg-1",
                "summary": "$2,400 for a panel upgrade",
            },
            headers=HERMES_HEADERS,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["source"] == "email"

        detail = await client.get(f"{API}/world/entities/{body['id']}", headers=HERMES_HEADERS)
        assert detail.status_code == 200
        assert detail.json()["entity"]["entity_type"] == "document"
