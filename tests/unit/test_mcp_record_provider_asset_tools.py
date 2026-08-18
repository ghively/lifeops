"""Unit tests for ``record_provider``/``record_asset`` (BUILD_SPEC section 51)
after they gained upsert-with-history semantics.

Before this, both tools only ever called ``create_entity``, which refuses a
duplicate name outright — so an agent that had already recorded a provider
had no way to record a newly-learned fact about it (a changed phone number,
say) except by erroring. Both now route through
``LifeOpsCore.record_or_update_entity``: create on the first call, revise
(with tracked history, section 16) on every call after that. Same
``real LifeOpsCore + MCPServer`` pattern as ``test_mcp_world_tools.py``.
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from mcp.server.mcpserver import MCPServer

from lifeops.clock import FrozenClock
from lifeops.container import Container
from lifeops.core import LifeOpsCore
from lifeops.domain.people import Person
from lifeops.mcp.server import build_server
from lifeops.policy import ClientIdentity, ClientRole
from lifeops.policy.capabilities import HERMES
from lifeops.repositories.fakes import (
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
    FakeWorldRepository,
)
from tests.conftest import PRIMARY_PERSON_ID

TS = "2026-01-01T00:00:00Z"

NO_WRITE_WORLD_CLIENT = ClientIdentity(
    client_id="no-write-world",
    role=ClientRole.INTERACTIVE_ASSISTANT,
    display_name="Cannot write world",
    capabilities=frozenset(),
)


class _StubContainer:
    def __init__(self, core: LifeOpsCore, clock: FrozenClock) -> None:
        self.core = core
        self.clock = clock

    async def startup(self) -> None:  # pragma: no cover - lifespan not entered
        pass

    async def shutdown(self) -> None:  # pragma: no cover - lifespan not entered
        pass


def _build(core: LifeOpsCore, clock: FrozenClock, client: ClientIdentity) -> MCPServer:
    return build_server(cast(Container, _StubContainer(core, clock)), client)


async def _call(server: MCPServer, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = await server.call_tool(tool, arguments)
    (content,) = result.content
    return json.loads(content.text)


@pytest.fixture
async def core(clock: FrozenClock) -> LifeOpsCore:
    people = FakePersonRepository()
    await people.upsert(
        Person(
            id=PRIMARY_PERSON_ID, display_name="Test User", is_primary=True,
            created_at=TS, updated_at=TS,
        )
    )
    return LifeOpsCore(
        people=people,
        preferences=FakePreferenceRepository(),
        tasks=FakeTaskRepository(),
        world=FakeWorldRepository(),
        clock=clock,
    )


@pytest.fixture
def hermes_server(core: LifeOpsCore, clock: FrozenClock) -> MCPServer:
    return _build(core, clock, HERMES)


class TestRecordProvider:
    async def test_first_call_creates(self, hermes_server: MCPServer) -> None:
        payload = await _call(
            hermes_server,
            "record_provider",
            {"display_name": "ABC Electric", "facts": {"phone": "555-0100"}},
        )
        assert payload["ok"] is True
        assert payload["provider"]["facts"] == {"phone": "555-0100"}

    async def test_a_second_call_for_the_same_name_revises_rather_than_errors(
        self, hermes_server: MCPServer
    ) -> None:
        await _call(
            hermes_server,
            "record_provider",
            {"display_name": "ABC Electric", "facts": {"phone": "555-0100"}},
        )
        revised = await _call(
            hermes_server,
            "record_provider",
            {"display_name": "ABC Electric", "facts": {"phone": "555-9999"}},
        )
        assert revised["ok"] is True
        assert revised["provider"]["facts"] == {"phone": "555-9999"}

    async def test_the_revision_is_recorded_in_history(
        self, hermes_server: MCPServer, core: LifeOpsCore
    ) -> None:
        await _call(
            hermes_server,
            "record_provider",
            {"display_name": "ABC Electric", "facts": {"phone": "555-0100"}},
        )
        await _call(
            hermes_server,
            "record_provider",
            {"display_name": "ABC Electric", "facts": {"phone": "555-9999"}},
        )
        history = await core.entity_history(HERMES, entity_id="provider_abc_electric")
        phone_versions = [f for f in history.fact_history if f.key == "phone"]
        assert {v.value for v in phone_versions} == {"555-0100", "555-9999"}

    async def test_unrelated_facts_survive_a_revision(
        self, hermes_server: MCPServer
    ) -> None:
        await _call(
            hermes_server,
            "record_provider",
            {
                "display_name": "ABC Electric",
                "facts": {"phone": "555-0100", "trade": "electrician"},
            },
        )
        revised = await _call(
            hermes_server,
            "record_provider",
            {"display_name": "ABC Electric", "facts": {"phone": "555-9999"}},
        )
        assert revised["provider"]["facts"] == {
            "phone": "555-9999", "trade": "electrician",
        }

    async def test_a_client_without_write_world_is_denied(
        self, core: LifeOpsCore, clock: FrozenClock
    ) -> None:
        server = _build(core, clock, NO_WRITE_WORLD_CLIENT)
        payload = await _call(
            server, "record_provider", {"display_name": "ABC Electric"}
        )
        assert payload["ok"] is False
        assert payload["error"] == "capability_denied"


class TestRecordAsset:
    async def test_first_call_creates(self, hermes_server: MCPServer) -> None:
        payload = await _call(
            hermes_server,
            "record_asset",
            {"display_name": "Land Rover", "facts": {"mileage": "100000"}},
        )
        assert payload["ok"] is True
        assert payload["asset"]["facts"] == {"mileage": "100000"}

    async def test_a_second_call_for_the_same_name_revises_rather_than_errors(
        self, hermes_server: MCPServer
    ) -> None:
        await _call(
            hermes_server,
            "record_asset",
            {"display_name": "Land Rover", "facts": {"mileage": "100000"}},
        )
        revised = await _call(
            hermes_server,
            "record_asset",
            {"display_name": "Land Rover", "facts": {"mileage": "108900"}},
        )
        assert revised["ok"] is True
        assert revised["asset"]["facts"] == {"mileage": "108900"}
