"""Bills and payees over HTTP (BUILD_SPEC sections 72, 99).

Runs the real LifeOpsCore over fakes. What is pinned is the boundary a human
meets: who may pay, that a payee is unusable until approved, and that a bill
is never settled without the provider's own confirmation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager  # type: ignore[import-not-found]

from lifeops.api.http import create_app, get_client
from lifeops.clock import FrozenClock
from lifeops.config.service import ConfigurationService
from lifeops.core import LifeOpsCore
from lifeops.domain.people import Person
from lifeops.events import EventBus
from lifeops.policy.capabilities import HERMES
from lifeops.repositories.fakes import (
    FakeActionRepository,
    FakeApprovalRepository,
    FakeAuditRepository,
    FakeBillRepository,
    FakeMemoryRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
    FakeWaitingRepository,
    FakeWorldRepository,
)
from lifeops.secrets.local_encrypted import InMemorySecretStore
from lifeops.settings import Settings

API = "/api/v1"
TS = "2026-01-01T00:00:00Z"


class StubContainer:
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
        self.core = LifeOpsCore(
            people=self.people,
            preferences=FakePreferenceRepository(),
            tasks=FakeTaskRepository(),
            memory=FakeMemoryRepository(),
            world=FakeWorldRepository(),
            waiting=FakeWaitingRepository(),
            actions=FakeActionRepository(),
            approvals=FakeApprovalRepository(),
            audit=FakeAuditRepository(),
            bills=FakeBillRepository(),
            clock=self.clock,
            events=self.events,
        )

    async def startup(self) -> None:
        await self.people.upsert(
            Person(id="person_u", display_name="U", is_primary=True,
                   created_at=TS, updated_at=TS)
        )

    async def shutdown(self) -> None:
        return None

    async def health(self) -> dict[str, Any]:
        return {"safe_mode": self.core.safe_mode}


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[tuple[httpx.AsyncClient, Any]]:
    container = StubContainer(tmp_path)
    app = create_app(container=container, settings=container.settings)  # type: ignore[arg-type]
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://lifeops.test"
        ) as http:
            yield http, app


async def _approved_payee(http: httpx.AsyncClient, name: str = "Utility Co") -> str:
    await http.post(f"{API}/payees", json={"display_name": name})
    payee_id = (await http.get(f"{API}/payees")).json()["payees"][0]["id"]
    await http.post(f"{API}/payees/{payee_id}/approve")
    return payee_id


class TestPayees:
    async def test_a_new_payee_returns_an_action_not_a_usable_payee(self, env) -> None:
        """Section 72: new payee always requires approval."""
        http, _ = env
        response = await http.post(f"{API}/payees", json={"display_name": "Utility Co"})
        assert response.status_code == 201
        assert response.json()["status"] == "needs_approval"

        listed = (await http.get(f"{API}/payees")).json()["payees"]
        assert listed[0]["is_approved"] is False

    async def test_a_credential_shaped_secret_ref_is_refused(self, env) -> None:
        """Section 72: credentials never reach the graph."""
        http, _ = env
        response = await http.post(
            f"{API}/payees",
            json={"display_name": "Utility", "secret_ref": "4111111111111111"},
        )
        assert response.status_code == 422

    async def test_approving_makes_it_usable(self, env) -> None:
        http, _ = env
        payee_id = await _approved_payee(http)
        listed = (await http.get(f"{API}/payees")).json()["payees"]
        assert [p["is_approved"] for p in listed if p["id"] == payee_id] == [True]


class TestBills:
    async def test_recording_and_listing(self, env) -> None:
        http, _ = env
        payee_id = await _approved_payee(http)
        created = await http.post(
            f"{API}/bills",
            json={"payee_id": payee_id, "description": "Electricity", "amount": "89.1"},
        )
        assert created.status_code == 422  # 89.1 is ambiguous; two decimals required

        created = await http.post(
            f"{API}/bills",
            json={"payee_id": payee_id, "description": "Electricity", "amount": "89.10"},
        )
        assert created.status_code == 201
        body = created.json()
        assert body["amount"] == "89.10"
        assert isinstance(body["amount"], str)
        assert body["status"] == "due"
        assert body["is_payable"] is True

    async def test_a_bill_for_an_unknown_payee_is_404(self, env) -> None:
        http, _ = env
        response = await http.post(
            f"{API}/bills",
            json={"payee_id": "payee_nope", "description": "X", "amount": "1.00"},
        )
        assert response.status_code == 404

    async def test_a_payment_always_needs_approval(self, env) -> None:
        http, _ = env
        payee_id = await _approved_payee(http)
        bill = (
            await http.post(
                f"{API}/bills",
                json={"payee_id": payee_id, "description": "Electricity",
                      "amount": "89.10"},
            )
        ).json()

        response = await http.post(f"{API}/bills/{bill['id']}/payment")
        assert response.status_code == 201
        assert response.json()["status"] == "needs_approval"

    async def test_a_bill_is_settled_only_with_a_confirmation(self, env) -> None:
        http, _ = env
        payee_id = await _approved_payee(http)
        bill = (
            await http.post(
                f"{API}/bills",
                json={"payee_id": payee_id, "description": "Electricity",
                      "amount": "89.10"},
            )
        ).json()

        blank = await http.post(
            f"{API}/bills/{bill['id']}/settle", json={"external_reference": " "}
        )
        assert blank.status_code == 422

        settled = await http.post(
            f"{API}/bills/{bill['id']}/settle", json={"external_reference": "CONF-1"}
        )
        assert settled.status_code == 200
        assert settled.json()["status"] == "paid"
        assert settled.json()["external_reference"] == "CONF-1"


class TestWhoMayPay:
    async def test_hermes_cannot_record_a_payee_or_prepare_a_payment(self, env) -> None:
        """FINANCIAL_PAYMENT is Console-only; Hermes holds no path to money."""
        http, app = env
        payee_id = await _approved_payee(http)
        bill = (
            await http.post(
                f"{API}/bills",
                json={"payee_id": payee_id, "description": "Electricity",
                      "amount": "89.10"},
            )
        ).json()

        app.dependency_overrides[get_client] = lambda: HERMES
        denied = await http.post(f"{API}/payees", json={"display_name": "Other"})
        assert denied.status_code == 403
        assert denied.json()["code"] == "capability_denied"

        denied = await http.post(f"{API}/bills/{bill['id']}/payment")
        assert denied.status_code == 403

    async def test_hermes_can_still_see_what_is_owed(self, env) -> None:
        """Knowing a bill is due is not being able to pay it."""
        http, app = env
        payee_id = await _approved_payee(http)
        await http.post(
            f"{API}/bills",
            json={"payee_id": payee_id, "description": "Electricity", "amount": "89.10"},
        )
        app.dependency_overrides[get_client] = lambda: HERMES
        listed = await http.get(f"{API}/bills")
        assert listed.status_code == 200
        assert [b["description"] for b in listed.json()["bills"]] == ["Electricity"]
