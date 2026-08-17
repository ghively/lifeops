"""Voice acceptance: same Hermes, same LifeOps state, regardless of modality
(BUILD_SPEC section 95's "verify same Hermes and same LifeOps state across
voice/text").

This repository does not contain a working local voice runtime (phase 6 ships
adapters that honestly report a missing runtime, not a working microphone
pipeline — see ``tests/unit/test_voice.py``) or Hermes itself
(HERMES_INTEGRATION.md). What phase 6 *can* prove from inside this repo is
the architectural claim the acceptance scenario is really about: voice adds
nothing but audio in front of and behind the same tool calls a typed session
already made (BUILD_SPEC section 32's Voice Bridge diagram — ASR feeds
transcribed text to "the same Hermes runtime", which reaches LifeOps the
same way a text session does). Concretely: whichever modality the user is
speaking through, Hermes reaches LifeOps state over MCP; a human reading or
writing through the Console reaches the identical state over HTTP. Neither
``VoiceService`` nor the local ASR/TTS adapters hold a preference, task, or
any other piece of LifeOps state of their own (asserted below) — voice is
strictly a front-end, never a second copy of the world.

So this test saves a preference over MCP with Hermes's own client identity —
the path a transcribed voice utterance and a typed message reach LifeOps
through identically — and reads it back over the Console's HTTP surface, and
the reverse, against one shared ``LifeOpsCore``. If voice state were ever
modality-local, one of these two directions would fail to see the other's
write.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from asgi_lifespan import LifespanManager  # type: ignore[import-not-found]
from mcp.server.mcpserver import MCPServer

from lifeops.api.http import create_app
from lifeops.clock import FrozenClock
from lifeops.config.service import ConfigurationService
from lifeops.container import Container
from lifeops.core import LifeOpsCore
from lifeops.domain.people import Person
from lifeops.events import EventBus
from lifeops.mcp.server import build_server
from lifeops.policy.capabilities import HERMES
from lifeops.repositories.fakes import (
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
)
from lifeops.secrets.local_encrypted import InMemorySecretStore
from lifeops.settings import Settings

PRIMARY = "person_voice_shared_state_user"
API = "/api/v1"

VOICE_KEY = "scheduling.earliest_appointment_time"
VOICE_VALUE = "Nothing before ten, I said that on a call."

TEXT_KEY = "scheduling.preferred_mechanic"
TEXT_VALUE = "Always the same shop on 5th."


class StubContainer:
    """A Container with fakes in place of NornicDB (same shape as
    ``tests/integration/test_memory_api.py``'s), shared between the HTTP app
    and the in-process MCP server below so both surfaces read and write
    through one ``LifeOpsCore``/repository set — exactly as the real
    ``Container`` does within a single LifeOps Core process."""

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
                display_name="Voice Shared State User",
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
) -> AsyncIterator[tuple[httpx.AsyncClient, MCPServer, StubContainer]]:
    """One container backing both surfaces: an HTTP client (the Console —
    what a person reads and writes through, in text) and an in-process MCP
    server bound to Hermes's own client identity (what Hermes calls whether
    the user is currently speaking or typing to it)."""
    container = StubContainer(tmp_path)
    app = create_app(container=container, settings=container.settings)  # type: ignore[arg-type]
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://lifeops.test"
        ) as http_client:
            mcp_server = build_server(cast(Container, container), HERMES)
            yield http_client, mcp_server, container


async def _call_tool(server: MCPServer, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = await server.call_tool(tool, arguments)
    (content,) = result.content
    return json.loads(content.text)


class TestPreferenceStateIsSharedAcrossVoiceAndText:
    async def test_saved_through_hermes_is_visible_through_the_console(
        self, env: tuple[httpx.AsyncClient, MCPServer, StubContainer]
    ) -> None:
        http_client, mcp_server, _container = env

        # Stands in for a voice session: the user said this over the
        # microphone, local ASR transcribed it, and Hermes called the same
        # save_preference tool it would call from a typed message.
        saved = await _call_tool(
            mcp_server,
            "save_preference",
            {"key": VOICE_KEY, "value": VOICE_VALUE, "source_type": "user_explicit"},
        )
        assert saved["ok"] is True

        # The Console — a person reading LifeOps state in text — sees it.
        response = await http_client.get(f"{API}/preferences")
        assert response.status_code == 200
        keys = {p["key"]: p["value"] for p in response.json()["preferences"]}
        assert keys[VOICE_KEY] == VOICE_VALUE

    async def test_saved_through_the_console_is_visible_through_hermes(
        self, env: tuple[httpx.AsyncClient, MCPServer, StubContainer]
    ) -> None:
        http_client, mcp_server, _container = env

        # A person typing directly into the Console.
        response = await http_client.post(
            f"{API}/preferences", json={"key": TEXT_KEY, "value": TEXT_VALUE}
        )
        assert response.status_code == 201

        # Whether the user's *next* turn with Hermes happens by voice or by
        # text, Hermes reaches this same tool and this same state.
        read_back = await _call_tool(mcp_server, "get_preferences", {})
        values = {p["key"]: p["value"] for p in read_back["preferences"]}
        assert values[TEXT_KEY] == TEXT_VALUE

    async def test_a_correction_made_through_hermes_supersedes_for_the_console_too(
        self, env: tuple[httpx.AsyncClient, MCPServer, StubContainer]
    ) -> None:
        """Exercises the temporal rule (preferences are never overwritten,
        only superseded) across the same voice/text boundary, not just a
        single write."""
        http_client, mcp_server, _container = env

        await _call_tool(
            mcp_server, "save_preference", {"key": VOICE_KEY, "value": "before ten is fine"}
        )
        await _call_tool(
            mcp_server, "save_preference", {"key": VOICE_KEY, "value": VOICE_VALUE}
        )

        response = await http_client.get(f"{API}/preferences")
        current = [p for p in response.json()["preferences"] if p["key"] == VOICE_KEY]
        assert len(current) == 1
        assert current[0]["value"] == VOICE_VALUE

        history_response = await http_client.get(
            f"{API}/preferences/history", params={"key": VOICE_KEY}
        )
        assert len(history_response.json()["history"]) == 2


class TestVoiceModuleHoldsNoLifeOpsStateOfItsOwn:
    """The structural half of "the state is LifeOps's, not the modality's":
    nothing under ``lifeops.voice`` imports the preference or task domain, so
    there is no code path by which a voice component could hold a second,
    modality-local copy of state that the tests above would not catch."""

    _FORBIDDEN = re.compile(r"lifeops\.(domain\.(preferences|tasks)|repositories)")

    def test_no_voice_module_imports_lifeops_state_domains(self) -> None:
        voice_dir = Path(__file__).resolve().parents[2] / "core" / "lifeops" / "voice"
        offenders = [
            path.name
            for path in sorted(voice_dir.glob("*.py"))
            if self._FORBIDDEN.search(path.read_text())
        ]
        assert offenders == []
