"""NornicWaitingRepository — waiting-item persistence (BUILD_SPEC 13, 54, 55).

Graph shape:

    (:WaitingItem {id, task_id, subject, waiting_on_entity_id, waiting_since,
                   expected_by, next_action_at, last_contact_at,
                   followup_count, max_followups, status, attempt_count,
                   lease_owner, lease_until, created_by_client})

    (:WaitingItem)-[:WAITING_ON]->(entity)   who/what is being waited on
    (:Task)-[:WAITING_ON]->(:WaitingItem)    the task this item blocks

Both edges use the same relationship type but opposite directions off the
``WaitingItem`` node, so deleting the stale entity edge (``(w)-[:WAITING_ON]->()``)
never touches the incoming task edge (``()-[:WAITING_ON]->(w)``).

``claim`` is the one method that must not read-then-write: it is a single
conditional ``SET`` guarded by a ``WHERE`` clause, so two workers racing for
the same lease cannot both win it (section 55).
"""

from __future__ import annotations

from typing import Any

from lifeops.domain.waiting import ACTIVE_STATUSES, WaitingItem, WaitingStatus
from lifeops.errors import NotFoundError
from lifeops.repositories.nornic.client import NornicClient

_RETURN = """
    w.id AS id,
    w.task_id AS task_id,
    w.subject AS subject,
    w.waiting_on_entity_id AS waiting_on_entity_id,
    w.waiting_since AS waiting_since,
    w.expected_by AS expected_by,
    w.next_action_at AS next_action_at,
    w.last_contact_at AS last_contact_at,
    w.followup_count AS followup_count,
    w.max_followups AS max_followups,
    w.status AS status,
    w.attempt_count AS attempt_count,
    w.lease_owner AS lease_owner,
    w.lease_until AS lease_until,
    w.created_by_client AS created_by_client
"""

_WRITE = """
    MERGE (w:WaitingItem {id: $id})
    SET w.task_id = $task_id,
        w.subject = $subject,
        w.waiting_on_entity_id = $waiting_on_entity_id,
        w.waiting_since = $waiting_since,
        w.expected_by = $expected_by,
        w.next_action_at = $next_action_at,
        w.last_contact_at = $last_contact_at,
        w.followup_count = $followup_count,
        w.max_followups = $max_followups,
        w.status = $status,
        w.attempt_count = $attempt_count,
        w.lease_owner = $lease_owner,
        w.lease_until = $lease_until,
        w.created_by_client = $created_by_client
"""


def _row_to_item(row: dict[str, Any]) -> WaitingItem:
    return WaitingItem(
        id=row["id"],
        task_id=row["task_id"],
        subject=row["subject"],
        waiting_on_entity_id=row.get("waiting_on_entity_id"),
        waiting_since=row["waiting_since"],
        expected_by=row.get("expected_by"),
        next_action_at=row.get("next_action_at"),
        last_contact_at=row.get("last_contact_at"),
        followup_count=int(row.get("followup_count") or 0),
        max_followups=int(row.get("max_followups") or 0),
        status=WaitingStatus(row.get("status") or "waiting"),
        attempt_count=int(row.get("attempt_count") or 0),
        lease_owner=row.get("lease_owner"),
        lease_until=row.get("lease_until"),
        created_by_client=row.get("created_by_client"),
    )


def _write_params(item: WaitingItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "task_id": item.task_id,
        "subject": item.subject,
        "waiting_on_entity_id": item.waiting_on_entity_id,
        "waiting_since": item.waiting_since,
        "expected_by": item.expected_by,
        "next_action_at": item.next_action_at,
        "last_contact_at": item.last_contact_at,
        "followup_count": item.followup_count,
        "max_followups": item.max_followups,
        "status": str(item.status),
        "attempt_count": item.attempt_count,
        "lease_owner": item.lease_owner,
        "lease_until": item.lease_until,
        "created_by_client": item.created_by_client,
    }


def _entity_edge_statement(item: WaitingItem) -> tuple[str, dict[str, Any]] | None:
    if not item.waiting_on_entity_id:
        return None
    return (
        """
        MATCH (w:WaitingItem {id: $waiting_id})
        MATCH (e) WHERE e.id = $entity_id
        MERGE (w)-[:WAITING_ON]->(e)
        """,
        {"waiting_id": item.id, "entity_id": item.waiting_on_entity_id},
    )


def _task_edge_statement(item: WaitingItem) -> tuple[str, dict[str, Any]]:
    return (
        """
        MATCH (t:Task {id: $task_id})
        MATCH (w:WaitingItem {id: $waiting_id})
        MERGE (t)-[:WAITING_ON]->(w)
        """,
        {"task_id": item.task_id, "waiting_id": item.id},
    )


