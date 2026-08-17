"""Unit tests for the Phase 2 memory MCP tools (BUILD_SPEC sections 42-47).

Like the Phase 1 resource tests, these run against the in-memory fakes and the
FrozenClock — no database, no transport — because the tools are shape
translators over LifeOpsCore's public operations. What is proven here:

  * ``search_memory`` / ``remember`` / ``invalidate_memory`` each return the
    documented shape on the happy path;
  * a client without ``read_memory`` / ``write_memory`` gets
    ``{"ok": false, "error": "capability_denied"}`` as *data*, never a raised
    protocol error a model would retry blindly;
  * invalidating an unknown memory id is ``not_found``, also as data;
  * ``remember`` cannot touch transactional state (section 44): tasks and
    preferences in the fake repositories are byte-identical before and after.

The memory-capable client is constructed inline rather than taken from the
capability manifest so these tests pin the tools' behaviour to the
capabilities they require, not to any one role's current grant set.
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
from lifeops.domain.preferences import PreferenceDraft
from lifeops.domain.tasks import TaskDraft
from lifeops.mcp.server import build_server
from lifeops.policy import HERMES, Capability, ClientIdentity, ClientRole
from lifeops.repositories.fakes import (
    FakeMemoryRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
)
from tests.conftest import PRIMARY_PERSON_ID

#: A client holding exactly the capabilities the memory tools require.
MEMORY_CLIENT = ClientIdentity(
    client_id="memory-client",
    role=ClientRole.INTERACTIVE_ASSISTANT,
    display_name="Memory client",
    capabilities=frozenset({Capability.READ_MEMORY, Capability.WRITE_MEMORY}),
)


class _StubContainer:
    """Duck-typed Container: the MCP layer needs only ``core`` and ``clock``.

    Lifespan hooks exist so ``build_server``'s lifespan would run unchanged,
    though these tests call tools without entering it.
    """

    def __init__(self, core: LifeOpsCore, clock: FrozenClock) -> None:
        self.core = core
        self.clock = clock

    async def startup(self) -> None:  # pragma: no cover - lifespan not entered
        pass

    async def shutdown(self) -> None:  # pragma: no cover - lifespan not entered
        pass


def _build(
    core: LifeOpsCore, clock: FrozenClock, client: ClientIdentity = MEMORY_CLIENT
) -> MCPServer:
    return build_server(cast(Container, _StubContainer(core, clock)), client)


async def _call(server: MCPServer, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Invoke a tool and decode its JSON payload."""
    result = await server.call_tool(tool, arguments)
    (content,) = result.content
    return json.loads(content.text)


async def _remember(
    server: MCPServer, content: str, *, type: str = "semantic", **extra: Any
) -> dict[str, Any]:
    payload = await _call(server, "remember", {"content": content, "type": type, **extra})
    assert payload["ok"] is True
    return payload["memory"]


@pytest.fixture
def memory_repos() -> (
    tuple[
        FakePersonRepository,
        FakePreferenceRepository,
        FakeTaskRepository,
        FakeMemoryRepository,
    ]
):
    return (
        FakePersonRepository(),
        FakePreferenceRepository(),
        FakeTaskRepository(),
        FakeMemoryRepository(),
    )


