"""Unit tests for the Phase 3 world MCP tools (BUILD_SPEC sections 50, 92).

Like the Phase 2 memory tools, these run against a real ``LifeOpsCore`` over
in-memory repositories — only the ``Container`` is duck-typed, because the MCP
layer needs just ``core`` and ``clock``. Stubbing the core here would prove
only that the tools agree with the stub.

What is proven:

  * the four tools are listed alongside the earlier phases' tools;
  * each tool's happy path returns the documented shape (canonical IDs, the
    entity's facts, one-hop neighbourhoods, history entries);
  * an unknown entity id comes back as ``{"ok": false, "error": "not_found"}``
    *data*, never a raised protocol error a model would retry blindly;
  * a client without ``read_world`` gets ``capability_denied`` as data from
    all four tools — READ_WORLD gates every one of them.
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from mcp.server.mcpserver import MCPServer

from lifeops.clock import FrozenClock
from lifeops.container import Container
from lifeops.core import LifeOpsCore
from lifeops.domain.memory import MemoryRecord, MemorySource, MemoryType
from lifeops.domain.people import Person
from lifeops.domain.world import WorldEntity, WorldEntityType, WorldRelationship
from lifeops.mcp.server import build_server
from lifeops.policy import Capability, ClientIdentity, ClientRole
from lifeops.repositories.fakes import (
    FakeMemoryRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
    FakeWorldRepository,
)
from tests.conftest import PRIMARY_PERSON_ID

#: A client holding exactly the capabilities the world tools read through.
#: READ_MEMORY is included because entity history *is* the memory record in
#: Phase 3; the test below pins what a client without it sees instead.
WORLD_CLIENT = ClientIdentity(
    client_id="world-client",
    role=ClientRole.INTERACTIVE_ASSISTANT,
    display_name="World client",
    capabilities=frozenset({Capability.READ_WORLD, Capability.READ_MEMORY}),
)

#: A client with no read capability at all.
READ_LESS_CLIENT = ClientIdentity(
    client_id="read-less",
    role=ClientRole.INTERACTIVE_ASSISTANT,
    display_name="Read-less client",
    capabilities=frozenset(),
)

PROVIDER_ID = "provider_abc_electric"
HOUSEHOLD_ID = "household_main"

TS = "2026-01-01T00:00:00Z"


class _StubContainer:
    """Duck-typed Container: the MCP layer needs only ``core`` and ``clock``."""

    def __init__(self, core: LifeOpsCore, clock: FrozenClock) -> None:
        self.core = core
        self.clock = clock

    async def startup(self) -> None:  # pragma: no cover - lifespan not entered
        pass

    async def shutdown(self) -> None:  # pragma: no cover - lifespan not entered
        pass


def _build(
    core: LifeOpsCore, clock: FrozenClock, client: ClientIdentity = WORLD_CLIENT
) -> MCPServer:
    return build_server(cast(Container, _StubContainer(core, clock)), client)


async def _call(server: MCPServer, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Invoke a tool and decode its JSON payload."""
    result = await server.call_tool(tool, arguments)
    (content,) = result.content
    return json.loads(content.text)


def _entity(
    entity_id: str,
    entity_type: WorldEntityType,
    display_name: str,
    **facts: str,
) -> WorldEntity:
    return WorldEntity(
        id=entity_id,
        entity_type=entity_type,
        display_name=display_name,
        facts=facts,
        created_at=TS,
        updated_at=TS,
    )


def _memory(memory_id: str, content: str, **overrides: Any) -> MemoryRecord:
    return MemoryRecord(
        id=memory_id,
        subject_id=PRIMARY_PERSON_ID,
        type=MemoryType.SEMANTIC,
        content=content,
        source_type=MemorySource.USER_EXPLICIT,
        observed_at=TS,
        created_at=TS,
        valid_from=TS,
        entity_ids=[PROVIDER_ID],
        **overrides,
    )


