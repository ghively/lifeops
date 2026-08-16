"""NornicTaskRepository — Task persistence in NornicDB.

Graph shape:

    (:Task)-[:ASSIGNED_TO]->(:Person)      owner
    (:Task)-[:REFERENCES]->(entity)        related entities (Phase 3)

``related_entity_ids`` is stored as a property in Phase 0 because the entity
types it points at do not exist yet. Phase 3 promotes it to real edges, which
is a migration of one repository rather than a change to the domain.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from lifeops.domain.tasks import Task, TaskPriority, TaskState, VerificationState
from lifeops.errors import NotFoundError
from lifeops.repositories.nornic.client import NornicClient

_RETURN = """
    t.id AS id,
    t.title AS title,
    t.description AS description,
    t.state AS state,
    t.priority AS priority,
    t.created_at AS created_at,
    t.updated_at AS updated_at,
    t.due_at AS due_at,
    t.owner_entity_id AS owner_entity_id,
    t.assigned_client AS assigned_client,
    t.current_action AS current_action,
    t.waiting_item_id AS waiting_item_id,
    t.verification_required AS verification_required,
    t.verification_state AS verification_state,
    t.verification_evidence AS verification_evidence,
    t.related_entity_ids AS related_entity_ids,
    t.source AS source,
    t.created_by_client AS created_by_client
"""

_WRITE = """
    MERGE (t:Task {id: $id})
    SET t.title = $title,
        t.description = $description,
        t.state = $state,
        t.priority = $priority,
        t.created_at = $created_at,
        t.updated_at = $updated_at,
        t.due_at = $due_at,
        t.owner_entity_id = $owner_entity_id,
        t.assigned_client = $assigned_client,
        t.current_action = $current_action,
        t.waiting_item_id = $waiting_item_id,
        t.verification_required = $verification_required,
        t.verification_state = $verification_state,
        t.verification_evidence = $verification_evidence,
        t.related_entity_ids = $related_entity_ids,
        t.source = $source,
        t.created_by_client = $created_by_client
"""


def _row_to_task(row: dict[str, Any]) -> Task:
    return Task(
        id=row["id"],
        title=row["title"],
        description=row.get("description"),
        state=TaskState(row["state"]),
        priority=TaskPriority(row.get("priority") or "medium"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        due_at=row.get("due_at"),
        owner_entity_id=row.get("owner_entity_id"),
        assigned_client=row.get("assigned_client"),
        current_action=row.get("current_action"),
        waiting_item_id=row.get("waiting_item_id"),
        verification_required=bool(row.get("verification_required")),
        verification_state=VerificationState(
            row.get("verification_state") or "not_required"
        ),
        verification_evidence=row.get("verification_evidence"),
        related_entity_ids=list(row.get("related_entity_ids") or []),
        source=row.get("source"),
        created_by_client=row.get("created_by_client"),
    )


def _write_params(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "state": str(task.state),
        "priority": str(task.priority),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "due_at": task.due_at,
        "owner_entity_id": task.owner_entity_id,
        "assigned_client": task.assigned_client,
        "current_action": task.current_action,
        "waiting_item_id": task.waiting_item_id,
        "verification_required": task.verification_required,
        "verification_state": str(task.verification_state),
        "verification_evidence": task.verification_evidence,
        "related_entity_ids": task.related_entity_ids,
        "source": task.source,
        "created_by_client": task.created_by_client,
    }


class NornicTaskRepository:
    def __init__(self, client: NornicClient) -> None:
        self._client = client

    async def get(self, task_id: str) -> Task | None:
        rows = await self._client.read(
            f"MATCH (t:Task {{id: $id}}) RETURN {_RETURN}", id=task_id
        )
        return _row_to_task(rows[0]) if rows else None

    async def list(
        self,
        *,
        states: list[TaskState] | None = None,
        owner_entity_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        clauses: list[str] = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}

        if states:
            clauses.append("t.state IN $states")
            params["states"] = [str(s) for s in states]
        if owner_entity_id:
            clauses.append("t.owner_entity_id = $owner_entity_id")
            params["owner_entity_id"] = owner_entity_id

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = await self._client.read(
            f"""
            MATCH (t:Task)
            {where}
            RETURN {_RETURN}
            ORDER BY t.created_at DESC
            SKIP $offset
            LIMIT $limit
            """,
            **params,
        )
        return [_row_to_task(r) for r in rows]

    async def count_by_state(self) -> dict[str, int]:
        rows = await self._client.read(
            "MATCH (t:Task) RETURN t.state AS state, count(*) AS total"
        )
        return {row["state"]: int(row["total"]) for row in rows if row.get("state")}

    async def search(self, query: str, *, limit: int = 25) -> Sequence[Task]:
        rows = await self._client.read(
            f"""
            MATCH (t:Task)
            WHERE toLower(t.title) CONTAINS $needle
               OR toLower(coalesce(t.description, '')) CONTAINS $needle
            RETURN {_RETURN}
            ORDER BY t.created_at DESC
            LIMIT $limit
            """,
            needle=query.strip().lower(),
            limit=limit,
        )
        return [_row_to_task(r) for r in rows]

    async def create(self, task: Task) -> Task:
        statements: list[tuple[str, dict[str, Any]]] = [(_WRITE, _write_params(task))]
        if task.owner_entity_id:
            statements.append(
                (
                    """
                    MATCH (t:Task {id: $task_id})
                    MATCH (owner:Person {id: $owner_id})
                    MERGE (t)-[:ASSIGNED_TO]->(owner)
                    """,
                    {"task_id": task.id, "owner_id": task.owner_entity_id},
                )
            )
        await self._client.write_many(statements)
        stored = await self.get(task.id)
        return stored or task

    async def update(self, task: Task) -> Task:
        existing = await self.get(task.id)
        if existing is None:
            raise NotFoundError(f"task {task.id} does not exist", task_id=task.id)

        statements: list[tuple[str, dict[str, Any]]] = [(_WRITE, _write_params(task))]

        # Owner reassignment has to drop the stale edge, otherwise the graph
        # shows the task assigned to two people at once.
        if existing.owner_entity_id != task.owner_entity_id:
            statements.append(
                (
                    "MATCH (t:Task {id: $task_id})-[r:ASSIGNED_TO]->(:Person) DELETE r",
                    {"task_id": task.id},
                )
            )
            if task.owner_entity_id:
                statements.append(
                    (
                        """
                        MATCH (t:Task {id: $task_id})
                        MATCH (owner:Person {id: $owner_id})
                        MERGE (t)-[:ASSIGNED_TO]->(owner)
                        """,
                        {"task_id": task.id, "owner_id": task.owner_entity_id},
                    )
                )

        await self._client.write_many(statements)
        stored = await self.get(task.id)
        return stored or task
