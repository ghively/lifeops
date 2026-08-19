"""NornicTaskRepository — Task persistence in NornicDB.

Graph shape:

    (:Task)-[:ASSIGNED_TO]->(:Person)      owner
    (:Task)-[:ABOUT]->(entity)             related entities (Phase 3)

``related_entity_ids`` remains stored as a property and stays the source of
truth for reads: tasks written before Phase 3 carry only the property, and the
migration is write-path only (DATA_MODEL.md). The ABOUT edges exist so the
world graph can traverse task → entity without a property scan.
"""

from __future__ import annotations

import builtins
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


def _about_statements(task: Task) -> list[tuple[str, dict[str, Any]]]:
    """One MERGE per related entity id.

    List predicates over bound collections are not portable across NornicDB
    (verified in Phase 2), and a task's related-entity fan-out is small, so
    each edge gets its own statement inside the surrounding transaction.
    Entities that do not exist match nothing and are skipped — a dangling id
    must not fail the task write.
    """
    return [
        (
            """
            MATCH (t:Task {id: $task_id})
            MATCH (e) WHERE e.id = $entity_id
            MERGE (t)-[:ABOUT]->(e)
            """,
            {"task_id": task.id, "entity_id": entity_id},
        )
        for entity_id in dict.fromkeys(task.related_entity_ids)
    ]


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
            ORDER BY t.created_at DESC, t.id DESC
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
        # CONTAINS + ORDER BY + LIMIT in one clause returns one row per text-
        # index posting on NornicDB, not one per node — a single task came
        # back seven times (found live, 2026-08-19). Sorting and limiting
        # through a WITH stage before the projection avoids the broken plan;
        # DISTINCT is not the fix because this database does not reliably
        # dedupe aliased columns (see shopping.py's find_lists_containing).
        # The seen-set is the belt to that suspender: the invariant is one
        # row per task, and the repository holds it even if the planner
        # regresses differently next time.
        rows = await self._client.read(
            f"""
            MATCH (t:Task)
            WHERE toLower(t.title) CONTAINS $needle
               OR toLower(coalesce(t.description, '')) CONTAINS $needle
            WITH t
            ORDER BY t.created_at DESC, t.id DESC
            LIMIT $limit
            RETURN {_RETURN}
            """,
            needle=query.strip().lower(),
            limit=limit,
        )
        seen: set[str] = set()
        tasks: list[Task] = []
        for row in rows:
            if row["id"] not in seen:
                seen.add(row["id"])
                tasks.append(_row_to_task(row))
        return tasks

    async def list_related_to_entity(self, entity_id: str) -> builtins.list[Task]:
        """Tasks pointing at the entity, from the property and from ABOUT edges.

        The property membership covers pre-Phase-3 tasks that have no edges;
        the edge match covers anything whose property drifted. Results are
        unioned by id, so a task visible through both appears once.
        """
        found: dict[str, Task] = {}
        rows = await self._client.read(
            f"""
            MATCH (t:Task)
            WHERE $entity_id IN coalesce(t.related_entity_ids, [])
            RETURN {_RETURN}
            """,
            entity_id=entity_id,
        )
        for row in rows:
            task = _row_to_task(row)
            found[task.id] = task
        rows = await self._client.read(
            f"""
            MATCH (t:Task)-[:ABOUT]->(e {{id: $entity_id}})
            RETURN {_RETURN}
            """,
            entity_id=entity_id,
        )
        for row in rows:
            task = _row_to_task(row)
            found.setdefault(task.id, task)
        return sorted(found.values(), key=lambda t: (t.created_at, t.id), reverse=True)

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
        statements.extend(_about_statements(task))
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

        # Same discipline for ABOUT: when the related set changes, drop the
        # stale edges before re-adding, so the graph never shows the task
        # pointing at entities it no longer concerns.
        if set(existing.related_entity_ids) != set(task.related_entity_ids):
            statements.append(
                (
                    "MATCH (t:Task {id: $task_id})-[r:ABOUT]->() DELETE r",
                    {"task_id": task.id},
                )
            )
            statements.extend(_about_statements(task))

        await self._client.write_many(statements)
        stored = await self.get(task.id)
        return stored or task