@pytest.fixture
async def core(
    memory_repos: tuple[
        FakePersonRepository,
        FakePreferenceRepository,
        FakeTaskRepository,
        FakeMemoryRepository,
    ],
    clock: FrozenClock,
) -> LifeOpsCore:
    """A LifeOpsCore with the memory fake wired.

    Shadows the shared conftest fixture, which predates Phase 2 and has no
    memory repository; the memory tools need one.
    """
    people, preferences, tasks, memories = memory_repos
    await people.upsert(
        Person(
            id=PRIMARY_PERSON_ID,
            display_name="Test User",
            is_primary=True,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
    )
    return LifeOpsCore(
        people=people,
        preferences=preferences,
        tasks=tasks,
        memory=memories,
        clock=clock,
    )


@pytest.fixture
def server(core: LifeOpsCore, clock: FrozenClock) -> MCPServer:
    return _build(core, clock)


class TestToolListing:
    async def test_the_phase_two_memory_tools_are_listed(
        self, server: MCPServer
    ) -> None:
        names = {tool.name for tool in await server.list_tools()}
        assert {"search_memory", "remember", "invalidate_memory"} <= names


class TestSearchMemory:
    async def test_recalls_a_stored_memory(self, server: MCPServer) -> None:
        stored = await _remember(server, "Tori's dog is called Biscuit.")

        payload = await _call(server, "search_memory", {"query": "Biscuit"})

        assert payload["ok"] is True
        assert payload["total"] >= 1
        (hit,) = [m for m in payload["memories"] if m["id"] == stored["id"]]
        assert hit["content"] == "Tori's dog is called Biscuit."
        assert hit["type"] == "semantic"
        assert hit["subject_id"] == PRIMARY_PERSON_ID

    async def test_empty_memory_still_returns_the_shape(
        self, server: MCPServer
    ) -> None:
        payload = await _call(server, "search_memory", {"query": "anything"})
        assert payload == {"ok": True, "memories": [], "total": 0}

    async def test_invalidated_memories_are_not_recalled(
        self, server: MCPServer
    ) -> None:
        stored = await _remember(server, "The Land Rover is garaged at the outlet.")
        invalidated = await _call(
            server,
            "invalidate_memory",
            {"memory_id": stored["id"], "reason": "vehicle sold"},
        )
        assert invalidated["ok"] is True

        payload = await _call(server, "search_memory", {"query": "Land Rover"})
        assert payload["ok"] is True
        assert payload["memories"] == []


class TestRemember:
    async def test_stores_a_semantic_memory(self, server: MCPServer) -> None:
        payload = await _call(
            server,
            "remember",
            {
                "content": "The user takes coffee black.",
                "type": "semantic",
                "source_type": "conversation",
                "confidence": 0.9,
                "importance": 0.3,
            },
        )

        assert payload["ok"] is True
        memory = payload["memory"]
        assert memory["id"].startswith("memory_")
        assert memory["type"] == "semantic"
        assert memory["content"] == "The user takes coffee black."
        assert memory["subject_id"] == PRIMARY_PERSON_ID
        assert memory["source"] == "conversation"
        assert memory["confidence"] == 0.9
        assert memory["importance"] == 0.3
        assert memory["valid_to"] is None

    async def test_stores_a_low_confidence_preference_candidate(
        self, server: MCPServer
    ) -> None:
        memory = await _remember(
            server,
            "The user may prefer morning appointments.",
            type="preference_candidate",
            source_type="user_inferred",
            confidence=0.4,
        )
        assert memory["type"] == "preference_candidate"
        assert memory["confidence"] == 0.4

    async def test_cannot_touch_transactional_state(
        self,
        server: MCPServer,
        core: LifeOpsCore,
        memory_repos: tuple[
            FakePersonRepository,
            FakePreferenceRepository,
            FakeTaskRepository,
            FakeMemoryRepository,
        ],
    ) -> None:
        """Section 44: memory observes; it never rewrites transactional reality.

        A task and a preference exist; remember() runs; the fake repositories
        must hold exactly the same transactional records afterwards.
        """
        _, preferences, tasks, _memories = memory_repos

        # Transactional state is seeded through the core with Hermes, which
        # holds the task/preference capabilities the memory-only client does
        # not — exactly the separation section 44 requires.
        await core.create_task(HERMES, TaskDraft(title="Call the dentist"))
        await core.save_preference(
            HERMES,
            PreferenceDraft(
                key="scheduling.earliest_appointment_time", value="nothing before ten"
            ),
        )
        before_tasks = [t.model_dump() for t in await tasks.list()]
        before_preferences = [
            p.model_dump() for p in await preferences.list_current(PRIMARY_PERSON_ID)
        ]

        remembered = await _remember(
            server,
            "The user mentioned the dentist while talking about coffee.",
            type="episodic",
        )
        assert remembered["id"].startswith("memory_")

        assert [t.model_dump() for t in await tasks.list()] == before_tasks
        assert [
            p.model_dump() for p in await preferences.list_current(PRIMARY_PERSON_ID)
        ] == before_preferences


class TestInvalidateMemory:
    async def test_closes_the_validity_window(
        self, server: MCPServer, clock: FrozenClock
    ) -> None:
        stored = await _remember(server, "The mechanic is ABC Auto.")

        payload = await _call(
            server,
            "invalidate_memory",
            {"memory_id": stored["id"], "reason": "switched mechanics"},
        )

        assert payload["ok"] is True
        memory = payload["memory"]
        assert memory["id"] == stored["id"]
        # Temporal close, never a delete: the window ends at "now" on the
        # injected clock and the record itself is still returned.
        assert memory["valid_to"] == clock.now().isoformat().replace("+00:00", "Z")

    async def test_unknown_id_is_not_found_as_data(self, server: MCPServer) -> None:
        payload = await _call(
            server,
            "invalidate_memory",
            {"memory_id": "memory_does_not_exist", "reason": "cleanup"},
        )
        assert payload["ok"] is False
        assert payload["error"] == "not_found"


class TestCapabilityDenial:
    """Denials arrive as data with a stable code, never as raised errors."""

    async def test_search_memory_requires_read_memory_capability(
        self, core: LifeOpsCore, clock: FrozenClock
    ) -> None:
        client = ClientIdentity(
            client_id="write-only",
            role=ClientRole.INTERACTIVE_ASSISTANT,
            display_name="write-only",
            capabilities=frozenset({Capability.WRITE_MEMORY}),
        )
        server = _build(core, clock, client)

        payload = await _call(server, "search_memory", {"query": "anything"})
        assert payload["ok"] is False
        assert payload["error"] == "capability_denied"

    async def test_remember_requires_write_memory_capability(
        self, core: LifeOpsCore, clock: FrozenClock
    ) -> None:
        client = ClientIdentity(
            client_id="search-only",
            role=ClientRole.INTERACTIVE_ASSISTANT,
            display_name="search-only",
            capabilities=frozenset({Capability.READ_MEMORY}),
        )
        server = _build(core, clock, client)

        payload = await _call(
            server, "remember", {"content": "a fact", "type": "semantic"}
        )
        assert payload["ok"] is False
        assert payload["error"] == "capability_denied"

    async def test_invalidate_memory_requires_write_memory_capability(
        self, core: LifeOpsCore, clock: FrozenClock
    ) -> None:
        client = ClientIdentity(
            client_id="search-only",
            role=ClientRole.INTERACTIVE_ASSISTANT,
            display_name="search-only",
            capabilities=frozenset({Capability.READ_MEMORY}),
        )
        server = _build(core, clock, client)

        payload = await _call(
            server,
            "invalidate_memory",
            {"memory_id": "memory_whatever", "reason": "no authority"},
        )
        assert payload["ok"] is False
        assert payload["error"] == "capability_denied"
