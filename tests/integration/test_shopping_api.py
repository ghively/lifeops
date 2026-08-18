"""Shopping HTTP API (BUILD_SPEC sections 56, 60, 61, 88, 98).

Same discipline as ``test_calendar_email_api.py``: the real ``LifeOpsCore``
over in-memory repositories and a fake browser worker, reached through the
real FastAPI app. What is pinned here: routes, status codes, and that section
98's order — search, build a cart (no approval), submit for checkout (always
approval), approve, execute, independently verify — survives the HTTP
boundary. Also pins section 88: a Test button on the disabled browser
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
from lifeops.browser.fake import FakeBrowser
from lifeops.browser.service import BrowserProviderService
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

API = "/api/v1"
PRIMARY = "person_shopping_api_user"
HERMES_HEADERS = {"X-LifeOps-Client": "hermes-personal"}
CONSOLE_HEADERS = {"X-LifeOps-Client": "lifeops-console"}
CODING_HEADERS = {"X-LifeOps-Client": "claude-code"}


class StubContainer:
    """A Container with fakes in place of NornicDB and the browser provider."""

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

        self.fake_browser = FakeBrowser()
        self.browser = BrowserProviderService(
            config=self.config,
            secret_store=self.secret_store,
            factories={"browser": lambda settings, secrets: self.fake_browser},
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
            browser=self.browser,
            clock=self.clock,
            events=self.events,
        )

    def enable_browser(self) -> None:
        self.config.update_provider("browser", {"enabled": True})

    async def startup(self) -> None:
        person = Person(
            id=PRIMARY,
            display_name="Shopping API User",
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
    container.enable_browser()
    app = create_app(container=container, settings=container.settings)  # type: ignore[arg-type]
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://lifeops.test"
        ) as http_client:
            yield http_client, container


Env = tuple[httpx.AsyncClient, "StubContainer"]


class TestProviderHonesty:
    """Section 88: never fake success for a disabled provider, and never
    fake integration for one that is enabled but has no runtime."""

    async def test_testing_a_disabled_browser_provider_reports_not_configured(
        self, tmp_path: Path
    ) -> None:
        container = StubContainer(tmp_path)  # not enabled
        app = create_app(container=container, settings=container.settings)  # type: ignore[arg-type]
        async with LifespanManager(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://lifeops.test"
            ) as client:
                response = await client.post(f"{API}/config/providers/browser/test")
        assert response.status_code == 200
        assert response.json()["healthy"] is False

    async def test_testing_an_enabled_browser_provider_calls_the_adapter(
        self, env: Env
    ) -> None:
        # The fake reports healthy, proving the route actually reaches the
        # configured worker rather than the generic "no adapter" fallback.
        client, _ = env
        response = await client.post(f"{API}/config/providers/browser/test")
        assert response.status_code == 200
        assert response.json()["healthy"] is True


class TestSearchAndListRoutes:
    async def test_search_is_read_only(self, env: Env) -> None:
        client, _ = env
        response = await client.get(
            f"{API}/shopping/search",
            params={"query": "milk", "store": "fakemart"},
            headers=HERMES_HEADERS,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] > 0

    async def test_a_client_without_shopping_checkout_is_refused(self, env: Env) -> None:
        client, _ = env
        response = await client.get(
            f"{API}/shopping/search", params={"query": "milk"}, headers=CODING_HEADERS
        )
        assert response.status_code == 403


class TestShoppingListRoutes:
    async def _create_list(self, client: httpx.AsyncClient) -> dict[str, Any]:
        response = await client.post(
            f"{API}/shopping/lists",
            json={
                "title": "Weekly groceries",
                "store": "fakemart",
                "items": [{"name": "Milk", "quantity": "1 gal"}],
            },
            headers=HERMES_HEADERS,
        )
        assert response.status_code == 201
        return response.json()

    async def test_creating_a_list_needs_no_approval(self, env: Env) -> None:
        client, _ = env
        body = await self._create_list(client)
        assert body["status"] == "draft"
        assert body["items"][0]["name"] == "Milk"

    async def test_adding_items(self, env: Env) -> None:
        client, _ = env
        created = await self._create_list(client)
        response = await client.post(
            f"{API}/shopping/lists/{created['id']}/items",
            json={"items": [{"name": "Bread"}]},
            headers=HERMES_HEADERS,
        )
        assert response.status_code == 200
        assert [item["name"] for item in response.json()["items"]] == ["Milk", "Bread"]

    async def test_the_full_flow_builds_a_cart_and_checks_out_through_http(
        self, env: Env
    ) -> None:
        client, _ = env
        created = await self._create_list(client)
        list_id = created["id"]

        # R1: cart building needs no approval and executes in one call.
        build_response = await client.post(
            f"{API}/shopping/lists/{list_id}/build-cart", headers=HERMES_HEADERS
        )
        assert build_response.status_code == 200
        cart_action = build_response.json()
        assert cart_action["status"] == "executed"

        verify_cart = await client.post(
            f"{API}/actions/{cart_action['id']}/verify-externally", headers=HERMES_HEADERS
        )
        assert verify_cart.status_code == 200
        assert verify_cart.json()["status"] == "verified"

        built_list = await client.get(
            f"{API}/shopping/lists/{list_id}", headers=HERMES_HEADERS
        )
        assert built_list.json()["status"] == "cart_built"

        # R3: checkout must be approved before it can execute.
        checkout_response = await client.post(
            f"{API}/shopping/lists/{list_id}/checkout", headers=HERMES_HEADERS
        )
        assert checkout_response.status_code == 200
        checkout_action = checkout_response.json()
        assert checkout_action["status"] == "needs_approval"

        blocked = await client.post(
            f"{API}/actions/{checkout_action['id']}/execute", headers=HERMES_HEADERS
        )
        assert blocked.status_code == 409

        approvals = await client.get(f"{API}/approvals", headers=CONSOLE_HEADERS)
        approval_id = approvals.json()["approvals"][0]["id"]
        decided = await client.post(
            f"{API}/approvals/{approval_id}/decide",
            json={"approved": True},
            headers=CONSOLE_HEADERS,
        )
        assert decided.status_code == 200

        executed = await client.post(
            f"{API}/actions/{checkout_action['id']}/execute", headers=HERMES_HEADERS
        )
        assert executed.status_code == 200
        assert executed.json()["status"] == "executed"

        verified = await client.post(
            f"{API}/actions/{checkout_action['id']}/verify-externally", headers=HERMES_HEADERS
        )
        assert verified.status_code == 200
        assert verified.json()["status"] == "verified"

        final_list = await client.get(
            f"{API}/shopping/lists/{list_id}", headers=HERMES_HEADERS
        )
        assert final_list.json()["status"] == "verified"
        assert final_list.json()["order_reference"] is not None

    async def test_a_substitution_after_approval_invalidates_it_through_http(
        self, env: Env
    ) -> None:
        client, _ = env
        created = await self._create_list(client)
        list_id = created["id"]

        build_action = (
            await client.post(
                f"{API}/shopping/lists/{list_id}/build-cart", headers=HERMES_HEADERS
            )
        ).json()
        await client.post(
            f"{API}/actions/{build_action['id']}/verify-externally", headers=HERMES_HEADERS
        )
        checkout_action = (
            await client.post(
                f"{API}/shopping/lists/{list_id}/checkout", headers=HERMES_HEADERS
            )
        ).json()
        approvals = (await client.get(f"{API}/approvals", headers=CONSOLE_HEADERS)).json()
        approval_id = approvals["approvals"][0]["id"]
        await client.post(
            f"{API}/approvals/{approval_id}/decide",
            json={"approved": True},
            headers=CONSOLE_HEADERS,
        )

        # Section 57: a substitution applied after approval must not let the
        # old approval ride through.
        sub_response = await client.post(
            f"{API}/shopping/lists/{list_id}/substitutions",
            json={"item_name": "Milk", "substituted_with": "Oat milk"},
            headers=HERMES_HEADERS,
        )
        assert sub_response.status_code == 200

        blocked = await client.post(
            f"{API}/actions/{checkout_action['id']}/execute", headers=HERMES_HEADERS
        )
        assert blocked.status_code == 409

        fresh_approvals = (await client.get(f"{API}/approvals", headers=CONSOLE_HEADERS)).json()
        assert len(fresh_approvals["approvals"]) == 1
        assert fresh_approvals["approvals"][0]["action_id"] == checkout_action["id"]

    async def test_hermes_cannot_approve_its_own_checkout(self, env: Env) -> None:
        client, _ = env
        created = await self._create_list(client)
        list_id = created["id"]
        build_action = (
            await client.post(
                f"{API}/shopping/lists/{list_id}/build-cart", headers=HERMES_HEADERS
            )
        ).json()
        await client.post(
            f"{API}/actions/{build_action['id']}/verify-externally", headers=HERMES_HEADERS
        )
        await client.post(f"{API}/shopping/lists/{list_id}/checkout", headers=HERMES_HEADERS)
        approvals = (await client.get(f"{API}/approvals", headers=CONSOLE_HEADERS)).json()
        approval_id = approvals["approvals"][0]["id"]

        response = await client.post(
            f"{API}/approvals/{approval_id}/decide",
            json={"approved": True},
            headers=HERMES_HEADERS,
        )
        assert response.status_code == 403
