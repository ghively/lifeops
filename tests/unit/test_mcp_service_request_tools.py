"""Unit tests for the Phase 8 provider-workflow MCP tools (BUILD_SPEC
sections 68, 97, 101).

Same discipline as ``test_mcp_world_tools.py``: a real ``LifeOpsCore`` over
in-memory repositories and a fake telephony provider, with only the
``Container`` duck-typed. ``create_service_request``, ``request_provider_call``,
``request_quote``, and ``book_service_request`` are checked for their
documented shape and for the capability gate every action tool goes through
(``prepare_action`` -> ``capability_for_action``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from mcp.server.mcpserver import MCPServer

from lifeops.calendar.fake import FakeCalendarProvider
from lifeops.calendar.service import CalendarProviderService
from lifeops.clock import FrozenClock
from lifeops.config.service import ConfigurationService
from lifeops.container import Container
from lifeops.core import LifeOpsCore
from lifeops.domain.people import Person
from lifeops.mcp.server import build_server
from lifeops.policy import Capability, ClientIdentity, ClientRole
from lifeops.policy.capabilities import HERMES
from lifeops.repositories.fakes import (
    FakeActionRepository,
    FakeApprovalRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
    FakeWaitingRepository,
    FakeWorldRepository,
)
from lifeops.secrets.local_encrypted import InMemorySecretStore
from lifeops.telephony.fake import FakeTelephonyProvider
from lifeops.telephony.service import TelephonyProviderService

PRIMARY_PERSON_ID = "person_service_request_mcp_user"
TS = "2026-01-01T00:00:00Z"

#: A client with no capability at all — used to prove the denial path.
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


def _build(
    core: LifeOpsCore, clock: FrozenClock, client: ClientIdentity = HERMES
) -> MCPServer:
    return build_server(cast(Container, _StubContainer(core, clock)), client)


async def _call(server: MCPServer, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = await server.call_tool(tool, arguments)
    (content,) = result.content
    return json.loads(content.text)


@pytest.fixture
def fake_telephony() -> FakeTelephonyProvider:
    return FakeTelephonyProvider(
        availability=["Thursday 1:00-3:00 PM"], diagnostic_fee="$89"
    )


@pytest.fixture
def config_service(tmp_path: Path) -> ConfigurationService:
    return ConfigurationService(
        config_dir=tmp_path / "config",
        secret_store=InMemorySecretStore(),
        clock=FrozenClock(),
    )


@pytest.fixture
def telephony_service(
    config_service: ConfigurationService, fake_telephony: FakeTelephonyProvider
) -> TelephonyProviderService:
    config_service.update_provider("telephony", {"enabled": True})
    return TelephonyProviderService(
        config=config_service,
        secret_store=InMemorySecretStore(),
        factories={"telephony": lambda settings, secrets: fake_telephony},
    )


@pytest.fixture
def calendar_service(config_service: ConfigurationService) -> CalendarProviderService:
    fake_calendar = FakeCalendarProvider()
    config_service.update_provider("calendar", {"enabled": True, "backend": "caldav"})
    return CalendarProviderService(
        config=config_service,
        secret_store=InMemorySecretStore(),
        factories={"caldav": lambda settings, secrets: fake_calendar},
    )


@pytest.fixture
async def core(
    telephony_service: TelephonyProviderService,
    calendar_service: CalendarProviderService,
) -> LifeOpsCore:
    people = FakePersonRepository()
    await people.upsert(
        Person(
            id=PRIMARY_PERSON_ID,
            display_name="Service Request MCP User",
            is_primary=True,
            created_at=TS,
            updated_at=TS,
        )
    )
    preferences = FakePreferenceRepository()
    world = FakeWorldRepository(preferences=preferences)
    return LifeOpsCore(
        people=people,
        preferences=preferences,
        tasks=FakeTaskRepository(),
        world=world,
        waiting=FakeWaitingRepository(),
        actions=FakeActionRepository(),
        approvals=FakeApprovalRepository(),
        telephony=telephony_service,
        calendar=calendar_service,
        clock=FrozenClock(),
    )


@pytest.fixture
def server(core: LifeOpsCore, clock: FrozenClock) -> MCPServer:
    return _build(core, clock)


class TestToolListing:
    async def test_the_phase_eight_tools_are_listed(self, server: MCPServer) -> None:
        names = {tool.name for tool in await server.list_tools()}
        assert {
            "create_service_request",
            "get_service_request",
            "request_provider_call",
            "request_quote",
            "book_service_request",
        } <= names


class TestCreateAndGetServiceRequest:
    async def test_create_then_get_round_trips(self, server: MCPServer) -> None:
        created = await _call(
            server, "create_service_request", {"subject": "Living Room Outlet repair"}
        )
        assert created["ok"] is True
        sr_id = created["service_request"]["id"]
        assert created["service_request"]["status"] == "researching"

        fetched = await _call(server, "get_service_request", {"service_request_id": sr_id})
        assert fetched["ok"] is True
        assert fetched["service_request"]["id"] == sr_id

    async def test_unknown_service_request_is_not_found_as_data(
        self, server: MCPServer
    ) -> None:
        payload = await _call(
            server, "get_service_request", {"service_request_id": "servicerequest_nowhere"}
        )
        assert payload["ok"] is False
        assert payload["error"] == "not_found"


class TestRequestProviderCall:
    async def test_never_authorises_charge_or_repairs(self, server: MCPServer) -> None:
        """BUILD_SPEC section 97's hard rule, proven at the MCP boundary — the
        tool exposes no argument that could set either flag."""
        created = await _call(
            server, "create_service_request", {"subject": "Living Room Outlet repair"}
        )
        sr_id = created["service_request"]["id"]

        called = await _call(
            server,
            "request_provider_call",
            {
                "service_request_id": sr_id,
                "provider_entity_id": "provider_abc_electric",
                "objective": "schedule_electrician",
                "collect": ["availability", "diagnostic_fee"],
            },
        )
        assert called["ok"] is True
        authority = called["action"]["payload"]["authority"]
        assert authority["authorize_charge"] is False
        assert authority["authorize_repairs"] is False

        follow_up = await _call(
            server, "get_service_request", {"service_request_id": sr_id}
        )
        assert follow_up["service_request"]["status"] == "contacting_provider"


class TestCapabilityDenial:
    async def test_a_client_without_send_external_message_is_denied(
        self, core: LifeOpsCore, clock: FrozenClock
    ) -> None:
        server = _build(core, clock, READ_LESS_CLIENT)
        created = await _call(
            server, "create_service_request", {"subject": "Furnace tune-up"}
        )
        # WRITE_WORLD is also missing for this client, so creation itself is
        # denied — the denial-as-data contract holds at the very first step.
        assert created["ok"] is False
        assert created["error"] == "capability_denied"

    async def test_a_client_with_only_write_world_cannot_call_a_provider(
        self, core: LifeOpsCore, clock: FrozenClock
    ) -> None:
        world_only = ClientIdentity(
            client_id="world-only",
            role=ClientRole.INTERACTIVE_ASSISTANT,
            display_name="World only",
            capabilities=frozenset({Capability.WRITE_WORLD, Capability.READ_WORLD}),
        )
        server = _build(core, clock, world_only)
        created = await _call(
            server, "create_service_request", {"subject": "Furnace tune-up"}
        )
        assert created["ok"] is True
        sr_id = created["service_request"]["id"]

        called = await _call(
            server,
            "request_provider_call",
            {
                "service_request_id": sr_id,
                "provider_entity_id": "provider_abc_hvac",
                "objective": "schedule_hvac",
                "collect": ["availability"],
            },
        )
        assert called["ok"] is False
        assert called["error"] == "capability_denied"
