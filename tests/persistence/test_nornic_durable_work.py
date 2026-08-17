"""Durable-work repositories against a live NornicDB (BUILD_SPEC 13, 51, 54,
55, 57-62).

The fakes in ``repositories/fakes`` prove the domain rules; only these prove
the Cypher is right — the graph shape the Waiting, Actions, Approvals, and
Audit screens will traverse, and the two invariants that only a real database
can break silently:

  * ``WaitingRepository.claim`` really is one atomic conditional write, so two
    workers racing for the same lease cannot both win it (section 55).
  * ``Action.idempotency_key`` really is unique, so a duplicate key — the
    exact failure section 61 exists to prevent — is rejected by the database
    itself rather than by application code that could be skipped.

Skipped automatically when NornicDB is not reachable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from lifeops.domain.actions import (
    Action,
    ActionStatus,
    ActionType,
    make_idempotency_key,
    payload_hash,
)
from lifeops.domain.approvals import Approval, ApprovalStatus
from lifeops.domain.audit import AuditRecord
from lifeops.domain.waiting import WaitingItem, WaitingStatus
from lifeops.errors import NotFoundError, RepositoryError
from lifeops.repositories.nornic.actions import NornicActionRepository
from lifeops.repositories.nornic.approvals import NornicApprovalRepository
from lifeops.repositories.nornic.audit import NornicAuditRepository
from lifeops.repositories.nornic.client import NornicClient
from lifeops.repositories.nornic.waiting import NornicWaitingRepository

pytestmark = [pytest.mark.integration, pytest.mark.persistence]

TS = "2026-01-01T00:00:00Z"


def _later(ts: str, *, seconds: int) -> str:
    moment = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return (moment + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


@dataclass
class DurableStack:
    waiting: NornicWaitingRepository
    actions: NornicActionRepository
    approvals: NornicApprovalRepository
    audit: NornicAuditRepository
    client: NornicClient
    task_id: str
    other_task_id: str
    person_id: str
    entity_id: str
    make_id: object  # Callable[[str], str], tracked for teardown


@pytest.fixture
async def durable(nornic_client: NornicClient, test_label: str):
    """The four repositories plus scaffolding nodes for one isolated test.

    Every id this fixture or a test hands out is tracked and swept in
    teardown by a generic id match, mirroring ``test_nornic_world.py``.
    """
    created: list[str] = []

    def make_id(value: str) -> str:
        created.append(value)
        return value

    task_id = make_id(f"task_{test_label}")
    other_task_id = make_id(f"task_other_{test_label}")
    person_id = make_id(f"person_{test_label}")
    entity_id = make_id(f"provider_{test_label}")

    # One explicit transaction, not four auto-commit writes: a node created
    # by ``write()`` (auto-commit) is not reliably visible yet to a ``MATCH``
    # inside a *separate*, immediately-following ``write_many`` (explicit
    # transaction) — a real NornicDB visibility lag distinct from the
    # already-documented quirks in ``world.py``. Explicit-transaction writes
    # are visible to a later explicit transaction immediately, so scaffolding
    # this way keeps every repository's own ``write_many`` calls race-free.
    await nornic_client.write_many(
        [
            (
                "CREATE (t:Task {id: $id, title: $title})",
                {"id": task_id, "title": "Durable work task"},
            ),
            (
                "CREATE (t:Task {id: $id, title: $title})",
                {"id": other_task_id, "title": "Other task"},
            ),
            (
                "CREATE (p:Person {id: $id, display_name: $name})",
                {"id": person_id, "name": "Approver"},
            ),
            (
                "CREATE (e:Provider {id: $id, display_name: $name})",
                {"id": entity_id, "name": "Provider"},
            ),
        ]
    )

    stack = DurableStack(
        waiting=NornicWaitingRepository(nornic_client),
        actions=NornicActionRepository(nornic_client),
        approvals=NornicApprovalRepository(nornic_client),
        audit=NornicAuditRepository(nornic_client),
        client=nornic_client,
        task_id=task_id,
        other_task_id=other_task_id,
        person_id=person_id,
        entity_id=entity_id,
        make_id=make_id,
    )
    try:
        yield stack
    finally:
        for entity_id_ in created:
            await nornic_client.write("MATCH (n {id: $id}) DETACH DELETE n", id=entity_id_)


def _waiting_item(stack: DurableStack, *, suffix: str, **overrides: object) -> WaitingItem:
    defaults: dict[str, object] = dict(
        id=stack.make_id(f"waiting_{suffix}"),
        task_id=stack.task_id,
        subject="Refund from ABC Electric",
        waiting_since=TS,
    )
    defaults.update(overrides)
    return WaitingItem(**defaults)


def _action(stack: DurableStack, *, suffix: str, **overrides: object) -> Action:
    payload = {"to": "abc@example.com"}
    defaults: dict[str, object] = dict(
        id=stack.make_id(f"action_{suffix}"),
        type=ActionType.SEND_EMAIL,
        idempotency_key=make_idempotency_key(ActionType.SEND_EMAIL, payload),
        payload_hash=payload_hash(payload),
        payload=payload,
        task_id=stack.task_id,
        created_at=TS,
    )
    defaults.update(overrides)
    return Action(**defaults)


def _approval(stack: DurableStack, action: Action, *, suffix: str, **overrides: object) -> Approval:
    defaults: dict[str, object] = dict(
        id=stack.make_id(f"approval_{suffix}"),
        action_id=action.id,
        payload_hash=action.payload_hash,
        requested_by="hermes",
        expires_at=_later(TS, seconds=1800),
        action_type=str(action.type),
        created_at=TS,
    )
    defaults.update(overrides)
    return Approval(**defaults)


def _audit_record(stack: DurableStack, *, suffix: str, **overrides: object) -> AuditRecord:
    defaults: dict[str, object] = dict(
        id=stack.make_id(f"audit_{suffix}"),
        client="lifeops-console",
        result="success",
        timestamp=TS,
    )
    defaults.update(overrides)
    return AuditRecord(**defaults)


class TestWaitingRepository:
    async def test_create_and_get(self, durable: DurableStack) -> None:
        item = await durable.waiting.create(_waiting_item(durable, suffix="one"))
        fetched = await durable.waiting.get(item.id)
        assert fetched is not None
        assert fetched.subject == "Refund from ABC Electric"
        assert fetched.status is WaitingStatus.WAITING

    async def test_get_returns_none_for_an_absent_item(self, durable: DurableStack) -> None:
        assert await durable.waiting.get("waiting_never_created") is None

    async def test_task_waiting_on_edge_is_written(self, durable: DurableStack) -> None:
        item = await durable.waiting.create(_waiting_item(durable, suffix="edge"))
        rows = await durable.client.read(
            "MATCH (t:Task {id: $task_id})-[:WAITING_ON]->(w:WaitingItem {id: $wid}) "
            "RETURN w.id AS id",
            task_id=durable.task_id,
            wid=item.id,
        )
        assert len(rows) == 1

    async def test_waiting_on_entity_edge_is_written(self, durable: DurableStack) -> None:
        item = await durable.waiting.create(
            _waiting_item(durable, suffix="entity", waiting_on_entity_id=durable.entity_id)
        )
        rows = await durable.client.read(
            "MATCH (w:WaitingItem {id: $wid})-[:WAITING_ON]->(e {id: $eid}) "
            "RETURN e.id AS id",
            wid=item.id,
            eid=durable.entity_id,
        )
        assert len(rows) == 1

    async def test_list_for_task(self, durable: DurableStack) -> None:
        item = await durable.waiting.create(_waiting_item(durable, suffix="list"))
        other = await durable.waiting.create(
            _waiting_item(durable, suffix="other_task", task_id=durable.other_task_id)
        )
        listed = await durable.waiting.list_for_task(durable.task_id)
        assert [i.id for i in listed] == [item.id]
        assert other.id not in {i.id for i in listed}

    async def test_list_by_status_filters(self, durable: DurableStack) -> None:
        waiting_item = await durable.waiting.create(_waiting_item(durable, suffix="status_a"))
        resolved = await durable.waiting.create(
            _waiting_item(durable, suffix="status_b", status=WaitingStatus.RESOLVED)
        )
        listed = await durable.waiting.list_by_status(statuses=[WaitingStatus.WAITING])
        listed_ids = {i.id for i in listed}
        assert waiting_item.id in listed_ids
        assert resolved.id not in listed_ids

    async def test_list_due_finds_only_active_unleased_due_items(
        self, durable: DurableStack
    ) -> None:
        due = await durable.waiting.create(
            _waiting_item(durable, suffix="due", next_action_at=TS)
        )
        not_yet = await durable.waiting.create(
            _waiting_item(
                durable, suffix="not_yet", next_action_at=_later(TS, seconds=3600)
            )
        )
        leased = await durable.waiting.create(
            _waiting_item(
                durable,
                suffix="leased",
                next_action_at=TS,
                lease_owner="other-worker",
                lease_until=_later(TS, seconds=3600),
            )
        )
        resolved = await durable.waiting.create(
            _waiting_item(
                durable,
                suffix="resolved",
                next_action_at=TS,
                status=WaitingStatus.RESOLVED,
            )
        )

        due_now = await durable.waiting.list_due(now=_later(TS, seconds=10))
        due_ids = {i.id for i in due_now}
        assert due.id in due_ids
        assert not_yet.id not in due_ids
        assert leased.id not in due_ids
        assert resolved.id not in due_ids

    async def test_expired_lease_is_due_again(self, durable: DurableStack) -> None:
        item = await durable.waiting.create(
            _waiting_item(
                durable,
                suffix="expired_lease",
                next_action_at=TS,
                lease_owner="dead-worker",
                lease_until=TS,
            )
        )
        due = await durable.waiting.list_due(now=_later(TS, seconds=10))
        assert item.id in {i.id for i in due}

    async def test_claim_takes_an_unheld_lease(self, durable: DurableStack) -> None:
        item = await durable.waiting.create(_waiting_item(durable, suffix="claim"))
        claimed = await durable.waiting.claim(
            item.id, owner="worker-1", until=_later(TS, seconds=300), now=TS
        )
        assert claimed is not None
        assert claimed.lease_owner == "worker-1"

    async def test_claim_fails_against_a_live_lease(self, durable: DurableStack) -> None:
        item = await durable.waiting.create(_waiting_item(durable, suffix="race"))
        first = await durable.waiting.claim(
            item.id, owner="worker-1", until=_later(TS, seconds=300), now=TS
        )
        assert first is not None

        second = await durable.waiting.claim(
            item.id, owner="worker-2", until=_later(TS, seconds=300), now=TS
        )
        assert second is None
        # The first worker's lease must survive the second worker's attempt.
        current = await durable.waiting.get(item.id)
        assert current is not None
        assert current.lease_owner == "worker-1"

    async def test_claim_succeeds_once_the_lease_has_expired(
        self, durable: DurableStack
    ) -> None:
        item = await durable.waiting.create(
            _waiting_item(
                durable,
                suffix="expired_claim",
                lease_owner="dead-worker",
                lease_until=TS,
            )
        )
        claimed = await durable.waiting.claim(
            item.id,
            owner="worker-2",
            until=_later(TS, seconds=300),
            now=_later(TS, seconds=10),
        )
        assert claimed is not None
        assert claimed.lease_owner == "worker-2"

    async def test_claim_against_a_missing_item_returns_none(
        self, durable: DurableStack
    ) -> None:
        result = await durable.waiting.claim(
            "waiting_never_created", owner="worker-1", until=TS, now=TS
        )
        assert result is None

    async def test_update_persists_changed_fields(self, durable: DurableStack) -> None:
        item = await durable.waiting.create(_waiting_item(durable, suffix="update"))
        item.followup_count = 1
        item.status = WaitingStatus.ESCALATED
        updated = await durable.waiting.update(item)
        assert updated.followup_count == 1
        assert updated.status is WaitingStatus.ESCALATED

    async def test_update_moves_the_waiting_on_edge(self, durable: DurableStack) -> None:
        item = await durable.waiting.create(
            _waiting_item(durable, suffix="move", waiting_on_entity_id=durable.entity_id)
        )
        other_entity = durable.make_id(f"provider_other_{durable.entity_id}")
        # write_many, not write: see the fixture's comment on the auto-commit
        # to explicit-transaction visibility lag this must avoid.
        await durable.client.write_many(
            [
                (
                    "CREATE (e:Provider {id: $id, display_name: $name})",
                    {"id": other_entity, "name": "Second Provider"},
                )
            ]
        )
        item.waiting_on_entity_id = other_entity
        await durable.waiting.update(item)

        rows = await durable.client.read(
            "MATCH (w:WaitingItem {id: $wid})-[:WAITING_ON]->(e) RETURN e.id AS id",
            wid=item.id,
        )
        assert [r["id"] for r in rows] == [other_entity]

        # The task edge must survive the entity edge move.
        task_rows = await durable.client.read(
            "MATCH (t:Task {id: $tid})-[:WAITING_ON]->(w:WaitingItem {id: $wid}) "
            "RETURN w.id AS id",
            tid=durable.task_id,
            wid=item.id,
        )
        assert len(task_rows) == 1

    async def test_updating_a_missing_item_raises(self, durable: DurableStack) -> None:
        item = _waiting_item(durable, suffix="ghost")
        with pytest.raises(NotFoundError):
            await durable.waiting.update(item)


class TestActionRepository:
    async def test_create_and_get_round_trips_the_payload(
        self, durable: DurableStack
    ) -> None:
        action = await durable.actions.create(_action(durable, suffix="one"))
        fetched = await durable.actions.get(action.id)
        assert fetched is not None
        assert fetched.payload == {"to": "abc@example.com"}
        assert fetched.status is ActionStatus.PREPARED

    async def test_get_by_idempotency_key(self, durable: DurableStack) -> None:
        action = await durable.actions.create(_action(durable, suffix="idem"))
        found = await durable.actions.get_by_idempotency_key(action.idempotency_key)
        assert found is not None
        assert found.id == action.id

    async def test_get_by_idempotency_key_returns_none_when_absent(
        self, durable: DurableStack
    ) -> None:
        assert await durable.actions.get_by_idempotency_key("send_email:absent") is None

    async def test_for_task_edge_is_written(self, durable: DurableStack) -> None:
        action = await durable.actions.create(_action(durable, suffix="edge"))
        rows = await durable.client.read(
            "MATCH (a:Action {id: $aid})-[:FOR_TASK]->(t:Task {id: $tid}) "
            "RETURN a.id AS id",
            aid=action.id,
            tid=durable.task_id,
        )
        assert len(rows) == 1

    async def test_list_for_task(self, durable: DurableStack) -> None:
        action = await durable.actions.create(_action(durable, suffix="list"))
        other_payload = {"to": "else@example.com"}
        other = await durable.actions.create(
            _action(
                durable,
                suffix="other",
                task_id=durable.other_task_id,
                idempotency_key=make_idempotency_key(ActionType.SEND_EMAIL, other_payload),
                payload_hash=payload_hash(other_payload),
                payload=other_payload,
            )
        )
        listed = await durable.actions.list_for_task(durable.task_id)
        assert [a.id for a in listed] == [action.id]
        assert other.id not in {a.id for a in listed}

    async def test_list_by_status_filters(self, durable: DurableStack) -> None:
        prepared = await durable.actions.create(_action(durable, suffix="prepared"))
        executed_payload = {"to": "done@example.com"}
        executed = await durable.actions.create(
            _action(
                durable,
                suffix="executed",
                idempotency_key=make_idempotency_key(ActionType.SEND_EMAIL, executed_payload),
                payload_hash=payload_hash(executed_payload),
                payload=executed_payload,
                status=ActionStatus.EXECUTED,
            )
        )
        listed = await durable.actions.list_by_status(statuses=[ActionStatus.PREPARED])
        listed_ids = {a.id for a in listed}
        assert prepared.id in listed_ids
        assert executed.id not in listed_ids

    async def test_update_persists_status_and_attempt_fields(
        self, durable: DurableStack
    ) -> None:
        action = await durable.actions.create(_action(durable, suffix="update"))
        action.status = ActionStatus.EXECUTING
        action.attempt_count = 1
        action.last_attempt_at = TS
        updated = await durable.actions.update(action)
        assert updated.status is ActionStatus.EXECUTING
        assert updated.attempt_count == 1

    async def test_updating_a_missing_action_raises(self, durable: DurableStack) -> None:
        action = _action(durable, suffix="ghost")
        with pytest.raises(NotFoundError):
            await durable.actions.update(action)

    async def test_idempotency_key_uniqueness_is_enforced_by_the_database(
        self, durable: DurableStack
    ) -> None:
        """Section 61: two Action nodes must never share a key.

        This asserts the constraint itself does the work, not application
        code that a future caller could accidentally bypass.
        """
        first = await durable.actions.create(_action(durable, suffix="dupe_one"))
        clashing = Action(
            id=durable.make_id("action_dupe_two"),
            type=ActionType.SEND_EMAIL,
            idempotency_key=first.idempotency_key,
            payload_hash=first.payload_hash,
            payload={"to": "different@example.com"},
            task_id=durable.task_id,
            created_at=TS,
        )
        with pytest.raises(RepositoryError):
            await durable.actions.create(clashing)


class TestApprovalRepository:
    async def test_create_and_get(self, durable: DurableStack) -> None:
        action = await durable.actions.create(_action(durable, suffix="for_approval"))
        approval = await durable.approvals.create(_approval(durable, action, suffix="one"))
        fetched = await durable.approvals.get(approval.id)
        assert fetched is not None
        assert fetched.status is ApprovalStatus.PENDING
        assert fetched.action_id == action.id

    async def test_authorizes_edge_is_written(self, durable: DurableStack) -> None:
        action = await durable.actions.create(_action(durable, suffix="auth"))
        approval = await durable.approvals.create(_approval(durable, action, suffix="auth"))
        rows = await durable.client.read(
            "MATCH (ap:Approval {id: $apid})-[:AUTHORIZES]->(a:Action {id: $aid}) "
            "RETURN ap.id AS id",
            apid=approval.id,
            aid=action.id,
        )
        assert len(rows) == 1

    async def test_get_for_action_returns_the_latest(self, durable: DurableStack) -> None:
        action = await durable.actions.create(_action(durable, suffix="latest"))
        await durable.approvals.create(
            _approval(durable, action, suffix="older", created_at=TS)
        )
        newest = await durable.approvals.create(
            _approval(
                durable, action, suffix="newer", created_at=_later(TS, seconds=60)
            )
        )
        found = await durable.approvals.get_for_action(action.id)
        assert found is not None
        assert found.id == newest.id

    async def test_list_pending_excludes_decided_approvals(
        self, durable: DurableStack
    ) -> None:
        action = await durable.actions.create(_action(durable, suffix="pending"))
        pending = await durable.approvals.create(
            _approval(durable, action, suffix="pending")
        )
        approved = await durable.approvals.create(
            _approval(
                durable,
                action,
                suffix="approved",
                status=ApprovalStatus.APPROVED,
                approved_by=durable.person_id,
                approved_at=TS,
            )
        )
        listed = await durable.approvals.list_pending()
        listed_ids = {a.id for a in listed}
        assert pending.id in listed_ids
        assert approved.id not in listed_ids

    async def test_update_writes_the_approved_edge(self, durable: DurableStack) -> None:
        action = await durable.actions.create(_action(durable, suffix="decide"))
        approval = await durable.approvals.create(_approval(durable, action, suffix="decide"))

        approval.status = ApprovalStatus.APPROVED
        approval.approved_by = durable.person_id
        approval.approved_at = TS
        await durable.approvals.update(approval)

        rows = await durable.client.read(
            "MATCH (p:Person {id: $pid})-[:APPROVED]->(ap:Approval {id: $apid}) "
            "RETURN ap.id AS id",
            pid=durable.person_id,
            apid=approval.id,
        )
        assert len(rows) == 1

    async def test_updating_a_missing_approval_raises(self, durable: DurableStack) -> None:
        action = _action(durable, suffix="phantom_action")
        approval = _approval(durable, action, suffix="ghost")
        with pytest.raises(NotFoundError):
            await durable.approvals.update(approval)


class TestAuditRepository:
    async def test_append_and_get_round_trips_details(self, durable: DurableStack) -> None:
        record = await durable.audit.append(
            _audit_record(
                durable,
                suffix="one",
                target=durable.task_id,
                details={"reason": "booked appointment"},
            )
        )
        listed = await durable.audit.list_recent(limit=50)
        found = next((r for r in listed if r.id == record.id), None)
        assert found is not None
        assert found.details == {"reason": "booked appointment"}

    async def test_list_recent_orders_newest_first(self, durable: DurableStack) -> None:
        older = await durable.audit.append(
            _audit_record(durable, suffix="older", timestamp=TS)
        )
        newer = await durable.audit.append(
            _audit_record(durable, suffix="newer", timestamp=_later(TS, seconds=60))
        )
        listed = await durable.audit.list_recent(limit=50)
        ids_in_order = [r.id for r in listed if r.id in {older.id, newer.id}]
        assert ids_in_order == [newer.id, older.id]

    async def test_list_for_target(self, durable: DurableStack) -> None:
        matching = await durable.audit.append(
            _audit_record(durable, suffix="target", target=durable.task_id)
        )
        other = await durable.audit.append(
            _audit_record(durable, suffix="other_target", target=durable.entity_id)
        )
        listed = await durable.audit.list_for_target(durable.task_id)
        listed_ids = {r.id for r in listed}
        assert matching.id in listed_ids
        assert other.id not in listed_ids

    def test_the_repository_exposes_no_update_or_delete(self) -> None:
        """Append-only is enforced by the absent method, not a convention."""
        assert not hasattr(NornicAuditRepository, "update")
        assert not hasattr(NornicAuditRepository, "delete")
