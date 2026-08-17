"""NornicActionRepository — the action outbox in NornicDB (BUILD_SPEC 51, 60, 61).

Graph shape:

    (:Action {id, type, status, idempotency_key, payload_hash, payload_json,
              task_id, target_entity_id, created_at, attempt_count,
              last_attempt_at, external_reference, verification_state,
              failure_reason, created_by_client})

    (:Action)-[:FOR_TASK]->(:Task)

``payload`` is a dict and Neo4j-compatible property values cannot be maps, so
it is stored as the JSON string ``payload_json`` — same discipline as
``facts_json`` in ``world.py``, keys sorted so identical payloads compare
equal.

Section 61 makes ``idempotency_key`` the mechanism that prevents a blind
retry from double-booking or double-charging; the uniqueness constraint lives
in ``client.py``.
"""

from __future__ import annotations

import json
from typing import Any

from lifeops.domain.actions import Action, ActionStatus, ActionType
from lifeops.domain.tasks import VerificationState
from lifeops.errors import NotFoundError
from lifeops.repositories.nornic.client import NornicClient

_RETURN = """
    a.id AS id,
    a.type AS type,
    a.status AS status,
    a.idempotency_key AS idempotency_key,
    a.payload_hash AS payload_hash,
    a.payload_json AS payload_json,
    a.task_id AS task_id,
    a.target_entity_id AS target_entity_id,
    a.created_at AS created_at,
    a.attempt_count AS attempt_count,
    a.last_attempt_at AS last_attempt_at,
    a.external_reference AS external_reference,
    a.verification_state AS verification_state,
    a.failure_reason AS failure_reason,
    a.created_by_client AS created_by_client
"""

_WRITE = """
    MERGE (a:Action {id: $id})
    SET a.type = $type,
        a.status = $status,
        a.idempotency_key = $idempotency_key,
        a.payload_hash = $payload_hash,
        a.payload_json = $payload_json,
        a.task_id = $task_id,
        a.target_entity_id = $target_entity_id,
        a.created_at = $created_at,
        a.attempt_count = $attempt_count,
        a.last_attempt_at = $last_attempt_at,
        a.external_reference = $external_reference,
        a.verification_state = $verification_state,
        a.failure_reason = $failure_reason,
        a.created_by_client = $created_by_client
"""


def _row_to_action(row: dict[str, Any]) -> Action:
    payload_raw = row.get("payload_json")
    payload = json.loads(payload_raw) if payload_raw else {}
    return Action(
        id=row["id"],
        type=ActionType(row["type"]),
        status=ActionStatus(row.get("status") or "prepared"),
        idempotency_key=row["idempotency_key"],
        payload_hash=row["payload_hash"],
        payload=payload,
        task_id=row.get("task_id"),
        target_entity_id=row.get("target_entity_id"),
        created_at=row["created_at"],
        attempt_count=int(row.get("attempt_count") or 0),
        last_attempt_at=row.get("last_attempt_at"),
        external_reference=row.get("external_reference"),
        verification_state=VerificationState(row.get("verification_state") or "pending"),
        failure_reason=row.get("failure_reason"),
        created_by_client=row.get("created_by_client"),
    )


def _write_params(action: Action) -> dict[str, Any]:
    return {
        "id": action.id,
        "type": str(action.type),
        "status": str(action.status),
        "idempotency_key": action.idempotency_key,
        "payload_hash": action.payload_hash,
        "payload_json": json.dumps(action.payload, sort_keys=True),
        "task_id": action.task_id,
        "target_entity_id": action.target_entity_id,
        "created_at": action.created_at,
        "attempt_count": action.attempt_count,
        "last_attempt_at": action.last_attempt_at,
        "external_reference": action.external_reference,
        "verification_state": str(action.verification_state),
        "failure_reason": action.failure_reason,
        "created_by_client": action.created_by_client,
    }


def _task_edge_statement(action: Action) -> tuple[str, dict[str, Any]] | None:
    if not action.task_id:
        return None
    return (
        """
        MATCH (a:Action {id: $action_id})
        MATCH (t:Task {id: $task_id})
        MERGE (a)-[:FOR_TASK]->(t)
        """,
        {"action_id": action.id, "task_id": action.task_id},
    )


class NornicActionRepository:
    def __init__(self, client: NornicClient) -> None:
        self._client = client

    async def get(self, action_id: str) -> Action | None:
        rows = await self._client.read(
            f"MATCH (a:Action {{id: $id}}) RETURN {_RETURN}", id=action_id
        )
        return _row_to_action(rows[0]) if rows else None

    async def get_by_idempotency_key(self, key: str) -> Action | None:
        rows = await self._client.read(
            f"MATCH (a:Action {{idempotency_key: $key}}) RETURN {_RETURN}", key=key
        )
        return _row_to_action(rows[0]) if rows else None

    async def list_for_task(self, task_id: str) -> list[Action]:
        rows = await self._client.read(
            f"""
            MATCH (a:Action) WHERE a.task_id = $task_id
            RETURN {_RETURN}
            ORDER BY a.created_at DESC, a.id DESC
            """,
            task_id=task_id,
        )
        return [_row_to_action(r) for r in rows]

    async def list_by_status(
        self, *, statuses: list[ActionStatus] | None = None, limit: int = 100
    ) -> list[Action]:
        clauses: list[str] = []
        params: dict[str, Any] = {"limit": limit}
        if statuses:
            clauses.append("a.status IN $statuses")
            params["statuses"] = [str(s) for s in statuses]
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = await self._client.read(
            f"""
            MATCH (a:Action)
            {where}
            RETURN {_RETURN}
            ORDER BY a.created_at DESC, a.id DESC
            LIMIT $limit
            """,
            **params,
        )
        return [_row_to_action(r) for r in rows]

    async def create(self, action: Action) -> Action:
        statements: list[tuple[str, dict[str, Any]]] = [(_WRITE, _write_params(action))]
        task_edge = _task_edge_statement(action)
        if task_edge is not None:
            statements.append(task_edge)
        await self._client.write_many(statements)
        stored = await self.get(action.id)
        return stored or action

    async def update(self, action: Action) -> Action:
        existing = await self.get(action.id)
        if existing is None:
            raise NotFoundError(
                f"action {action.id} does not exist", action_id=action.id
            )

        statements: list[tuple[str, dict[str, Any]]] = [(_WRITE, _write_params(action))]

        if existing.task_id != action.task_id:
            statements.append(
                (
                    "MATCH (a:Action {id: $id})-[r:FOR_TASK]->(:Task) DELETE r",
                    {"id": action.id},
                )
            )
            task_edge = _task_edge_statement(action)
            if task_edge is not None:
                statements.append(task_edge)

        await self._client.write_many(statements)
        stored = await self.get(action.id)
        return stored or action
