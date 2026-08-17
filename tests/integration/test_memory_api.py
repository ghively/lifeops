"""Memory HTTP API (BUILD_SPEC sections 42-47, 91).

These run against in-memory repositories: the point is the adapter's contract
— routes, status codes, stable error codes, capability enforcement — not the
memory ranking itself, which is covered by the unit and persistence suites.

The safety invariant under test is section 44: this surface can store, recall,
correct, and invalidate *observations*, and nothing here touches transactional
reality.
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
from lifeops.events import MEMORY_CHANGED, EventBus
from lifeops.policy import ClientIdentity, ClientRole
from lifeops.repositories.fakes import (
    FakeMemoryRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
)
from lifeops.secrets.local_encrypted import InMemorySecretStore
from lifeops.settings import Settings

PRIMARY = "person_memory_api_user"

API = "/api/v1"


class StubContainer:
    """A Container with fakes in place of NornicDB."""

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
        self.core = LifeOpsCore(
            people=self.people,
            preferences=self.preferences,
            tasks=self.tasks,
            memory=self.memories,
            clock=self.clock,
            events=self.events,
        )

    async def startup(self) -> None:
        await self.people.upsert(
            Person(
                id=PRIMARY,
                display_name="Memory API User",
                is_primary=True,
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
            )
        )

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
async def env(
    tmp_path: Path,
) -> AsyncIterator[tuple[httpx.AsyncClient, Any, StubContainer]]:
    container = StubContainer(tmp_path)
    app = create_app(container=container, settings=container.settings)  # type: ignore[arg-type]
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://lifeops.test"
        ) as http_client:
            yield http_client, app, container


async def _remember(
    client: httpx.AsyncClient, content: str, **fields: Any
) -> httpx.Response:
    return await client.post(
        f"{API}/memory", json={"content": content, "type": "semantic", **fields}
    )


class TestRemember:
    async def test_remember_stores_a_memory_with_provenance(
        self, env: tuple[httpx.AsyncClient, Any, StubContainer]
    ) -> None:
        client, _, _ = env
        response = await _remember(
            client, "Favourite coffee is a flat white", source_type="user_explicit"
        )
        assert response.status_code == 201
        body = response.json()
        assert body["id"]
        assert body["subject_id"] == PRIMARY
        assert body["type"] == "semantic"
        assert body["content"] == "Favourite coffee is a flat white"
        assert body["source_type"] == "user_explicit"
        assert body["valid_to"] is None
        assert body["supersedes"] is None

    async def test_unknown_type_is_rejected_422(
        self, env: tuple[httpx.AsyncClient, Any, StubContainer]
    ) -> None:
        client, _, _ = env
        response = await client.post(
            f"{API}/memory", json={"content": "Some durable fact", "type": "bogus"}
        )
        assert response.status_code == 422

    async def test_secret_like_content_is_refused(
        self, env: tuple[httpx.AsyncClient, Any, StubContainer]
    ) -> None:
        """Section 47: memory never stores secrets. Refused, not redacted."""
        client, _, _ = env
        response = await _remember(client, "password: hunter2")
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"

    async def test_remember_publishes_memory_changed(
        self, env: tuple[httpx.AsyncClient, Any, StubContainer]
    ) -> None:
        client, _, container = env
        queue = container.events.subscribe()
        response = await _remember(client, "Favourite coffee is a flat white")
        assert response.status_code == 201
        event = queue.get_nowait()
        assert event["type"] == MEMORY_CHANGED
        assert event["memory_id"] == response.json()["id"]


class TestListAndSearch:
    async def test_list_returns_memories_newest_visible(
        self, env: tuple[httpx.AsyncClient, Any, StubContainer]
    ) -> None:
        client, _, _ = env
        await _remember(client, "Favourite coffee is a flat white")
        body = (await client.get(f"{API}/memory")).json()
        assert body["total"] == 1
        assert body["memories"][0]["content"] == "Favourite coffee is a flat white"

    async def test_list_filters_by_type(
        self, env: tuple[httpx.AsyncClient, Any, StubContainer]
    ) -> None:
        client, _, _ = env
        await _remember(client, "Favourite coffee is a flat white")
        await _remember(client, "Discussed the mortgage renewal", type="episodic")
        body = (await client.get(f"{API}/memory", params={"type": "episodic"})).json()
        assert body["total"] == 1
        assert body["memories"][0]["type"] == "episodic"

    async def test_include_invalid_is_refused_loudly_not_silently_ignored(
        self, env: tuple[httpx.AsyncClient, Any, StubContainer]
    ) -> None:
        """Listing closed records has no core operation yet; the honest answer
        is a stable refusal that points at the per-memory history route."""
        client, _, _ = env
        memory = (await _remember(client, "Favourite coffee is a flat white")).json()
        await client.post(
            f"{API}/memory/{memory['id']}/invalidate", json={"reason": "no longer true"}
        )

        current = (await client.get(f"{API}/memory")).json()
        assert current["total"] == 0

        response = await client.get(f"{API}/memory", params={"include_invalid": True})
        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "validation_error"
        assert body["details"]["reason"] == "include_invalid_unsupported"

        # The closed record stays reachable through its history chain.
        history = (await client.get(f"{API}/memory/{memory['id']}/history")).json()
        assert history["total"] == 1
        assert history["history"][0]["valid_to"] is not None

    async def test_search_finds_by_content(
        self, env: tuple[httpx.AsyncClient, Any, StubContainer]
    ) -> None:
        client, _, _ = env
        await _remember(client, "Favourite coffee is a flat white")
        await _remember(client, "Discussed the mortgage renewal", type="episodic")
        body = (await client.get(f"{API}/memory/search", params={"q": "coffee"})).json()
        assert body["total"] == 1
        assert "coffee" in body["memories"][0]["content"]

    async def test_search_requires_a_query(
        self, env: tuple[httpx.AsyncClient, Any, StubContainer]
    ) -> None:
        client, _, _ = env
        assert (await client.get(f"{API}/memory/search")).status_code == 422


class TestGetAndHistory:
    async def test_get_one_memory(
        self, env: tuple[httpx.AsyncClient, Any, StubContainer]
    ) -> None:
        client, _, _ = env
        memory = (await _remember(client, "Favourite coffee is a flat white")).json()
        body = (await client.get(f"{API}/memory/{memory['id']}")).json()
        assert body["id"] == memory["id"]

    async def test_unknown_memory_is_404_with_a_code(
        self, env: tuple[httpx.AsyncClient, Any, StubContainer]
    ) -> None:
        client, _, _ = env
        response = await client.get(f"{API}/memory/mem_nope")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_unknown_history_is_404(
        self, env: tuple[httpx.AsyncClient, Any, StubContainer]
    ) -> None:
        client, _, _ = env
        response = await client.get(f"{API}/memory/mem_nope/history")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"


class TestCorrectAndInvalidate:
    async def test_correction_supersedes_and_preserves_history(
        self, env: tuple[httpx.AsyncClient, Any, StubContainer]
    ) -> None:
        """A correction closes the old record; it never edits in place (§45)."""
        client, _, _ = env
        original = (await _remember(client, "Favourite coffee is a flat white")).json()

        corrected = (
            await client.post(
                f"{API}/memory/{original['id']}/correct",
                json={"content": "Favourite coffee is now a cortado"},
            )
        ).json()
        assert corrected["id"] != original["id"]
        assert corrected["supersedes"] == original["id"]
        assert corrected["content"] == "Favourite coffee is now a cortado"

        history = (await client.get(f"{API}/memory/{corrected['id']}/history")).json()
        assert history["total"] == 2
        by_id = {entry["id"]: entry for entry in history["history"]}
        assert by_id[original["id"]]["valid_to"] is not None
        assert by_id[corrected["id"]]["valid_to"] is None

    async def test_invalidate_closes_the_window_with_a_reason(
        self, env: tuple[httpx.AsyncClient, Any, StubContainer]
    ) -> None:
        client, _, _ = env
        memory = (await _remember(client, "Favourite coffee is a flat white")).json()
        response = await client.post(
            f"{API}/memory/{memory['id']}/invalidate", json={"reason": "user said so"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["valid_to"] is not None
        assert body["invalidation_reason"] == "user said so"

    async def test_invalidate_requires_a_reason(
        self, env: tuple[httpx.AsyncClient, Any, StubContainer]
    ) -> None:
        client, _, _ = env
        memory = (await _remember(client, "Favourite coffee is a flat white")).json()
        response = await client.post(f"{API}/memory/{memory['id']}/invalidate", json={})
        assert response.status_code == 422

    async def test_unknown_invalidate_is_404(
        self, env: tuple[httpx.AsyncClient, Any, StubContainer]
    ) -> None:
        client, _, _ = env
        response = await client.post(
            f"{API}/memory/mem_nope/invalidate", json={"reason": "gone"}
        )
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_unknown_correct_is_404(
        self, env: tuple[httpx.AsyncClient, Any, StubContainer]
    ) -> None:
        client, _, _ = env
        response = await client.post(
            f"{API}/memory/mem_nope/correct", json={"content": "replacement"}
        )
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"


class TestCapabilities:
    """Section 44's enforcement point: memory ops are capability-gated like
    every other state change, so an unprivileged client observes nothing."""

    async def test_capability_denial_is_403_with_a_stable_code(
        self, env: tuple[httpx.AsyncClient, Any, StubContainer]
    ) -> None:
        client, app, _ = env
        powerless = ClientIdentity(
            client_id="no-caps",
            role=ClientRole.ENGINEERING_ASSISTANT,
            display_name="No capabilities",
            capabilities=frozenset(),
        )
        app.dependency_overrides[get_client] = lambda: powerless
        try:
            for response in (
                await client.get(f"{API}/memory"),
                await client.get(f"{API}/memory/search", params={"q": "coffee"}),
                await _remember(client, "Favourite coffee is a flat white"),
            ):
                assert response.status_code == 403
                assert response.json()["code"] == "capability_denied"
        finally:
            app.dependency_overrides.clear()
