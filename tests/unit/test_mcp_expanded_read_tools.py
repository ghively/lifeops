"""Unit tests for BUILD_SPEC section 48's remaining resources and section 50's
expanded read tools, exercised against a real ``LifeOpsCore`` over in-memory
repositories — the same pattern ``test_mcp_world_tools.py`` uses, because
stubbing the core would only prove the tools agree with the stub.

What is proven:

  * the five new resources (``lifeops://household``, ``lifeops://approvals``,
    ``lifeops://entity/{id}``, ``lifeops://task/{id}``,
    ``lifeops://provider/{id}``) and the new tools (``get_task``,
    ``list_waiting_items``, ``find_provider``, ``get_asset``, ``list_assets``,
    ``get_bill``, ``list_bills``) return the documented shape;
  * an unknown id comes back as ``{"ok": false, "error": "not_found"}`` data,
    never a raised protocol error;
  * a client lacking the relevant read capability gets ``capability_denied``
    as data, matching every other tool in this file.

``get_appointment``/``list_appointments`` are exercised at the ``LifeOpsCore``
level already (``test_calendar_email_core.py``); the MCP wrapping added here
is a thin shape translation over those already-tested methods.
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from mcp.server.mcpserver import MCPServer

from lifeops.clock import FrozenClock
from lifeops.container import Container
from lifeops.core import LifeOpsCore
from lifeops.domain.bills import BillDraft, PayeeDraft
from lifeops.domain.people import Person
from lifeops.domain.tasks import TaskDraft
from lifeops.domain.waiting import WaitingDraft
from lifeops.domain.world import WorldEntity, WorldEntityType
from lifeops.mcp.server import build_server
from lifeops.policy import ClientIdentity, ClientRole
from lifeops.policy.capabilities import CONSOLE, HERMES
from lifeops.repositories.fakes import (
    FakeActionRepository,
    FakeApprovalRepository,
    FakeBillRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
    FakeWaitingRepository,
    FakeWorldRepository,
)
from tests.conftest import PRIMARY_PERSON_ID

PROVIDER_ID = "provider_abc_electric"
ASSET_ID = "asset_land_rover"
HOUSEHOLD_ID = "household_main"
KNOWLEDGE_ID = "knowledge_01"
TS = "2026-01-01T00:00:00Z"

READ_LESS_CLIENT = ClientIdentity(
    client_id="read-less",
    role=ClientRole.INTERACTIVE_ASSISTANT,
    display_name="Read-less client",
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


async def _read(server: MCPServer, uri: str) -> dict[str, Any]:
    contents = await server.read_resource(uri)
    (payload,) = list(contents)
    content = payload.content
    assert isinstance(content, str)
    return json.loads(content)


def _entity(entity_id: str, entity_type: WorldEntityType, name: str, **facts: str) -> WorldEntity:
    return WorldEntity(
        id=entity_id, entity_type=entity_type, display_name=name, facts=facts,
        created_at=TS, updated_at=TS,
    )


@pytest.fixture
async def core(clock: FrozenClock) -> LifeOpsCore:
    people = FakePersonRepository()
    world = FakeWorldRepository()
    waiting = FakeWaitingRepository()
    actions = FakeActionRepository()
    approvals = FakeApprovalRepository()
    bills = FakeBillRepository()

    await people.upsert(
        Person(
            id=PRIMARY_PERSON_ID, display_name="Test User", is_primary=True,
            created_at=TS, updated_at=TS,
        )
    )
    world.seed(_entity(HOUSEHOLD_ID, WorldEntityType.HOUSEHOLD, "Main House"))
    world.seed(
        _entity(PROVIDER_ID, WorldEntityType.PROVIDER, "ABC Electric", phone="555-0100")
    )
    world.seed(_entity(ASSET_ID, WorldEntityType.ASSET, "Land Rover", plate="ABC-123"))
    world.seed(
        _entity(
            KNOWLEDGE_ID, WorldEntityType.KNOWLEDGE, "Water heater warranty",
            category="warranty", content="10-year tank warranty.",
        )
    )

    return LifeOpsCore(
        people=people,
        preferences=FakePreferenceRepository(),
        tasks=FakeTaskRepository(),
        world=world,
        waiting=waiting,
        actions=actions,
        approvals=approvals,
        bills=bills,
        clock=clock,
    )


@pytest.fixture
def hermes_server(core: LifeOpsCore, clock: FrozenClock) -> MCPServer:
    return _build(core, clock, HERMES)


class TestHousehold:
    async def test_returns_the_seeded_household(self, hermes_server: MCPServer) -> None:
        payload = await _read(hermes_server, "lifeops://household")
        assert payload["ok"] is True
        assert payload["household"]["id"] == HOUSEHOLD_ID

    async def test_none_when_no_household_exists(
        self, clock: FrozenClock
    ) -> None:
        empty_world = FakeWorldRepository()
        people = FakePersonRepository()
        await people.upsert(
            Person(
                id=PRIMARY_PERSON_ID, display_name="Test User", is_primary=True,
                created_at=TS, updated_at=TS,
            )
        )
        empty_core = LifeOpsCore(
            people=people, preferences=FakePreferenceRepository(),
            tasks=FakeTaskRepository(), world=empty_world, clock=clock,
        )
        server = _build(empty_core, clock, HERMES)
        payload = await _read(server, "lifeops://household")
        assert payload == {"ok": True, "household": None}

    async def test_denied_without_read_world(self, core: LifeOpsCore, clock: FrozenClock) -> None:
        server = _build(core, clock, READ_LESS_CLIENT)
        payload = await _read(server, "lifeops://household")
        assert payload["ok"] is False
        assert payload["error"] == "capability_denied"


class TestApprovals:
    async def test_lists_a_pending_approval(
        self, core: LifeOpsCore, hermes_server: MCPServer
    ) -> None:
        # record_payee always requires approval (section 72) — the cheapest
        # way to get one real pending Approval into the fakes. Recording is a
        # Console act; reading the resource back is Hermes's.
        payee_action = await core.record_payee(
            CONSOLE, PayeeDraft(display_name="ABC Electric", provider_entity_id=PROVIDER_ID)
        )
        assert payee_action.status.value == "needs_approval"

        payload = await _read(hermes_server, "lifeops://approvals")
        assert payload["ok"] is True
        assert payload["total"] == 1
        (approval,) = payload["approvals"]
        assert approval["action_id"] == payee_action.id
        assert approval["status"] == "pending"

    async def test_denied_without_read_tasks(self, core: LifeOpsCore, clock: FrozenClock) -> None:
        server = _build(core, clock, READ_LESS_CLIENT)
        payload = await _read(server, "lifeops://approvals")
        assert payload["ok"] is False
        assert payload["error"] == "capability_denied"


class TestEntityResource:
    async def test_reads_a_provider_by_id(self, hermes_server: MCPServer) -> None:
        payload = await _read(hermes_server, f"lifeops://entity/{PROVIDER_ID}")
        assert payload["ok"] is True
        assert payload["entity"]["entity"]["id"] == PROVIDER_ID

    async def test_unknown_id_is_not_found(self, hermes_server: MCPServer) -> None:
        payload = await _read(hermes_server, "lifeops://entity/provider_nobody")
        assert payload["ok"] is False
        assert payload["error"] == "not_found"


class TestTaskResource:
    async def test_reads_one_task(self, core: LifeOpsCore, hermes_server: MCPServer) -> None:
        created = await core.create_task(HERMES, TaskDraft(title="Call the electrician"))
        payload = await _read(hermes_server, f"lifeops://task/{created.id}")
        assert payload["ok"] is True
        assert payload["task"]["id"] == created.id
        assert payload["task"]["title"] == "Call the electrician"

    async def test_unknown_task_is_not_found(self, hermes_server: MCPServer) -> None:
        payload = await _read(hermes_server, "lifeops://task/task_nonexistent")
        assert payload["ok"] is False
        assert payload["error"] == "not_found"


class TestProviderResource:
    async def test_reads_a_provider(self, hermes_server: MCPServer) -> None:
        payload = await _read(hermes_server, f"lifeops://provider/{PROVIDER_ID}")
        assert payload["ok"] is True
        assert payload["provider"]["entity"]["id"] == PROVIDER_ID

    async def test_an_asset_id_is_not_a_provider(self, hermes_server: MCPServer) -> None:
        payload = await _read(hermes_server, f"lifeops://provider/{ASSET_ID}")
        assert payload["ok"] is False
        assert payload["error"] == "not_found"


class TestGetTaskTool:
    async def test_gets_a_task(self, core: LifeOpsCore, hermes_server: MCPServer) -> None:
        created = await core.create_task(HERMES, TaskDraft(title="Order part"))
        payload = await _call(hermes_server, "get_task", {"task_id": created.id})
        assert payload["ok"] is True
        assert payload["task"]["id"] == created.id

    async def test_unknown_task_is_not_found(self, hermes_server: MCPServer) -> None:
        payload = await _call(hermes_server, "get_task", {"task_id": "task_nope"})
        assert payload["ok"] is False
        assert payload["error"] == "not_found"


class TestListWaitingItemsTool:
    async def test_lists_a_waiting_item(
        self, core: LifeOpsCore, hermes_server: MCPServer
    ) -> None:
        task = await core.create_task(HERMES, TaskDraft(title="Order part"))
        await core.create_waiting_item(
            HERMES, WaitingDraft(task_id=task.id, subject="the supplier")
        )
        payload = await _call(hermes_server, "list_waiting_items", {})
        assert payload["ok"] is True
        assert payload["total"] == 1
        assert payload["waiting_items"][0]["task_id"] == task.id

    async def test_denied_without_read_tasks(self, core: LifeOpsCore, clock: FrozenClock) -> None:
        server = _build(core, clock, READ_LESS_CLIENT)
        payload = await _call(server, "list_waiting_items", {})
        assert payload["ok"] is False
        assert payload["error"] == "capability_denied"


class TestFindProviderTool:
    async def test_finds_by_partial_name(self, hermes_server: MCPServer) -> None:
        payload = await _call(hermes_server, "find_provider", {"query": "electric"})
        assert payload["ok"] is True
        assert payload["total"] == 1
        assert payload["providers"][0]["id"] == PROVIDER_ID

    async def test_no_match_is_an_empty_list_not_an_error(
        self, hermes_server: MCPServer
    ) -> None:
        payload = await _call(hermes_server, "find_provider", {"query": "nobody"})
        assert payload["ok"] is True
        assert payload["total"] == 0


class TestGetAssetTool:
    async def test_gets_by_id(self, hermes_server: MCPServer) -> None:
        payload = await _call(hermes_server, "get_asset", {"name_or_id": ASSET_ID})
        assert payload["ok"] is True
        assert payload["asset"]["entity"]["id"] == ASSET_ID

    async def test_gets_by_name(self, hermes_server: MCPServer) -> None:
        payload = await _call(hermes_server, "get_asset", {"name_or_id": "Land Rover"})
        assert payload["ok"] is True
        assert payload["asset"]["entity"]["id"] == ASSET_ID

    async def test_unknown_asset_is_not_found(self, hermes_server: MCPServer) -> None:
        payload = await _call(hermes_server, "get_asset", {"name_or_id": "asset_nope"})
        assert payload["ok"] is False
        assert payload["error"] == "not_found"


class TestListAssetsTool:
    async def test_lists_every_asset(self, hermes_server: MCPServer) -> None:
        payload = await _call(hermes_server, "list_assets", {})
        assert payload["ok"] is True
        assert payload["total"] == 1
        assert payload["assets"][0]["id"] == ASSET_ID


class TestBillTools:
    async def test_get_and_list_bills(
        self, core: LifeOpsCore, hermes_server: MCPServer
    ) -> None:
        await core.record_payee(
            CONSOLE, PayeeDraft(display_name="ABC Electric", provider_entity_id=PROVIDER_ID)
        )
        bill = await core.record_bill(
            CONSOLE,
            BillDraft(
                payee_id="payee_abc_electric", description="March invoice", amount="89.10"
            ),
        )

        listed = await _call(hermes_server, "list_bills", {})
        assert listed["ok"] is True
        assert listed["total"] == 1
        assert listed["bills"][0]["id"] == bill.id

        got = await _call(hermes_server, "get_bill", {"bill_id": bill.id})
        assert got["ok"] is True
        assert got["bill"]["amount"] == "89.10"

    async def test_unknown_bill_is_not_found(self, hermes_server: MCPServer) -> None:
        payload = await _call(hermes_server, "get_bill", {"bill_id": "bill_nope"})
        assert payload["ok"] is False
        assert payload["error"] == "not_found"


class TestSearchKnowledgeTool:
    async def test_matches_on_title(self, hermes_server: MCPServer) -> None:
        payload = await _call(hermes_server, "search_knowledge", {"query": "water heater"})
        assert payload["ok"] is True
        assert payload["total"] == 1
        assert payload["knowledge"][0]["id"] == KNOWLEDGE_ID

    async def test_matches_on_content(self, hermes_server: MCPServer) -> None:
        payload = await _call(hermes_server, "search_knowledge", {"query": "10-year"})
        assert payload["ok"] is True
        assert payload["total"] == 1

    async def test_empty_query_returns_everything(self, hermes_server: MCPServer) -> None:
        payload = await _call(hermes_server, "search_knowledge", {})
        assert payload["ok"] is True
        assert payload["total"] == 1

    async def test_denied_without_read_world(self, core: LifeOpsCore, clock: FrozenClock) -> None:
        server = _build(core, clock, READ_LESS_CLIENT)
        payload = await _call(server, "search_knowledge", {"query": "water"})
        assert payload["ok"] is False
        assert payload["error"] == "capability_denied"