@pytest.fixture
async def core(clock: FrozenClock) -> LifeOpsCore:
    """A LifeOpsCore over a small, fully-populated world.

        Test User ─MEMBER_OF→ Household ←MEMBER_OF─ Tori
                                  │
                            USES_PROVIDER
                                  ↓
                            ABC Electric        (ABC Gas: unrelated, same prefix)
    """
    people = FakePersonRepository()
    world = FakeWorldRepository()
    memories = FakeMemoryRepository()

    for person_id, name, aliases in (
        (PRIMARY_PERSON_ID, "Test User", []),
        ("person_tori", "Tori", ["Vicky"]),
    ):
        await people.upsert(
            Person(
                id=person_id,
                display_name=name,
                is_primary=person_id == PRIMARY_PERSON_ID,
                aliases=aliases,
                created_at=TS,
                updated_at=TS,
            )
        )
        world.seed(_entity(person_id, WorldEntityType.PERSON, name))

    world.seed(_entity(HOUSEHOLD_ID, WorldEntityType.HOUSEHOLD, "Main House"))
    world.seed(
        _entity(PROVIDER_ID, WorldEntityType.PROVIDER, "ABC Electric", phone="555-0100")
    )
    world.seed(_entity("provider_abc_gas", WorldEntityType.PROVIDER, "ABC Gas"))

    await world.link(PRIMARY_PERSON_ID, HOUSEHOLD_ID, WorldRelationship.MEMBER_OF)
    await world.link("person_tori", HOUSEHOLD_ID, WorldRelationship.MEMBER_OF)
    await world.link(HOUSEHOLD_ID, PROVIDER_ID, WorldRelationship.USES_PROVIDER)

    # One closed memory and one current, both about the provider: entity
    # history is exactly this record in Phase 3.
    await memories.save_superseding(
        _memory(
            "memory_old",
            "The old electrician was DEF Power.",
            valid_to="2026-02-01T00:00:00Z",
            invalidation_reason="switched providers",
        ),
        supersedes=None,
    )
    await memories.save_superseding(
        _memory("memory_current", "The electrician is ABC Electric."), supersedes=None
    )

    return LifeOpsCore(
        people=people,
        preferences=FakePreferenceRepository(),
        tasks=FakeTaskRepository(),
        memory=memories,
        world=world,
        clock=clock,
    )


@pytest.fixture
def server(core: LifeOpsCore, clock: FrozenClock) -> MCPServer:
    return _build(core, clock)


class TestToolListing:
    async def test_the_phase_three_world_tools_are_listed(
        self, server: MCPServer
    ) -> None:
        names = {tool.name for tool in await server.list_tools()}
        assert {
            "find_person",
            "get_provider",
            "get_related_entities",
            "get_entity_history",
        } <= names


class TestFindPerson:
    async def test_finds_a_person_by_display_name(self, server: MCPServer) -> None:
        payload = await _call(server, "find_person", {"name": "Tori"})

        assert payload["ok"] is True
        assert payload["total"] == 1
        (person,) = payload["people"]
        assert person["id"] == "person_tori"
        assert person["display_name"] == "Tori"

    async def test_finds_a_person_by_alias(self, server: MCPServer) -> None:
        payload = await _call(server, "find_person", {"name": "Vicky"})

        assert payload["ok"] is True
        assert [p["id"] for p in payload["people"]] == ["person_tori"]

    async def test_no_match_is_an_empty_list_not_an_error(
        self, server: MCPServer
    ) -> None:
        payload = await _call(server, "find_person", {"name": "Nobody"})
        assert payload == {"ok": True, "people": [], "total": 0}


class TestGetProvider:
    async def test_by_id_returns_the_provider_with_its_facts(
        self, server: MCPServer
    ) -> None:
        payload = await _call(server, "get_provider", {"name_or_id": PROVIDER_ID})

        assert payload["ok"] is True
        provider = payload["provider"]
        assert provider["entity"]["id"] == PROVIDER_ID
        assert provider["entity"]["entity_type"] == "provider"
        assert provider["entity"]["display_name"] == "ABC Electric"
        assert provider["entity"]["facts"]["phone"] == "555-0100"

    async def test_unique_name_match_resolves_to_the_detail(
        self, server: MCPServer
    ) -> None:
        payload = await _call(server, "get_provider", {"name_or_id": "ABC Electric"})

        assert payload["ok"] is True
        assert payload["provider"]["entity"]["id"] == PROVIDER_ID

    async def test_ambiguous_name_returns_matches_with_canonical_ids(
        self, server: MCPServer
    ) -> None:
        payload = await _call(server, "get_provider", {"name_or_id": "ABC"})

        assert payload["ok"] is True
        assert payload["total"] == 2
        ids = {p["id"] for p in payload["providers"]}
        assert ids == {PROVIDER_ID, "provider_abc_gas"}

    async def test_unknown_provider_is_not_found_as_data(
        self, server: MCPServer
    ) -> None:
        payload = await _call(server, "get_provider", {"name_or_id": "No Such Co"})
        assert payload["ok"] is False
        assert payload["error"] == "not_found"


