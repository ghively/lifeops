"""Durable work HTTP API — waiting items, actions, approvals, audit
(BUILD_SPEC sections 13, 54-62, 93).

Runs the real ``LifeOpsCore`` over in-memory repositories, the same
discipline ``test_world_api.py`` uses: an adapter test against a stubbed core
would only prove the adapter agrees with the stub. What is pinned here:
routes, status codes, stable error codes, capability enforcement, and the
Approval screen's enrichment (the exact payload the human is approving,
attached without a second Console round trip).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager  # type: ignore[import-not-found]

from lifeops.api.http import create_app, get_client
from lifeops.clock import FrozenClock
from lifeops.config.service import ConfigurationService
from lifeops.core import LifeOpsCore
from lifeops.domain.actions import ActionDraft, ActionStatus, ActionType
from lifeops.domain.actions import prepare as prepare_action
from lifeops.domain.approvals import request as request_approval
from lifeops.domain.people import Person
from lifeops.domain.tasks import TaskDraft
from lifeops.events import EventBus
from lifeops.policy import Capability, ClientIdentity, ClientRole
from lifeops.policy.capabilities import CONSOLE
from lifeops.repositories.fakes import (
    FakeActionRepository,
    FakeApprovalRepository,
    FakeAuditRepository,
    FakeMemoryRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
    FakeWaitingRepository,
    FakeWorldRepository,
)
from lifeops.secrets.local_encrypted import InMemorySecretStore
from lifeops.settings import Settings

API = "/api/v1"

PRIMARY = "person_durable_work_user"


class StubContainer:
    """A Container with fakes in place of NornicDB, wired for durable work."""

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
        self.memories = FakeMemoryRepository()
        self.world = FakeWorldRepository(preferences=self.preferences)
        self.waiting = FakeWaitingRepository()
        self.actions = FakeActionRepository()
        self.approvals = FakeApprovalRepository()
        self.audit = FakeAuditRepository()
        self.core = LifeOpsCore(
            people=self.people,
            preferences=self.preferences,
            tasks=self.tasks,
            memory=self.memories,
            world=self.world,
            waiting=self.waiting,
            actions=self.actions,
            approvals=self.approvals,
            audit=self.audit,
            clock=self.clock,
            events=self.events,
        )

    async def startup(self) -> None:
        person = Person(
            id=PRIMARY,
            display_name="Durable Work User",
            is_primary=True,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        await self.people.upsert(person)

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
) -> AsyncIterator[tuple[httpx.AsyncClient, Any, StubContainer]]:
    container = StubContainer(tmp_path)
    app = create_app(container=container, settings=container.settings)  # type: ignore[arg-type]
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://lifeops.test"
        ) as http_client:
            yield http_client, app, container


Env = tuple[httpx.AsyncClient, Any, "StubContainer"]


async def _make_task(container: StubContainer, title: str = "Book electrician") -> str:
    task = await container.core.create_task(CONSOLE, TaskDraft(title=title))
    return task.id


async def _seed_action_needing_approval(
    container: StubContainer,
    *,
    task_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Seed an Action + Approval directly through the repositories.

    None of the built-in client identities carry a capability for a
    consequential action type (that grant arrives with the client that will
    actually drive bookings), so tests seed the two-phase-commit state the
    same way ``FakeWorldRepository.seed`` lets world tests bypass creation —
    directly through the fakes rather than through ``LifeOpsCore``. Only the
    HTTP routes under test are ever exercised through the real core.
    """
    now = "2026-08-17T09:00:00Z"
    action = prepare_action(
        ActionDraft(
            type=ActionType.BOOK_APPOINTMENT,
            payload=payload or {"time": "Thursday 1-3 PM", "amount": "89"},
            task_id=task_id,
            target_entity_id="provider_abc_electric",
        ),
        now=now,
        client_id="hermes-personal",
    )
    created = await container.actions.create(action)
    approval = request_approval(created, now=now, requested_by="hermes-personal")
    saved_approval = await container.approvals.create(approval)
    return created.id, saved_approval.id


