"""Unit tests for the LifeOps MCP resources (BUILD_SPEC section 48).

The resources are shape translators over LifeOpsCore's public read operations,
so these tests run against the in-memory fakes and the FrozenClock — no
database, no transport. What is proven here:

  * each resource returns the documented shape;
  * lifeops://today derives "open" and "due" from task state and due_at;
  * lifeops://waiting carries the waiting context;
  * a client without the required capability gets
    ``{"ok": false, "error": "capability_denied"}`` as *data* — never a raised
    protocol error a model would retry blindly.
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from mcp.server.mcpserver import MCPServer

from lifeops.clock import FrozenClock
from lifeops.container import Container
from lifeops.core import LifeOpsCore
from lifeops.domain.preferences import PreferenceDraft
from lifeops.domain.tasks import TaskDraft, TaskState, TaskUpdate
from lifeops.mcp.server import build_server
from lifeops.policy import HERMES, Capability, ClientIdentity, ClientRole
from tests.conftest import PRIMARY_PERSON_ID


class _StubContainer:
    """Duck-typed Container: the MCP layer needs only ``core`` and ``clock``.

    Lifespan hooks exist so ``build_server``'s lifespan would run unchanged,
    though these tests read resources without entering it.
    """

    def __init__(self, core: LifeOpsCore, clock: FrozenClock) -> None:
        self.core = core
        self.clock = clock

    async def startup(self) -> None:  # pragma: no cover - lifespan not entered
        pass

    async def shutdown(self) -> None:  # pragma: no cover - lifespan not entered
        pass


def _client(client_id: str, capabilities: frozenset[Capability]) -> ClientIdentity:
    return ClientIdentity(
        client_id=client_id,
        role=ClientRole.ENGINEERING_ASSISTANT,
        display_name=client_id,
        capabilities=capabilities,
    )


def _build(core: LifeOpsCore, clock: FrozenClock, client: ClientIdentity) -> MCPServer:
    return build_server(cast(Container, _StubContainer(core, clock)), client)


async def _read(server: MCPServer, uri: str) -> dict[str, Any]:
    """Read a resource and decode its JSON payload."""
    contents = await server.read_resource(uri)
    payload = list(contents)
    assert len(payload) == 1
    content = payload[0].content
    assert isinstance(content, str)
    return json.loads(content)


@pytest.fixture
def server(core: LifeOpsCore, clock: FrozenClock) -> MCPServer:
    return _build(core, clock, HERMES)


class TestResourceListing:
    async def test_the_three_phase_one_resources_are_listed(
        self, server: MCPServer
    ) -> None:
        uris = {str(resource.uri) for resource in await server.list_resources()}
        assert {"lifeops://me", "lifeops://today", "lifeops://waiting"} <= uris


class TestMe:
    async def test_returns_the_primary_person(self, server: MCPServer) -> None:
        payload = await _read(server, "lifeops://me")

        assert payload["ok"] is True
        assert payload["person"]["id"] == PRIMARY_PERSON_ID
        assert payload["person"]["display_name"] == "Test User"
        assert payload["person"]["is_primary"] is True


class TestToday:
    async def test_open_due_and_preferences(
        self, server: MCPServer, core: LifeOpsCore, clock: FrozenClock
    ) -> None:
        now = clock.now().isoformat().replace("+00:00", "Z")

        due = await core.create_task(
            HERMES, TaskDraft(title="Overdue call", due_at="2025-12-31T09:00:00Z")
        )
        future = await core.create_task(
            HERMES, TaskDraft(title="Future call", due_at="2026-06-01T09:00:00Z")
        )
        undated = await core.create_task(HERMES, TaskDraft(title="Someday"))
        done = await core.create_task(HERMES, TaskDraft(title="Finished"))
        # CAPTURED -> READY -> EXECUTING -> COMPLETED (no verification needed).
        for target in (TaskState.READY, TaskState.EXECUTING, TaskState.COMPLETED):
            await core.update_task(
                HERMES, task_id=done.id, update=TaskUpdate(state=target)
            )
        await core.save_preference(
            HERMES,
            # Hermes holds WRITE_PREFERENCE; the resource only reads it back.
            PreferenceDraft(
                key="scheduling.earliest_appointment_time",
                value="nothing before ten",
            ),
        )

        payload = await _read(server, "lifeops://today")

        assert payload["ok"] is True
        assert payload["as_of"] == now

        open_ids = {t["id"] for t in payload["open_tasks"]}
        assert open_ids == {due.id, future.id, undated.id}, "terminal tasks are not open"

        due_ids = {t["id"] for t in payload["due_tasks"]}
        assert due_ids == {due.id}, "only due_at <= now counts as due"

        keys = {p["key"] for p in payload["preferences"]}
        assert keys == {"scheduling.earliest_appointment_time"}

    async def test_empty_world_still_returns_the_shape(self, server: MCPServer) -> None:
        payload = await _read(server, "lifeops://today")
        assert payload["ok"] is True
        assert payload["open_tasks"] == []
        assert payload["due_tasks"] == []
        assert payload["preferences"] == []


class TestWaiting:
    async def test_lists_waiting_tasks_with_context(
        self, server: MCPServer, core: LifeOpsCore
    ) -> None:
        waiting_task = await core.create_task(
            HERMES, TaskDraft(title="Order part", verification_required=True)
        )
        for target in (TaskState.READY, TaskState.EXECUTING):
            await core.update_task(
                HERMES, task_id=waiting_task.id, update=TaskUpdate(state=target)
            )
        await core.update_task(
            HERMES,
            task_id=waiting_task.id,
            update=TaskUpdate(
                state=TaskState.WAITING_EXTERNAL, current_action="awaiting supplier"
            ),
        )
        await core.create_task(HERMES, TaskDraft(title="Not waiting"))

        payload = await _read(server, "lifeops://waiting")

        assert payload["ok"] is True
        assert payload["total"] == 1
        (entry,) = payload["waiting"]
        assert entry["id"] == waiting_task.id
        assert entry["state"] == "WAITING_EXTERNAL"
        assert entry["current_action"] == "awaiting supplier"
        assert entry["verification_state"] == "pending"
        assert "updated_at" in entry

    async def test_no_waiting_tasks(self, server: MCPServer) -> None:
        payload = await _read(server, "lifeops://waiting")
        assert payload == {"ok": True, "waiting": [], "total": 0}


class TestCapabilityDenial:
    """Denials arrive as data with a stable code, never as raised errors."""

    async def test_client_without_read_world_cannot_read_me(
        self, core: LifeOpsCore, clock: FrozenClock
    ) -> None:
        server = _build(core, clock, _client("no-read-world", frozenset()))
        payload = await _read(server, "lifeops://me")
        assert payload["ok"] is False
        assert payload["error"] == "capability_denied"

    async def test_client_without_read_tasks_cannot_read_today_or_waiting(
        self, core: LifeOpsCore, clock: FrozenClock
    ) -> None:
        # READ_WORLD alone: lifeops://me is fine, the task-backed views are not.
        client = _client("world-only", frozenset({Capability.READ_WORLD}))
        server = _build(core, clock, client)

        assert (await _read(server, "lifeops://me"))["ok"] is True

        today = await _read(server, "lifeops://today")
        assert today["ok"] is False
        assert today["error"] == "capability_denied"

        waiting = await _read(server, "lifeops://waiting")
        assert waiting["ok"] is False
        assert waiting["error"] == "capability_denied"

    async def test_client_without_read_preferences_cannot_read_today(
        self, core: LifeOpsCore, clock: FrozenClock
    ) -> None:
        # lifeops://today composes tasks and preferences; lacking either
        # capability denies the whole view rather than returning a partial one.
        client = _client(
            "tasks-only",
            frozenset({Capability.READ_WORLD, Capability.READ_TASKS}),
        )
        server = _build(core, clock, client)

        payload = await _read(server, "lifeops://today")
        assert payload["ok"] is False
        assert payload["error"] == "capability_denied"
