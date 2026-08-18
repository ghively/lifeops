"""Service request HTTP API (BUILD_SPEC sections 36, 60, 61, 67, 68, 97, 101).

Same discipline as ``test_calendar_email_api.py``: the real ``LifeOpsCore``
over in-memory repositories and fake providers, reached through the real
FastAPI app. Pins the section 101 flow at the HTTP boundary — open, contact,
collect, prepare booking, approve, execute, independently verify, confirm,
complete — and section 88: the telephony Test button reports "not
configured" rather than faking success while it ships disabled.
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
from lifeops.events import EventBus
from lifeops.repositories.fakes import (
    FakeActionRepository,
    FakeApprovalRepository,
    FakeAuditRepository,
    FakeMemoryRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeServiceRequestRepository,
    FakeShoppingRepository,
    FakeTaskRepository,
    FakeWaitingRepository,
    FakeWorldRepository,
)
from lifeops.secrets.local_encrypted import InMemorySecretStore
from lifeops.settings import Settings
from lifeops.telephony.fake import FakeTelephonyProvider
from lifeops.telephony.service import TelephonyProviderService

API = "/api/v1"
PRIMARY = "person_service_request_api_user"
HERMES_HEADERS = {"X-LifeOps-Client": "hermes-personal"}


class StubContainer:
    """A Container with fakes in place of NornicDB and every external
    provider, wired for service requests, calendar, and telephony."""

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
        self.fake_telephony = FakeTelephonyProvider(
            availability=["Thursday 1:00-3:00 PM"], diagnostic_fee="$89"
        )
        self.telephony = TelephonyProviderService(
            config=self.config,
            secret_store=self.secret_store,
            factories={"telephony": lambda settings, secrets: self.fake_telephony},
        )

        self.core = LifeOpsCore(
            people=self.people,
            preferences=self.preferences,
            tasks=self.tasks,
            memory=self.memories,
            world=self.world,
            shopping=FakeShoppingRepository(),
            service_requests=FakeServiceRequestRepository(),
            waiting=self.waiting,
            actions=self.actions,
            approvals=self.approvals,
            audit=self.audit,
            calendar=self.calendar,
            telephony=self.telephony,
            clock=self.clock,
            events=self.events,
        )

    def enable_calendar(self) -> None:
        self.config.update_provider("calendar", {"enabled": True, "backend": "caldav"})

    def enable_telephony(self) -> None:
        # account_sid/from_number/auth_token are now required fields
        # (Twilio's shape) — this stub still never reaches the real Twilio
        # adapter (factories={"telephony": ...} injects the fake above), but
        # status.missing_required checks these the same way calendar's
        # "backend" does, so they need to be present for the fake to be
        # selected at all. update_provider routes auth_token (a SecretField)
        # into the secret store automatically.
        self.config.update_provider(
            "telephony",
            {
                "enabled": True,
                "account_sid": "AC" + "0" * 32,
                "auth_token": "test-auth-token",
                "from_number": "+15551234567",
            },
        )

    async def startup(self) -> None:
        person = Person(
            id=PRIMARY,
            display_name="Service Request API User",
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
    """Section 88/104: telephony ships disabled, with no telephony SDK
    dependency and no real transport — a fresh deployment must report this
    honestly rather than fake a success."""

    async def test_testing_a_disabled_telephony_provider_reports_not_implemented(
        self, env: Env
    ) -> None:
        client, _ = env
        response = await client.post(f"{API}/config/providers/telephony/test")
        assert response.status_code == 200
        assert response.json()["healthy"] is False


class TestServiceRequestLifecycle:
    async def test_the_full_electrician_flow_through_http(self, env: Env) -> None:
        """Section 101 end to end at the HTTP boundary: open, contact,
        collect, hold, prepare booking, approve, execute, verify, confirm,
        complete."""
        client, container = env
        container.enable_calendar()
        container.enable_telephony()

        create_response = await client.post(
            f"{API}/service-requests",
            json={"subject": "Living Room Outlet repair", "asset_entity_id": "asset_outlet"},
            headers=HERMES_HEADERS,
        )
        assert create_response.status_code == 201
        service_request = create_response.json()
        assert service_request["status"] == "researching"
        sr_id = service_request["id"]

        call_response = await client.post(
            f"{API}/service-requests/{sr_id}/call",
            json={
                "provider_entity_id": "provider_abc_electric",
                "objective": "schedule_electrician",
                "collect": ["availability", "diagnostic_fee"],
            },
            headers=HERMES_HEADERS,
        )
        assert call_response.status_code == 200
        action = call_response.json()
        # R2, policy-controlled: not approval-gated by default.
        assert action["status"] == "prepared"
        assert action["payload"]["authority"]["authorize_charge"] is False
        assert action["payload"]["authority"]["authorize_repairs"] is False

        executed = await client.post(
            f"{API}/actions/{action['id']}/execute", headers=HERMES_HEADERS
        )
        assert executed.status_code == 200
        assert executed.json()["status"] == "executed"

        after_call = await client.get(
            f"{API}/service-requests/{sr_id}", headers=HERMES_HEADERS
        )
        assert after_call.json()["status"] == "quote_collected"
        assert after_call.json()["diagnostic_fee"] == "$89"

        hold_response = await client.post(
            f"{API}/appointments/holds",
            json={
                "subject": "Electrician: Living Room Outlet",
                "start_at": "2026-09-04T13:00:00Z",
                "end_at": "2026-09-04T15:00:00Z",
                "provider_entity_id": "provider_abc_electric",
            },
            headers=HERMES_HEADERS,
        )
        assert hold_response.status_code == 201
        appointment_id = hold_response.json()["id"]

        book_response = await client.post(
            f"{API}/service-requests/{sr_id}/book",
            json={"appointment_id": appointment_id},
            headers=HERMES_HEADERS,
        )
        assert book_response.status_code == 200
        booking_action = book_response.json()
        # BOOK_APPOINTMENT is R3: always approval.
        assert booking_action["status"] == "needs_approval"

        after_booking_request = await client.get(
            f"{API}/service-requests/{sr_id}", headers=HERMES_HEADERS
        )
        assert after_booking_request.json()["status"] == "booking_requested"

        approvals = await client.get(f"{API}/approvals")
        approval_id = approvals.json()["approvals"][0]["id"]
        decide = await client.post(
            f"{API}/approvals/{approval_id}/decide", json={"approved": True}
        )
        assert decide.status_code == 200

        book_executed = await client.post(
            f"{API}/actions/{booking_action['id']}/execute", headers=HERMES_HEADERS
        )
        assert book_executed.status_code == 200
        assert book_executed.json()["status"] == "executed"

        # Not booked until independently verified (section 63's warning,
        # section 101 step 13).
        still_held = await client.get(
            f"{API}/appointments/{appointment_id}", headers=HERMES_HEADERS
        )
        assert still_held.json()["status"] == "held"

        # Confirming against the service request before verification is
        # refused (AGENTS.md safety invariant 3: evidence before completion).
        premature_confirm = await client.post(
            f"{API}/service-requests/{sr_id}/confirm-booking",
            json={"appointment_id": appointment_id},
            headers=HERMES_HEADERS,
        )
        assert premature_confirm.status_code >= 400

        verified = await client.post(
            f"{API}/actions/{booking_action['id']}/verify-externally",
            headers=HERMES_HEADERS,
        )
        assert verified.status_code == 200
        assert verified.json()["status"] == "verified"

        now_booked = await client.get(
            f"{API}/appointments/{appointment_id}", headers=HERMES_HEADERS
        )
        assert now_booked.json()["status"] == "booked"

        confirm = await client.post(
            f"{API}/service-requests/{sr_id}/confirm-booking",
            json={"appointment_id": appointment_id},
            headers=HERMES_HEADERS,
        )
        assert confirm.status_code == 200
        assert confirm.json()["status"] == "booked"

        complete = await client.post(
            f"{API}/service-requests/{sr_id}/complete", headers=HERMES_HEADERS
        )
        assert complete.status_code == 200
        assert complete.json()["status"] == "completed"

    async def test_no_answer_opens_a_waiting_item_via_http(self, env: Env) -> None:
        """Section 101 step 8, at the HTTP boundary."""
        client, container = env
        container.enable_telephony()
        container.fake_telephony.connected = False

        task_response = await client.post(
            f"{API}/tasks", json={"title": "Get HVAC servicing"}, headers=HERMES_HEADERS
        )
        task_id = task_response.json()["id"]

        create_response = await client.post(
            f"{API}/service-requests",
            json={"subject": "Furnace tune-up", "task_id": task_id},
            headers=HERMES_HEADERS,
        )
        sr_id = create_response.json()["id"]

        call_response = await client.post(
            f"{API}/service-requests/{sr_id}/call",
            json={
                "provider_entity_id": "provider_hvac",
                "objective": "schedule_hvac",
                "collect": ["availability"],
            },
            headers=HERMES_HEADERS,
        )
        action_id = call_response.json()["id"]
        await client.post(f"{API}/actions/{action_id}/execute", headers=HERMES_HEADERS)

        updated = await client.get(
            f"{API}/service-requests/{sr_id}", headers=HERMES_HEADERS
        )
        assert updated.json()["status"] == "awaiting_provider"
        assert updated.json()["waiting_item_id"] is not None

        waiting = await client.get(f"{API}/waiting", headers=HERMES_HEADERS)
        assert waiting.json()["total"] == 1

    async def test_listing_service_requests(self, env: Env) -> None:
        client, _ = env
        await client.post(
            f"{API}/service-requests",
            json={"subject": "Water heater inspection"},
            headers=HERMES_HEADERS,
        )
        listed = await client.get(f"{API}/service-requests", headers=HERMES_HEADERS)
        assert listed.status_code == 200
        assert listed.json()["total"] >= 1
