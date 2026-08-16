"""Phase 1 Console-foundation HTTP surface (BUILD_SPEC section 90).

Covers the routes added in Phase 1 against in-memory repositories:

  * console authentication (disabled by default, enforced once a password is set)
  * the server-served task transition table
  * universal search
  * the ephemeral activity buffer
  * the console log sink
  * the WebSocket event stream
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager  # type: ignore[import-not-found]
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from lifeops.api.http import create_app
from lifeops.auth import TOKEN_TTL_S, ConsoleAuth
from lifeops.clock import FrozenClock
from lifeops.config.service import ConfigurationService
from lifeops.core import LifeOpsCore
from lifeops.domain.people import Person
from lifeops.domain.tasks import transition_table
from lifeops.events import EventBus
from lifeops.observability.activity import attach_activity_buffer, detach_activity_buffer
from lifeops.repositories.fakes import (
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
)
from lifeops.secrets.local_encrypted import InMemorySecretStore
from lifeops.settings import Settings

PRIMARY = "person_console_user"
PASSWORD = "open sesame"
API = "/api/v1"


class StubContainer:
    """A Container with fakes in place of NornicDB."""

    def __init__(self, tmp_path: Path, *, password: str | None = None) -> None:
        self.settings = Settings(state_dir=tmp_path / "state")
        self.settings.ensure_dirs()
        self.clock = FrozenClock()
        self.secret_store = InMemorySecretStore()
        self.config = ConfigurationService(
            config_dir=self.settings.config_dir,
            secret_store=self.secret_store,
            clock=self.clock,
        )
        self.auth = ConsoleAuth(
            secret_store=self.secret_store, settings=self.settings, clock=self.clock
        )
        if password is not None:
            self.auth.set_password(password)
        self.events = EventBus()
        self.activity = attach_activity_buffer()
        self.people = FakePersonRepository()
        self.preferences = FakePreferenceRepository()
        self.tasks = FakeTaskRepository()
        self.core = LifeOpsCore(
            people=self.people,
            preferences=self.preferences,
            tasks=self.tasks,
            clock=self.clock,
            events=self.events,
        )

    async def startup(self) -> None:
        await self.people.upsert(
            Person(
                id=PRIMARY,
                display_name="Console User",
                is_primary=True,
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
            )
        )

    async def shutdown(self) -> None:
        detach_activity_buffer(self.activity)

    async def health(self) -> dict[str, Any]:
        return {"lifeops_core": {"healthy": True, "detail": "running"}}


@pytest.fixture
def container(tmp_path: Path) -> StubContainer:
    return StubContainer(tmp_path)


@pytest.fixture
def secure_container(tmp_path: Path) -> StubContainer:
    return StubContainer(tmp_path, password=PASSWORD)


@pytest.fixture
async def client(container: StubContainer) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(container=container, settings=container.settings)  # type: ignore[arg-type]
    async with LifespanManager(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://lifeops.test"
    ) as http_client:
        yield http_client


@pytest.fixture
async def secure_client(
    secure_container: StubContainer,
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        container=secure_container,  # type: ignore[arg-type]
        settings=secure_container.settings,
    )
    async with LifespanManager(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://lifeops.test"
    ) as http_client:
        yield http_client


async def _login(client: httpx.AsyncClient, password: str = PASSWORD) -> str:
    response = await client.post(f"{API}/auth/login", json={"password": password})
    assert response.status_code == 200
    token = response.json()["token"]
    assert isinstance(token, str)
    return token


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- auth disabled (the loopback default) ------------------------------------


class TestAuthDisabled:
    async def test_routes_work_without_a_token(self, client: httpx.AsyncClient) -> None:
        assert (await client.get(f"{API}/people/me")).status_code == 200
        assert (await client.get(f"{API}/tasks")).status_code == 200

    async def test_login_reports_auth_disabled(self, client: httpx.AsyncClient) -> None:
        body = (await client.post(f"{API}/auth/login", json={"password": "any"})).json()
        assert body == {"auth_enabled": False, "token": None, "expires_at": None}

    async def test_me_reports_auth_disabled(self, client: httpx.AsyncClient) -> None:
        body = (await client.get(f"{API}/auth/me")).json()
        assert body["auth_enabled"] is False
        assert body["client_id"] == "lifeops-console"


# --- auth enabled ---------------------------------------------------------------


class TestAuthEnabled:
    async def test_api_routes_require_a_token(
        self, secure_client: httpx.AsyncClient
    ) -> None:
        for path in ("/people/me", "/tasks", "/search?q=x", "/system/status"):
            response = await secure_client.get(f"{API}{path}")
            assert response.status_code == 401, path
            assert response.json()["code"] == "authentication_required"

    async def test_health_and_login_stay_open(
        self, secure_client: httpx.AsyncClient
    ) -> None:
        assert (await secure_client.get("/health")).status_code == 200
        assert (await secure_client.get(f"{API}/health")).status_code == 200
        response = await secure_client.post(f"{API}/auth/login", json={"password": "x"})
        assert response.status_code == 401  # wrong password, but reachable

    async def test_wrong_password_is_refused(
        self, secure_client: httpx.AsyncClient
    ) -> None:
        response = await secure_client.post(
            f"{API}/auth/login", json={"password": "wrong"}
        )
        assert response.status_code == 401
        assert response.json()["code"] == "invalid_credentials"
        assert PASSWORD not in response.text

    async def test_login_then_bearer_token_works(
        self, secure_client: httpx.AsyncClient
    ) -> None:
        token = await _login(secure_client)
        response = await secure_client.get(f"{API}/people/me", headers=_bearer(token))
        assert response.status_code == 200
        assert response.json()["id"] == PRIMARY

    async def test_auth_me_identifies_the_console(
        self, secure_client: httpx.AsyncClient
    ) -> None:
        assert (await secure_client.get(f"{API}/auth/me")).status_code == 401
        token = await _login(secure_client)
        body = (await secure_client.get(f"{API}/auth/me", headers=_bearer(token))).json()
        assert body == {
            "client_id": "lifeops-console",
            "display_name": "LifeOps Console",
            "auth_enabled": True,
        }

    async def test_expired_token_is_rejected(
        self, secure_client: httpx.AsyncClient, secure_container: StubContainer
    ) -> None:
        token = await _login(secure_client)
        secure_container.clock.advance(TOKEN_TTL_S + 1)
        response = await secure_client.get(f"{API}/tasks", headers=_bearer(token))
        assert response.status_code == 401

    async def test_cors_preflight_is_not_challenged(
        self, secure_client: httpx.AsyncClient
    ) -> None:
        # Browsers preflight without Authorization; a 401 here would break the
        # Console's every request.
        response = await secure_client.options(
            f"{API}/tasks",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200


# --- setting the password (the only way auth turns on) -------------------------


class TestSetPassword:
    async def test_first_setup_needs_no_current_password(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post(
            f"{API}/auth/password", json={"new_password": "correct horse"}
        )
        assert response.status_code == 200
        assert response.json() == {"auth_enabled": True}

        # Auth is now on: routes demand a token, and the new password gets one.
        assert (await client.get(f"{API}/tasks")).status_code == 401
        token = await _login(client, "correct horse")
        assert (await client.get(f"{API}/tasks", headers=_bearer(token))).status_code == 200

    async def test_change_requires_the_current_password(
        self, secure_client: httpx.AsyncClient
    ) -> None:
        token = await _login(secure_client)
        for body in (
            {"new_password": "a new password"},
            {"current_password": "wrong", "new_password": "a new password"},
        ):
            response = await secure_client.post(
                f"{API}/auth/password", json=body, headers=_bearer(token)
            )
            assert response.status_code == 401
            assert response.json()["code"] == "invalid_credentials"

    async def test_change_with_current_password(
        self, secure_client: httpx.AsyncClient
    ) -> None:
        token = await _login(secure_client)
        response = await secure_client.post(
            f"{API}/auth/password",
            json={"current_password": PASSWORD, "new_password": "a new password"},
            headers=_bearer(token),
        )
        assert response.status_code == 200
        # The old password no longer logs in; the new one does.
        assert (
            await secure_client.post(f"{API}/auth/login", json={"password": PASSWORD})
        ).status_code == 401
        await _login(secure_client, "a new password")

    async def test_short_password_is_rejected(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            f"{API}/auth/password", json={"new_password": "short"}
        )
        assert response.status_code == 422

    async def test_password_never_appears_in_a_response(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post(
            f"{API}/auth/password", json={"new_password": "correct horse"}
        )
        assert "correct horse" not in response.text


# --- task transitions ------------------------------------------------------------


class TestTransitions:
    async def test_serves_the_domain_state_machine(
        self, client: httpx.AsyncClient
    ) -> None:
        body = (await client.get(f"{API}/tasks/transitions")).json()
        assert body["transitions"] == transition_table()
        assert body["transitions"]["COMPLETED"] == []
        assert "READY" in body["transitions"]["CAPTURED"]

    async def test_not_swallowed_by_the_task_id_route(
        self, client: httpx.AsyncClient
    ) -> None:
        # Route-ordering regression: /tasks/transitions must not be parsed as
        # a task with id "transitions".
        body = (await client.get(f"{API}/tasks/transitions")).json()
        assert "transitions" in body


# --- universal search ------------------------------------------------------------


class TestSearch:
    async def test_groups_results_by_domain(self, client: httpx.AsyncClient) -> None:
        await client.post(f"{API}/people", json={"display_name": "Tori Hively"})
        await client.post(
            f"{API}/preferences", json={"key": "coffee.roast", "value": "light roast"}
        )
        await client.post(f"{API}/tasks", json={"title": "Repair living room outlet"})

        body = (await client.get(f"{API}/search", params={"q": "roast"})).json()
        assert [p["key"] for p in body["preferences"]] == ["coffee.roast"]
        assert body["people"] == [] and body["tasks"] == []

        body = (await client.get(f"{API}/search", params={"q": "tori"})).json()
        assert [p["display_name"] for p in body["people"]] == ["Tori Hively"]

        body = (await client.get(f"{API}/search", params={"q": "outlet"})).json()
        assert [t["title"] for t in body["tasks"]] == ["Repair living room outlet"]

    async def test_missing_query_is_422(self, client: httpx.AsyncClient) -> None:
        assert (await client.get(f"{API}/search")).status_code == 422


# --- activity (ephemeral) --------------------------------------------------------


class TestActivity:
    async def test_recent_operations_appear(self, client: httpx.AsyncClient) -> None:
        created = await client.post(f"{API}/tasks", json={"title": "Water plants"})
        task_id = created.json()["id"]

        body = (await client.get(f"{API}/system/activity")).json()
        assert body["ephemeral"] is True
        task_ops = [e for e in body["entries"] if e["operation"] == "task.create"]
        assert task_ops and task_ops[0]["task_id"] == task_id
        assert task_ops[0]["result"] == "ok"

    async def test_empty_when_nothing_has_happened(
        self, client: httpx.AsyncClient
    ) -> None:
        body = (await client.get(f"{API}/system/activity")).json()
        assert body == {"entries": [], "ephemeral": True}


# --- console log sink ------------------------------------------------------------


class TestLogSink:
    async def test_entries_are_accepted_and_relogged(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger="lifeops.console"):
            response = await client.post(
                f"{API}/system/logs",
                json={
                    "entries": [
                        {"level": "error", "message": "render blew up", "ts": "t1"},
                        {
                            "level": "warn",
                            "message": "token refresh",
                            "context": {"token": "sekrit", "page": "tasks"},
                        },
                    ]
                },
            )
        assert response.status_code == 202
        assert response.json() == {"accepted": 2}

        records = [r for r in caplog.records if r.name == "lifeops.console"]
        assert [r.levelno for r in records] == [logging.ERROR, logging.WARNING]
        # Context fields on the redaction list never reach the log stream.
        assert records[1].context == {"token": "<redacted>", "page": "tasks"}

    async def test_unknown_level_falls_back_to_info(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG, logger="lifeops.console"):
            await client.post(
                f"{API}/system/logs",
                json={"entries": [{"level": "verbose", "message": "hi"}]},
            )
        assert caplog.records[-1].levelno == logging.INFO

    async def test_batch_size_is_bounded(self, client: httpx.AsyncClient) -> None:
        entries = [{"level": "info", "message": f"m{i}"} for i in range(101)]
        response = await client.post(f"{API}/system/logs", json={"entries": entries})
        assert response.status_code == 422


# --- websocket events ------------------------------------------------------------


class TestEventStream:
    def test_mutations_are_pushed_to_subscribers(self, tmp_path: Path) -> None:
        container = StubContainer(tmp_path)
        app = create_app(container=container, settings=container.settings)  # type: ignore[arg-type]
        with TestClient(app) as tc, tc.websocket_connect(f"{API}/events") as ws:
            created = tc.post(f"{API}/tasks", json={"title": "live update"})
            assert created.status_code == 201
            event = ws.receive_json()
            assert event["type"] == "task_changed"
            assert event["task_id"] == created.json()["id"]

    def test_config_changes_are_pushed(self, tmp_path: Path) -> None:
        container = StubContainer(tmp_path)
        app = create_app(container=container, settings=container.settings)  # type: ignore[arg-type]
        with TestClient(app) as tc, tc.websocket_connect(f"{API}/events") as ws:
            tc.put(f"{API}/config/system", json={"display_name": "Gene's LifeOps"})
            assert ws.receive_json()["type"] == "config_changed"

    def test_auth_enabled_requires_a_token(self, tmp_path: Path) -> None:
        container = StubContainer(tmp_path, password=PASSWORD)
        app = create_app(container=container, settings=container.settings)  # type: ignore[arg-type]
        with TestClient(app) as tc:
            with (
                pytest.raises(WebSocketDisconnect) as err,
                tc.websocket_connect(f"{API}/events"),
            ):
                pass
            assert err.value.code == 4401

            token = tc.post(f"{API}/auth/login", json={"password": PASSWORD}).json()[
                "token"
            ]
            with tc.websocket_connect(f"{API}/events?token={token}") as ws:
                tc.post(f"{API}/tasks", json={"title": "x"}, headers=_bearer(token))
                assert ws.receive_json()["type"] == "task_changed"
