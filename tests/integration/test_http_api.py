"""LifeOps Core HTTP API — the interface LifeOps Console consumes.

These run against in-memory repositories: the point is the adapter's contract
(status codes, error shapes, secret redaction, capability headers), not
NornicDB, which is covered by the persistence suite.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager  # type: ignore[import-not-found]

from lifeops.api.http import create_app
from lifeops.clock import FrozenClock
from lifeops.config.service import ConfigurationService
from lifeops.core import LifeOpsCore
from lifeops.domain.people import Person
from lifeops.repositories.fakes import (
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
)
from lifeops.secrets.local_encrypted import InMemorySecretStore
from lifeops.settings import Settings
from lifeops.voice.fake import FakeTTSProvider
from lifeops.voice.service import VoiceService

PRIMARY = "person_api_user"


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
        self.voice = VoiceService(config=self.config, secret_store=self.secret_store)
        self.people = FakePersonRepository()
        self.preferences = FakePreferenceRepository()
        self.tasks = FakeTaskRepository()
        self.core = LifeOpsCore(
            people=self.people,
            preferences=self.preferences,
            tasks=self.tasks,
            clock=self.clock,
            # Mirrors Container: safe mode is read live from the config
            # document, which is how a Console toggle reaches other processes.
            safe_mode=lambda: self.config.get_system().safe_mode,
        )

    async def startup(self) -> None:
        await self.people.upsert(
            Person(
                id=PRIMARY,
                display_name="API User",
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
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    container = StubContainer(tmp_path)
    app = create_app(container=container, settings=container.settings)  # type: ignore[arg-type]
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://lifeops.test"
        ) as http_client:
            yield http_client


API = "/api/v1"


class TestHealth:
    async def test_root_health_needs_no_auth(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    async def test_component_health(self, client: httpx.AsyncClient) -> None:
        body = (await client.get(f"{API}/health")).json()
        assert body["components"]["nornicdb"]["healthy"] is True

    async def test_every_response_carries_a_trace_id(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.get("/health")
        assert response.headers.get("x-trace-id")


class TestPeople:
    async def test_get_me_returns_the_primary_person(
        self, client: httpx.AsyncClient
    ) -> None:
        body = (await client.get(f"{API}/people/me")).json()
        assert body["id"] == PRIMARY
        assert body["is_primary"] is True

    async def test_unknown_person_is_404_with_a_code(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.get(f"{API}/people/person_nobody")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"


class TestPreferences:
    async def test_save_then_read(self, client: httpx.AsyncClient) -> None:
        created = await client.post(
            f"{API}/preferences",
            json={"key": "scheduling.earliest", "value": "after 10"},
        )
        assert created.status_code == 201
        assert created.json()["is_current"] is True

        listed = (await client.get(f"{API}/preferences")).json()
        assert listed["total"] == 1
        assert listed["preferences"][0]["value"] == "after 10"

    async def test_history_survives_supersession(
        self, client: httpx.AsyncClient
    ) -> None:
        await client.post(
            f"{API}/preferences", json={"key": "scheduling.earliest", "value": "after 10"}
        )
        await client.post(
            f"{API}/preferences", json={"key": "scheduling.earliest", "value": "after 9"}
        )

        current = (await client.get(f"{API}/preferences")).json()
        assert current["total"] == 1

        history = (
            await client.get(
                f"{API}/preferences/history", params={"key": "scheduling.earliest"}
            )
        ).json()
        assert history["total"] == 2

    async def test_weaker_source_is_refused_with_409(
        self, client: httpx.AsyncClient
    ) -> None:
        await client.post(
            f"{API}/preferences",
            json={
                "key": "scheduling.earliest",
                "value": "after 10",
                "source_type": "user_explicit",
            },
        )
        response = await client.post(
            f"{API}/preferences",
            json={
                "key": "scheduling.earliest",
                "value": "after 6",
                "source_type": "website",
            },
        )
        assert response.status_code == 409
        assert response.json()["code"] == "conflict"


class TestTasks:
    async def test_create_and_list(self, client: httpx.AsyncClient) -> None:
        created = await client.post(f"{API}/tasks", json={"title": "Call dentist"})
        assert created.status_code == 201
        assert created.json()["state"] == "CAPTURED"

        listed = (await client.get(f"{API}/tasks")).json()
        assert listed["total"] == 1
        assert listed["by_state"] == {"CAPTURED": 1}

    async def test_legal_transition(self, client: httpx.AsyncClient) -> None:
        task_id = (await client.post(f"{API}/tasks", json={"title": "t"})).json()["id"]
        response = await client.patch(f"{API}/tasks/{task_id}", json={"state": "READY"})
        assert response.status_code == 200
        assert response.json()["state"] == "READY"

    async def test_illegal_transition_is_409_not_a_silent_write(
        self, client: httpx.AsyncClient
    ) -> None:
        task_id = (await client.post(f"{API}/tasks", json={"title": "t"})).json()["id"]
        response = await client.patch(
            f"{API}/tasks/{task_id}", json={"state": "COMPLETED"}
        )
        assert response.status_code == 409
        assert response.json()["code"] == "invalid_transition"

        # The task must be untouched, not partially updated.
        assert (await client.get(f"{API}/tasks/{task_id}")).json()["state"] == "CAPTURED"

    async def test_verification_gate_over_http(self, client: httpx.AsyncClient) -> None:
        task_id = (
            await client.post(
                f"{API}/tasks",
                json={"title": "Book electrician", "verification_required": True},
            )
        ).json()["id"]

        for state in ("READY", "EXECUTING"):
            assert (
                await client.patch(f"{API}/tasks/{task_id}", json={"state": state})
            ).status_code == 200

        refused = await client.patch(f"{API}/tasks/{task_id}", json={"state": "COMPLETED"})
        assert refused.status_code == 409
        assert refused.json()["code"] == "verification_required"

        await client.patch(f"{API}/tasks/{task_id}", json={"state": "VERIFYING"})
        completed = await client.patch(
            f"{API}/tasks/{task_id}",
            json={"state": "COMPLETED", "verification_evidence": "CONF-8891"},
        )
        assert completed.status_code == 200
        assert completed.json()["verification_state"] == "verified"

    async def test_filter_by_state(self, client: httpx.AsyncClient) -> None:
        await client.post(f"{API}/tasks", json={"title": "one"})
        second = (await client.post(f"{API}/tasks", json={"title": "two"})).json()["id"]
        await client.patch(f"{API}/tasks/{second}", json={"state": "READY"})

        listed = (await client.get(f"{API}/tasks", params={"state": "READY"})).json()
        assert [t["title"] for t in listed["tasks"]] == ["two"]


class TestClientIdentityHeader:
    async def test_declared_coding_client_cannot_write_preferences(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post(
            f"{API}/preferences",
            json={"key": "k", "value": "v"},
            headers={"X-LifeOps-Client": "claude-code"},
        )
        assert response.status_code == 403
        assert response.json()["code"] == "capability_denied"

    async def test_declared_coding_client_may_create_a_task(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post(
            f"{API}/tasks",
            json={"title": "from the coding agent"},
            headers={"X-LifeOps-Client": "claude-code"},
        )
        assert response.status_code == 201
        assert response.json()["created_by_client"] == "claude-code"


class TestConfiguration:
    async def test_lists_every_provider_with_its_schema(
        self, client: httpx.AsyncClient
    ) -> None:
        body = (await client.get(f"{API}/config/providers")).json()
        ids = {entry["definition"]["id"] for entry in body["providers"]}
        assert {
            "deepseek",
            "elevenlabs",
            "telegram",
            "calendar",
            "email",
            "browser",
            "telephony",
        } <= ids

    async def test_fresh_deployment_has_nothing_connected(
        self, client: httpx.AsyncClient
    ) -> None:
        body = (await client.get(f"{API}/config/providers")).json()
        for entry in body["providers"]:
            assert entry["status"]["state"] in {"not_configured", "disabled"}
            assert entry["status"]["enabled"] is False

    async def test_secret_is_accepted_and_never_returned(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.put(
            f"{API}/config/providers/elevenlabs",
            json={"api_key": "el-live-key", "voice_id": "voice-123"},
        )
        assert response.status_code == 200
        assert "el-live-key" not in response.text

        status = (await client.get(f"{API}/config/providers/elevenlabs")).json()
        assert status["status"]["secrets"]["api_key"]["configured"] is True
        assert "el-live-key" not in (await client.get(f"{API}/config/providers")).text

    async def test_invalid_value_is_422(self, client: httpx.AsyncClient) -> None:
        response = await client.put(
            f"{API}/config/providers/elevenlabs", json={"stability": 99}
        )
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"

    async def test_test_button_reports_honestly_that_no_adapter_exists(
        self, client: httpx.AsyncClient
    ) -> None:
        # A Test button that fakes success is worse than one that says "not yet".
        body = (await client.post(f"{API}/config/providers/telegram/test")).json()
        assert body["healthy"] is False
        assert "phase 1" in body["message"]

    async def test_elevenlabs_test_button_reports_not_configured_without_a_key(
        self, client: httpx.AsyncClient
    ) -> None:
        # ElevenLabs has a real adapter as of phase 5, but development and CI
        # never hold a credential (AGENTS.md), so the honest answer is "not
        # configured" rather than a live network call.
        body = (await client.post(f"{API}/config/providers/elevenlabs/test")).json()
        assert body["healthy"] is False
        assert "not enabled and fully configured" in body["message"]

    async def test_system_config_round_trip(self, client: httpx.AsyncClient) -> None:
        await client.put(
            f"{API}/config/system", json={"display_name": "Gene's LifeOps"}
        )
        assert (await client.get(f"{API}/config/system")).json()["display_name"] == (
            "Gene's LifeOps"
        )

    async def test_voice_mode_defaults_to_quick_cloud(
        self, client: httpx.AsyncClient
    ) -> None:
        assert (await client.get(f"{API}/config/system")).json()["voice_mode"] == (
            "quick_cloud"
        )

    async def test_voice_mode_round_trips(self, client: httpx.AsyncClient) -> None:
        response = await client.put(f"{API}/config/system", json={"voice_mode": "hybrid"})
        assert response.status_code == 200
        assert response.json()["voice_mode"] == "hybrid"
        assert (await client.get(f"{API}/config/system")).json()["voice_mode"] == "hybrid"

    async def test_invalid_voice_mode_is_422(self, client: httpx.AsyncClient) -> None:
        response = await client.put(f"{API}/config/system", json={"voice_mode": "telepathic"})
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"

    async def test_safe_mode_takes_effect_immediately(
        self, client: httpx.AsyncClient
    ) -> None:
        await client.put(f"{API}/config/system", json={"safe_mode": True})
        status = (await client.get(f"{API}/system/status")).json()
        assert status["components"]["safe_mode"] is True

    async def test_client_permissions_are_inspectable(
        self, client: httpx.AsyncClient
    ) -> None:
        body = (await client.get(f"{API}/config/clients")).json()
        by_id = {c["client_id"]: c for c in body["clients"]}
        assert "write_preference" not in by_id["claude-code"]["capabilities"]
        assert "write_preference" in by_id["hermes-personal"]["capabilities"]


@pytest.fixture
async def voice_client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    """A client with ElevenLabs enabled behind ``FakeTTSProvider``.

    This is the test double AGENTS.md requires: real ElevenLabs credentials
    never exist in development or CI, so every assertion here proves the
    plumbing (routing, streaming, error shapes) rather than the live API.
    """
    container = StubContainer(tmp_path)
    container.voice = VoiceService(
        config=container.config,
        secret_store=container.secret_store,
        factories={"elevenlabs": lambda _settings, _secrets: FakeTTSProvider()},
    )
    container.config.update_provider(
        "elevenlabs",
        {"api_key": "el-test-key", "voice_id": "voice-fake-1", "enabled": True},
    )
    app = create_app(container=container, settings=container.settings)  # type: ignore[arg-type]
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://lifeops.test"
        ) as http_client:
            yield http_client


class TestElevenLabsVoice:
    """BUILD_SPEC section 27's Test/Refresh/Preview buttons, behind the fake."""

    async def test_button_reports_healthy_once_enabled_and_configured(
        self, voice_client: httpx.AsyncClient
    ) -> None:
        body = (await voice_client.post(f"{API}/config/providers/elevenlabs/test")).json()
        assert body["healthy"] is True
        assert body["state"] == "healthy"

    async def test_discover_lists_voices_from_the_provider(
        self, voice_client: httpx.AsyncClient
    ) -> None:
        response = await voice_client.post(
            f"{API}/config/providers/elevenlabs/discover", params={"field": "voice_id"}
        )
        body = response.json()
        assert {opt["value"] for opt in body["options"]} == {"voice-fake-1", "voice-fake-2"}

    async def test_discover_lists_models_from_the_provider(
        self, voice_client: httpx.AsyncClient
    ) -> None:
        response = await voice_client.post(
            f"{API}/config/providers/elevenlabs/discover", params={"field": "model_id"}
        )
        body = response.json()
        assert {opt["value"] for opt in body["options"]} == {
            "model-fake-flash",
            "model-fake-multilingual",
        }

    async def test_preview_streams_playable_audio(
        self, voice_client: httpx.AsyncClient
    ) -> None:
        response = await voice_client.post(
            f"{API}/voice/tts/preview", json={"text": "hello from the preview button"}
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("audio/")
        assert b"hello from the preview button" in response.content

    async def test_preview_requires_non_empty_text(
        self, voice_client: httpx.AsyncClient
    ) -> None:
        response = await voice_client.post(f"{API}/voice/tts/preview", json={"text": ""})
        assert response.status_code == 422

    async def test_preview_fails_cleanly_without_configuration(
        self, client: httpx.AsyncClient
    ) -> None:
        # The default `client` fixture has no provider enabled at all.
        response = await client.post(f"{API}/voice/tts/preview", json={"text": "hi"})
        assert response.status_code == 400
        assert response.json()["code"] == "provider_not_configured"
