"""Unit tests for the self-configuration MCP tools (BUILD_SPEC section 73):
``propose_self_change``, ``save_workflow_template``, ``list_workflow_templates``,
``due_routines``, ``delete_workflow_template``.

Before this, none of these existed over MCP — only a Console-only HTTP path
existed for the template CRUD, and ``propose_self_change`` had no agent
surface at all, so Hermes had no way to check or apply a permitted self-change
itself. Same pattern as ``test_mcp_expanded_read_tools.py``: a real
``LifeOpsCore`` over fake repositories, called through a real ``MCPServer``,
so this proves the tools agree with the already-tested ``LifeOpsCore``
methods (``test_self_config.py``) rather than with a stub.
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
    FakeActionRepository,
    FakeApprovalRepository,
    FakeBillRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
    FakeWaitingRepository,
    FakeWorkflowTemplateRepository,
    FakeWorldRepository,
)
from tests.conftest import PRIMARY_PERSON_ID

TS = "2026-01-01T00:00:00Z"

NO_SELF_CONFIGURE_CLIENT = ClientIdentity(
    client_id="no-self-configure",
    role=ClientRole.INTERACTIVE_ASSISTANT,
    display_name="Cannot self-configure",
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
        waiting=FakeWaitingRepository(),
        actions=FakeActionRepository(),
        approvals=FakeApprovalRepository(),
        bills=FakeBillRepository(),
        templates=FakeWorkflowTemplateRepository(),
        clock=clock,
    )


@pytest.fixture
def hermes_server(core: LifeOpsCore, clock: FrozenClock) -> MCPServer:
    return _build(core, clock, HERMES)


class TestProposeSelfChange:
    async def test_an_ordinary_change_is_permitted(self, hermes_server: MCPServer) -> None:
        payload = await _call(
            hermes_server,
            "propose_self_change",
            {"target": "cron_job", "name": "nightly sweep"},
        )
        assert payload == {"ok": True, "permitted": True}

    async def test_a_protected_component_is_refused_as_data_not_a_crash(
        self, hermes_server: MCPServer
    ) -> None:
        payload = await _call(
            hermes_server,
            "propose_self_change",
            {"target": "skill", "name": "approval validation"},
        )
        assert payload["ok"] is False
        assert payload["error"] == "validation_error"

    async def test_a_forbidden_effect_is_refused_even_with_a_permitted_target(
        self, hermes_server: MCPServer
    ) -> None:
        payload = await _call(
            hermes_server,
            "propose_self_change",
            {
                "target": "reminder",
                "name": "harmless reminder",
                "effects": ["disable_emergency_stop"],
            },
        )
        assert payload["ok"] is False

    async def test_it_never_persists_anything(
        self, hermes_server: MCPServer, core: LifeOpsCore
    ) -> None:
        await _call(
            hermes_server, "propose_self_change", {"target": "cron_job", "name": "nightly sweep"}
        )
        assert await core.list_workflow_templates(HERMES) == []

    async def test_a_client_without_self_configure_is_denied(
        self, core: LifeOpsCore, clock: FrozenClock
    ) -> None:
        server = _build(core, clock, NO_SELF_CONFIGURE_CLIENT)
        payload = await _call(
            server, "propose_self_change", {"target": "cron_job", "name": "nightly sweep"}
        )
        assert payload["ok"] is False
        assert payload["error"] == "capability_denied"


class TestSaveAndListWorkflowTemplates:
    async def test_save_then_list_round_trips(self, hermes_server: MCPServer) -> None:
        saved = await _call(
            hermes_server,
            "save_workflow_template",
            {
                "name": "Morning brief",
                "steps": ["Read the calendar", "Read the waiting items"],
                "trigger": "manual",
            },
        )
        assert saved["ok"] is True
        assert saved["template"]["name"] == "Morning brief"
        assert [s["description"] for s in saved["template"]["steps"]] == [
            "Read the calendar", "Read the waiting items",
        ]

        listed = await _call(hermes_server, "list_workflow_templates", {})
        assert listed["ok"] is True
        assert listed["total"] == 1
        assert listed["templates"][0]["id"] == saved["template"]["id"]

    async def test_saving_an_existing_name_revises_rather_than_duplicates(
        self, hermes_server: MCPServer
    ) -> None:
        first = await _call(
            hermes_server, "save_workflow_template", {"name": "Nightly sweep"}
        )
        second = await _call(
            hermes_server,
            "save_workflow_template",
            {"name": "Nightly sweep", "description": "now with a note"},
        )
        assert second["template"]["id"] == first["template"]["id"]

        listed = await _call(hermes_server, "list_workflow_templates", {})
        assert listed["total"] == 1

    async def test_a_scheduled_template_without_a_time_is_refused(
        self, hermes_server: MCPServer
    ) -> None:
        payload = await _call(
            hermes_server,
            "save_workflow_template",
            {"name": "cron-like thing", "trigger": "schedule"},
        )
        assert payload["ok"] is False

    async def test_a_name_for_a_protected_component_is_refused(
        self, hermes_server: MCPServer
    ) -> None:
        payload = await _call(
            hermes_server, "save_workflow_template", {"name": "payment code"}
        )
        assert payload["ok"] is False

    async def test_a_client_without_self_configure_cannot_save(
        self, core: LifeOpsCore, clock: FrozenClock
    ) -> None:
        server = _build(core, clock, NO_SELF_CONFIGURE_CLIENT)
        payload = await _call(server, "save_workflow_template", {"name": "whatever"})
        assert payload["ok"] is False
        assert payload["error"] == "capability_denied"


class TestDueRoutines:
    async def test_a_scheduled_template_in_the_past_is_due(
        self, hermes_server: MCPServer
    ) -> None:
        await _call(
            hermes_server,
            "save_workflow_template",
            {
                "name": "Overdue sweep",
                "trigger": "schedule",
                "next_run_at": "2020-01-01T00:00:00Z",
            },
        )
        due = await _call(hermes_server, "due_routines", {})
        assert due["ok"] is True
        assert due["total"] == 1
        assert due["templates"][0]["name"] == "Overdue sweep"

    async def test_a_manual_template_is_never_due(self, hermes_server: MCPServer) -> None:
        await _call(hermes_server, "save_workflow_template", {"name": "on request only"})
        due = await _call(hermes_server, "due_routines", {})
        assert due["total"] == 0

    async def test_a_paused_scheduled_template_never_comes_due(
        self, hermes_server: MCPServer
    ) -> None:
        await _call(
            hermes_server,
            "save_workflow_template",
            {
                "name": "Paused sweep",
                "trigger": "schedule",
                "next_run_at": "2020-01-01T00:00:00Z",
                "enabled": False,
            },
        )
        due = await _call(hermes_server, "due_routines", {})
        assert due["total"] == 0


class TestDeleteWorkflowTemplate:
    async def test_delete_removes_it(self, hermes_server: MCPServer) -> None:
        saved = await _call(hermes_server, "save_workflow_template", {"name": "Throwaway"})
        deleted = await _call(
            hermes_server,
            "delete_workflow_template",
            {"template_id": saved["template"]["id"]},
        )
        assert deleted == {"ok": True, "deleted": True}

        listed = await _call(hermes_server, "list_workflow_templates", {})
        assert listed["total"] == 0

    async def test_deleting_an_unknown_id_reports_false_not_an_error(
        self, hermes_server: MCPServer
    ) -> None:
        payload = await _call(
            hermes_server, "delete_workflow_template", {"template_id": "template_nope"}
        )
        assert payload == {"ok": True, "deleted": False}