class NornicWaitingRepository:
    def __init__(self, client: NornicClient) -> None:
        self._client = client

    async def get(self, waiting_id: str) -> WaitingItem | None:
        rows = await self._client.read(
            f"MATCH (w:WaitingItem {{id: $id}}) RETURN {_RETURN}", id=waiting_id
        )
        return _row_to_item(rows[0]) if rows else None

    async def list_for_task(self, task_id: str) -> list[WaitingItem]:
        rows = await self._client.read(
            f"""
            MATCH (w:WaitingItem) WHERE w.task_id = $task_id
            RETURN {_RETURN}
            ORDER BY w.waiting_since DESC, w.id DESC
            """,
            task_id=task_id,
        )
        return [_row_to_item(r) for r in rows]

    async def list_by_status(
        self, *, statuses: list[WaitingStatus] | None = None, limit: int = 100
    ) -> list[WaitingItem]:
        clauses: list[str] = []
        params: dict[str, Any] = {"limit": limit}
        if statuses:
            clauses.append("w.status IN $statuses")
            params["statuses"] = [str(s) for s in statuses]
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = await self._client.read(
            f"""
            MATCH (w:WaitingItem)
            {where}
            RETURN {_RETURN}
            ORDER BY w.waiting_since DESC, w.id DESC
            LIMIT $limit
            """,
            **params,
        )
        return [_row_to_item(r) for r in rows]

    async def list_due(self, *, now: str, limit: int = 50) -> list[WaitingItem]:
        rows = await self._client.read(
            f"""
            MATCH (w:WaitingItem)
            WHERE w.status IN $active_statuses
              AND w.next_action_at IS NOT NULL
              AND w.next_action_at <= $now
              AND (w.lease_until IS NULL OR w.lease_until <= $now)
            RETURN {_RETURN}
            ORDER BY w.next_action_at ASC, w.id ASC
            LIMIT $limit
            """,
            active_statuses=[str(s) for s in ACTIVE_STATUSES],
            now=now,
            limit=limit,
        )
        return [_row_to_item(r) for r in rows]

    async def claim(
        self, waiting_id: str, *, owner: str, until: str, now: str
    ) -> WaitingItem | None:
        # Single conditional write, never read-then-write: the WHERE clause
        # is the whole race guard (section 55). A row comes back only when
        # this call is the one that took the lease.
        rows = await self._client.write(
            f"""
            MATCH (w:WaitingItem {{id: $id}})
            WHERE w.lease_until IS NULL OR w.lease_until <= $now
            SET w.lease_owner = $owner, w.lease_until = $until
            RETURN {_RETURN}
            """,
            id=waiting_id,
            owner=owner,
            until=until,
            now=now,
        )
        if not rows:
            return None
        # Built from the write's own returned row, never a follow-up read:
        # CLAUDE.md's visibility quirk means a read issued straight after
        # this auto-commit write can be stale, handing the winner an item
        # whose lease fields are the pre-claim values.
        return _row_to_item(rows[0])

    async def create(self, item: WaitingItem) -> WaitingItem:
        statements: list[tuple[str, dict[str, Any]]] = [(_WRITE, _write_params(item))]
        entity_edge = _entity_edge_statement(item)
        if entity_edge is not None:
            statements.append(entity_edge)
        statements.append(_task_edge_statement(item))
        await self._client.write_many(statements)
        stored = await self.get(item.id)
        return stored or item

    async def update(self, item: WaitingItem) -> WaitingItem:
        existing = await self.get(item.id)
        if existing is None:
            raise NotFoundError(
                f"waiting item {item.id} does not exist", waiting_id=item.id
            )

        statements: list[tuple[str, dict[str, Any]]] = [(_WRITE, _write_params(item))]

        # Same discipline as tasks/world edges: drop the stale WAITING_ON
        # edge before re-adding when the entity being waited on changes.
        if existing.waiting_on_entity_id != item.waiting_on_entity_id:
            statements.append(
                (
                    "MATCH (w:WaitingItem {id: $id})-[r:WAITING_ON]->() DELETE r",
                    {"id": item.id},
                )
            )
            entity_edge = _entity_edge_statement(item)
            if entity_edge is not None:
                statements.append(entity_edge)

        # And the same again for the owning task's incoming edge: without
        # this branch, moving an item to another task updated the property
        # (reads stayed correct — list_for_task uses it) but left the graph
        # permanently showing the item blocking the old task, with no edge
        # from the new one (2026-08-18 audit, P2).
        if existing.task_id != item.task_id:
            statements.append(
                (
                    "MATCH (:Task)-[r:WAITING_ON]->(w:WaitingItem {id: $id}) DELETE r",
                    {"id": item.id},
                )
            )
            statements.append(_task_edge_statement(item))

        await self._client.write_many(statements)
        stored = await self.get(item.id)
        return stored or item
