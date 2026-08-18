"""Workflow templates over HTTP (BUILD_SPEC sections 73, 100).

Runs the real LifeOpsCore over fakes. What is pinned is the boundary the
Routines screen depends on: saving by name creates-or-revises rather than
duplicating, a scheduled routine without a run time is refused, and the due
list only returns what is actually due.
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
from lifeops.events import EventBus
from lifeops.repositories.fakes import (
    FakeActionRepository,
    FakeApprovalRepository,
    FakeAuditRepository,
    FakeMemoryRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
    FakeWaitingRepository,
    FakeWorkflowTemplateRepository,
    FakeWorldRepository,
)
from lifeops.secrets.local_encrypted import InMemorySecretStore
from lifeops.settings import Settings

API = "/api/v1"
TS = "2026-01-01T00:00:00Z"


class StubContainer:
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
        self.core = LifeOpsCore(
            people=self.people,
            preferences=FakePreferenceRepository(),
            tasks=FakeTaskRepository(),
            memory=FakeMemoryRepository(),
            world=FakeWorldRepository(),
            waiting=FakeWaitingRepository(),
            actions=FakeActionRepository(),
            approvals=FakeApprovalRepository(),
            audit=FakeAuditRepository(),
            templates=FakeWorkflowTemplateRepository(),
            clock=self.clock,
            events=self.events,
        )

    async def startup(self) -> None:
        await self.people.upsert(
            Person(id="person_u", display_name="U", is_primary=True,
                   created_at=TS, updated_at=TS)
        )

    async def shutdown(self) -> None:
        return None

    async def health(self) -> dict[str, Any]:
        return {"safe_mode": self.core.safe_mode}


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[tuple[httpx.AsyncClient, Any]]:
    container = StubContainer(tmp_path)
    app = create_app(container=container, settings=container.settings)  # type: ignore[arg-type]
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://lifeops.test"
        ) as http:
            yield http, app


class TestWorkflowTemplates:
    async def test_saving_creates_then_listing_returns_it(self, env) -> None:
        http, _ = env
        created = await http.post(
            f"{API}/workflow-templates",
            json={
                "name": "Weekly review",
                "description": "Look back on the week",
                "steps": [
                    {"order": 0, "description": "Summarize tasks", "action_type": None},
                ],
                "trigger": "manual",
            },
        )
        assert created.status_code == 201
        body = created.json()
        assert body["name"] == "Weekly review"
        assert body["enabled"] is True
        assert [s["description"] for s in body["steps"]] == ["Summarize tasks"]

        listed = await http.get(f"{API}/workflow-templates")
        assert listed.status_code == 200
        assert [t["name"] for t in listed.json()["templates"]] == ["Weekly review"]

    async def test_saving_the_same_name_revises_instead_of_duplicating(self, env) -> None:
        http, _ = env
        await http.post(f"{API}/workflow-templates", json={"name": "Weekly review"})
        await http.post(
            f"{API}/workflow-templates",
            json={"name": "Weekly review", "description": "Revised"},
        )
        listed = (await http.get(f"{API}/workflow-templates")).json()["templates"]
        assert len(listed) == 1
        assert listed[0]["description"] == "Revised"

    async def test_a_scheduled_routine_needs_a_run_time(self, env) -> None:
        http, _ = env
        response = await http.post(
            f"{API}/workflow-templates",
            json={"name": "Nightly backup check", "trigger": "schedule"},
        )
        assert response.status_code == 422

    async def test_due_routines_only_returns_what_is_due(self, env) -> None:
        http, _ = env
        await http.post(
            f"{API}/workflow-templates",
            json={
                "name": "Future routine",
                "trigger": "schedule",
                "next_run_at": "2099-01-01T00:00:00Z",
            },
        )
        await http.post(
            f"{API}/workflow-templates",
            json={
                "name": "Overdue routine",
                "trigger": "schedule",
                "next_run_at": "2000-01-01T00:00:00Z",
            },
        )
        due = (await http.get(f"{API}/workflow-templates/due")).json()["templates"]
        assert [t["name"] for t in due] == ["Overdue routine"]

    async def test_deleting_a_template_removes_it(self, env) -> None:
        http, _ = env
        created = (
            await http.post(f"{API}/workflow-templates", json={"name": "Throwaway"})
        ).json()

        deleted = await http.delete(f"{API}/workflow-templates/{created['id']}")
        assert deleted.status_code == 204

        listed = (await http.get(f"{API}/workflow-templates")).json()["templates"]
        assert listed == []


class TestSelfConfigCheck:
    """The MCP tool of the same name is tested against a real MCPServer in
    tests/unit/test_mcp_self_config_tools.py; this pins the equivalent HTTP
    surface the Console would use to show the same check."""

    async def test_an_ordinary_change_is_permitted(self, env) -> None:
        http, _ = env
        response = await http.post(
            f"{API}/self-config/check",
            json={"target": "cron_job", "name": "nightly sweep"},
        )
        assert response.status_code == 200
        assert response.json() == {"permitted": True}

    async def test_a_protected_component_is_refused_with_a_stable_code(self, env) -> None:
        http, _ = env
        response = await http.post(
            f"{API}/self-config/check",
            json={"target": "skill", "name": "approval validation"},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"

    async def test_a_forbidden_effect_is_refused_even_with_a_permitted_target(
        self, env
    ) -> None:
        http, _ = env
        response = await http.post(
            f"{API}/self-config/check",
            json={
                "target": "reminder",
                "name": "harmless reminder",
                "effects": ["disable_emergency_stop"],
            },
        )
        assert response.status_code == 422

    async def test_the_check_never_persists_a_template(self, env) -> None:
        http, _ = env
        await http.post(
            f"{API}/self-config/check",
            json={"target": "cron_job", "name": "nightly sweep"},
        )
        listed = (await http.get(f"{API}/workflow-templates")).json()["templates"]
        assert listed == []