class TestWaitingList:
    async def test_empty_list_is_honest(self, env: Env) -> None:
        client, _, _ = env
        response = await client.get(f"{API}/waiting")
        assert response.status_code == 200
        assert response.json() == {"items": [], "total": 0}

    async def test_create_then_list_round_trips(self, env: Env) -> None:
        client, _, container = env
        task_id = await _make_task(container)
        response = await client.post(
            f"{API}/waiting",
            json={
                "task_id": task_id,
                "subject": "ABC Electric",
                "waiting_on_entity_id": "provider_abc_electric",
                "expected_by": "2026-08-20T00:00:00Z",
                "max_followups": 3,
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["subject"] == "ABC Electric"
        assert body["task_id"] == task_id
        assert body["waiting_on_entity_id"] == "provider_abc_electric"
        assert body["status"] == "waiting"
        assert body["followup_count"] == 0
        assert body["next_action_at"] is not None

        listed = (await client.get(f"{API}/waiting")).json()
        assert listed["total"] == 1
        assert listed["items"][0]["id"] == body["id"]

    async def test_create_against_an_unknown_task_is_404(self, env: Env) -> None:
        client, _, _ = env
        response = await client.post(
            f"{API}/waiting",
            json={"task_id": "task_nope", "subject": "ABC Electric"},
        )
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_status_filter_narrows_the_list(self, env: Env) -> None:
        client, _, container = env
        task_id = await _make_task(container)
        first = (
            await client.post(
                f"{API}/waiting", json={"task_id": task_id, "subject": "ABC Electric"}
            )
        ).json()
        await client.post(f"{API}/waiting/{first['id']}/resolve")
        second = (
            await client.post(
                f"{API}/waiting", json={"task_id": task_id, "subject": "Pediatrician"}
            )
        ).json()

        waiting_only = (
            await client.get(f"{API}/waiting?status=waiting")
        ).json()
        assert [i["id"] for i in waiting_only["items"]] == [second["id"]]

    async def test_get_unknown_waiting_item_is_404(self, env: Env) -> None:
        client, _, _ = env
        response = await client.get(f"{API}/waiting/waiting_nope")
        assert response.status_code == 404


class TestWaitingFollowupAndResolve:
    async def test_followup_advances_the_count_and_next_action(self, env: Env) -> None:
        client, _, container = env
        task_id = await _make_task(container)
        created = (
            await client.post(
                f"{API}/waiting", json={"task_id": task_id, "subject": "ABC Electric"}
            )
        ).json()

        response = await client.post(f"{API}/waiting/{created['id']}/followup")
        assert response.status_code == 200
        body = response.json()
        assert body["followup_count"] == 1
        assert body["status"] == "waiting"
        assert body["last_contact_at"] is not None

    async def test_exhausting_the_followup_budget_escalates(self, env: Env) -> None:
        client, _, container = env
        task_id = await _make_task(container)
        created = (
            await client.post(
                f"{API}/waiting",
                json={"task_id": task_id, "subject": "ABC Electric", "max_followups": 1},
            )
        ).json()

        response = await client.post(f"{API}/waiting/{created['id']}/followup")
        assert response.status_code == 200
        body = response.json()
        assert body["followup_count"] == 1
        assert body["status"] == "escalated"
        assert body["next_action_at"] is None

    async def test_resolve_closes_the_item(self, env: Env) -> None:
        client, _, container = env
        task_id = await _make_task(container)
        created = (
            await client.post(
                f"{API}/waiting", json={"task_id": task_id, "subject": "ABC Electric"}
            )
        ).json()

        response = await client.post(f"{API}/waiting/{created['id']}/resolve")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "resolved"
        assert body["next_action_at"] is None

    async def test_following_up_on_a_resolved_item_is_a_conflict(self, env: Env) -> None:
        client, _, container = env
        task_id = await _make_task(container)
        created = (
            await client.post(
                f"{API}/waiting", json={"task_id": task_id, "subject": "ABC Electric"}
            )
        ).json()
        await client.post(f"{API}/waiting/{created['id']}/resolve")

        response = await client.post(f"{API}/waiting/{created['id']}/followup")
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"


class TestApprovals:
    async def test_pending_approvals_are_enriched_with_the_action_payload(
        self, env: Env
    ) -> None:
        """Section 58: the Approval screen needs "what will happen" without a
        second round trip to fetch the action."""
        client, _, container = env
        task_id = await _make_task(container)
        action_id, approval_id = await _seed_action_needing_approval(
            container, task_id=task_id
        )

        body = (await client.get(f"{API}/approvals")).json()
        assert body["total"] == 1
        approval = body["approvals"][0]
        assert approval["id"] == approval_id
        assert approval["action_id"] == action_id
        assert approval["action_type"] == "book_appointment"
        assert approval["target_entity_id"] == "provider_abc_electric"
        assert approval["amount"] == "89"
        assert approval["status"] == "pending"
        assert approval["action_payload"] == {
            "time": "Thursday 1-3 PM",
            "amount": "89",
        }
        assert approval["action_status"] == "needs_approval"

    async def test_approving_moves_the_action_to_approved(self, env: Env) -> None:
        client, _, container = env
        action_id, approval_id = await _seed_action_needing_approval(container)

        response = await client.post(
            f"{API}/approvals/{approval_id}/decide", json={"approved": True}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "approved"
        assert body["approved_by"] == CONSOLE.client_id
        assert body["action_status"] == "approved"

        action = (await client.get(f"{API}/actions/{action_id}")).json()
        assert action["status"] == "approved"

    async def test_declining_cancels_the_action(self, env: Env) -> None:
        client, _, container = env
        action_id, approval_id = await _seed_action_needing_approval(container)

        response = await client.post(
            f"{API}/approvals/{approval_id}/decide", json={"approved": False}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "declined"

        action = (await client.get(f"{API}/actions/{action_id}")).json()
        assert action["status"] == "cancelled"
        assert action["failure_reason"] == "declined by the user"

    async def test_declined_approval_no_longer_appears_pending(self, env: Env) -> None:
        client, _, container = env
        _, approval_id = await _seed_action_needing_approval(container)
        await client.post(f"{API}/approvals/{approval_id}/decide", json={"approved": False})

        body = (await client.get(f"{API}/approvals")).json()
        assert body["total"] == 0

    async def test_deciding_an_unknown_approval_is_404(self, env: Env) -> None:
        client, _, _ = env
        response = await client.post(
            f"{API}/approvals/approval_nope/decide", json={"approved": True}
        )
        assert response.status_code == 404


class TestActions:
    async def test_list_and_get_round_trip(self, env: Env) -> None:
        client, _, container = env
        action_id, _ = await _seed_action_needing_approval(container)

        listed = (await client.get(f"{API}/actions")).json()
        assert listed["total"] == 1
        assert listed["actions"][0]["id"] == action_id

        fetched = (await client.get(f"{API}/actions/{action_id}")).json()
        assert fetched["id"] == action_id
        assert fetched["type"] == "book_appointment"
        assert fetched["idempotency_key"]
        assert fetched["payload_hash"]

    async def test_status_filter_narrows_the_list(self, env: Env) -> None:
        client, _, container = env
        needs_approval_id, _ = await _seed_action_needing_approval(container)

        listed = (await client.get(f"{API}/actions?status=needs_approval")).json()
        assert [a["id"] for a in listed["actions"]] == [needs_approval_id]

        listed = (await client.get(f"{API}/actions?status=approved")).json()
        assert listed["actions"] == []

    async def test_unknown_action_is_404(self, env: Env) -> None:
        client, _, _ = env
        response = await client.get(f"{API}/actions/action_nope")
        assert response.status_code == 404


class TestAudit:
    async def test_read_audit_reports_recorded_operations(self, env: Env) -> None:
        client, _, container = env
        task_id = await _make_task(container)
        await client.post(f"{API}/waiting", json={"task_id": task_id, "subject": "ABC"})

        body = (await client.get(f"{API}/audit")).json()
        assert body["total"] >= 1
        assert any(r["intent"] == "create_waiting_item" for r in body["records"])
        assert all(r["client"] == CONSOLE.client_id for r in body["records"])

    async def test_read_audit_filters_by_target(self, env: Env) -> None:
        client, _, container = env
        task_id = await _make_task(container)
        created = (
            await client.post(
                f"{API}/waiting", json={"task_id": task_id, "subject": "ABC"}
            )
        ).json()
        await client.post(f"{API}/waiting", json={"task_id": task_id, "subject": "XYZ"})

        body = (await client.get(f"{API}/audit?target={created['id']}")).json()
        assert body["total"] == 1
        assert body["records"][0]["target"] == created["id"]

    async def test_empty_audit_log_is_honest(self, env: Env) -> None:
        client, _, _ = env
        body = (await client.get(f"{API}/audit")).json()
        assert body == {"records": [], "total": 0}


class TestCapabilities:
    """Durable work is capability-gated like every other surface (section 50)."""

    @staticmethod
    def _override(app: Any, client: ClientIdentity) -> None:
        app.dependency_overrides[get_client] = lambda: client

    async def test_reading_waiting_without_read_tasks_is_403(self, env: Env) -> None:
        client, app, _ = env
        self._override(
            app,
            ClientIdentity(
                client_id="no-caps",
                role=ClientRole.ENGINEERING_ASSISTANT,
                display_name="No capabilities",
                capabilities=frozenset(),
            ),
        )
        response = await client.get(f"{API}/waiting")
        assert response.status_code == 403
        assert response.json()["code"] == "capability_denied"

    async def test_creating_waiting_requires_create_task_not_just_read(
        self, env: Env
    ) -> None:
        client, app, container = env
        task_id = await _make_task(container)
        self._override(
            app,
            ClientIdentity(
                client_id="reader",
                role=ClientRole.ENGINEERING_ASSISTANT,
                display_name="Reader",
                capabilities=frozenset({Capability.READ_TASKS}),
            ),
        )
        response = await client.post(
            f"{API}/waiting", json={"task_id": task_id, "subject": "ABC Electric"}
        )
        assert response.status_code == 403
        assert response.json()["code"] == "capability_denied"

    async def test_deciding_an_approval_requires_approve_action(self, env: Env) -> None:
        client, app, container = env
        _, approval_id = await _seed_action_needing_approval(container)
        self._override(
            app,
            ClientIdentity(
                client_id="reader",
                role=ClientRole.ENGINEERING_ASSISTANT,
                display_name="Reader",
                capabilities=frozenset({Capability.READ_TASKS}),
            ),
        )
        response = await client.post(
            f"{API}/approvals/{approval_id}/decide", json={"approved": True}
        )
        assert response.status_code == 403
        assert response.json()["code"] == "capability_denied"


class TestRoundTrip:
    async def test_the_waiting_screens_whole_loop(self, env: Env) -> None:
        """Section 13's loop: something is created, followed up, and closed."""
        client, _, container = env
        task_id = await _make_task(container, title="Get quote from ABC Electric")

        created = (
            await client.post(
                f"{API}/waiting",
                json={
                    "task_id": task_id,
                    "subject": "ABC Electric",
                    "waiting_on_entity_id": "provider_abc_electric",
                    "max_followups": 2,
                },
            )
        ).json()
        assert created["status"] == "waiting"
        assert created["followup_count"] == 0

        after_followup = (
            await client.post(f"{API}/waiting/{created['id']}/followup")
        ).json()
        assert after_followup["followup_count"] == 1
        assert after_followup["status"] == "waiting"

        resolved = (await client.post(f"{API}/waiting/{created['id']}/resolve")).json()
        assert resolved["status"] == "resolved"

        final = (await client.get(f"{API}/waiting/{created['id']}")).json()
        assert final["status"] == "resolved"
        assert final["followup_count"] == 1

    async def test_the_approval_screens_whole_loop(self, env: Env) -> None:
        """Section 58's loop: prepared, needs approval, approved."""
        client, _, container = env
        action_id, approval_id = await _seed_action_needing_approval(container)

        pending = (await client.get(f"{API}/approvals")).json()
        assert pending["total"] == 1

        decided = (
            await client.post(
                f"{API}/approvals/{approval_id}/decide", json={"approved": True}
            )
        ).json()
        assert decided["status"] == "approved"

        still_pending = (await client.get(f"{API}/approvals")).json()
        assert still_pending["total"] == 0

        action = (await client.get(f"{API}/actions/{action_id}")).json()
        assert action["status"] == ActionStatus.APPROVED.value