class TestGetRelatedEntities:
    async def test_returns_the_one_hop_neighbourhood(self, server: MCPServer) -> None:
        payload = await _call(
            server, "get_related_entities", {"entity_id": HOUSEHOLD_ID}
        )

        assert payload["ok"] is True
        neighbourhood = payload["neighborhood"]
        node_ids = {node["id"] for node in neighbourhood["nodes"]}
        assert node_ids == {HOUSEHOLD_ID, PRIMARY_PERSON_ID, "person_tori", PROVIDER_ID}
        edge_types = {edge["type"] for edge in neighbourhood["edges"]}
        assert edge_types == {"MEMBER_OF", "USES_PROVIDER"}

    async def test_unknown_entity_is_not_found_as_data(
        self, server: MCPServer
    ) -> None:
        payload = await _call(
            server, "get_related_entities", {"entity_id": "provider_nowhere"}
        )
        assert payload["ok"] is False
        assert payload["error"] == "not_found"


class TestGetEntityHistory:
    async def test_returns_history_entries_with_closed_windows(
        self, server: MCPServer
    ) -> None:
        payload = await _call(server, "get_entity_history", {"entity_id": PROVIDER_ID})

        assert payload["ok"] is True
        assert payload["entity_id"] == PROVIDER_ID
        contents = {entry["content"] for entry in payload["memories"]}
        assert contents == {
            "The old electrician was DEF Power.",
            "The electrician is ABC Electric.",
        }
        (closed,) = [
            entry for entry in payload["memories"] if entry["id"] == "memory_old"
        ]
        assert closed["valid_to"] == "2026-02-01T00:00:00Z"
        assert closed["invalidation_reason"] == "switched providers"
        # The history declares its own scope: it is not the Phase 4 audit log.
        assert payload["covers"] == [
            "every version of every fact this entity has carried",
            "memories referencing this entity, including closed versions",
        ]
        assert payload["fact_history"] == []

    async def test_unknown_entity_is_not_found_as_data(
        self, server: MCPServer
    ) -> None:
        payload = await _call(
            server, "get_entity_history", {"entity_id": "asset_nowhere"}
        )
        assert payload["ok"] is False
        assert payload["error"] == "not_found"

    async def test_a_client_without_read_memory_is_told_what_is_missing(
        self, core: LifeOpsCore, clock: FrozenClock
    ) -> None:
        """An empty history must not read as "nothing ever happened"."""
        server = _build(
            core,
            clock,
            ClientIdentity(
                client_id="world-only",
                role=ClientRole.INTERACTIVE_ASSISTANT,
                display_name="World only",
                capabilities=frozenset({Capability.READ_WORLD}),
            ),
        )
        payload = await _call(server, "get_entity_history", {"entity_id": PROVIDER_ID})

        assert payload["ok"] is True
        assert payload["memories"] == []
        assert payload["covers"] == [
            "every version of every fact this entity has carried",
            "nothing about memory: this client cannot read it",
        ]


class TestCapabilityDenial:
    """READ_WORLD gates all four tools; denials arrive as data, never raised."""

    @pytest.mark.parametrize(
        ("tool", "arguments"),
        [
            ("find_person", {"name": "Tori"}),
            ("get_provider", {"name_or_id": PROVIDER_ID}),
            ("get_related_entities", {"entity_id": HOUSEHOLD_ID}),
            ("get_entity_history", {"entity_id": PROVIDER_ID}),
        ],
    )
    async def test_client_without_read_world_is_denied_as_data(
        self,
        core: LifeOpsCore,
        clock: FrozenClock,
        tool: str,
        arguments: dict[str, Any],
    ) -> None:
        server = _build(core, clock, READ_LESS_CLIENT)

        payload = await _call(server, tool, arguments)

        assert payload["ok"] is False
        assert payload["error"] == "capability_denied"
        assert payload["client_id"] == "read-less"
