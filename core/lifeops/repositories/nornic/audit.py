"""NornicAuditRepository — the durable audit log in NornicDB (BUILD_SPEC 62).

Graph shape:

    (:AuditRecord {id, requester, user, client, session, intent, tool, risk,
                    approval, action, target, result, verification,
                    timestamp, trace_id, details_json})

Append-only: this module implements ``append``, ``list_recent``, and
``list_for_target`` only. There is deliberately no update or delete Cypher
here — an audit log a caller can rewrite answers no question worth asking.

``details`` is a ``dict[str, str]`` and Neo4j-compatible property values
cannot be maps, so it is stored as the JSON string ``details_json`` — same
discipline as ``facts_json`` in ``world.py``.
"""

from __future__ import annotations

import json
from typing import Any

from lifeops.domain.audit import AuditRecord
from lifeops.repositories.nornic.client import NornicClient

_RETURN = """
    r.id AS id,
    r.requester AS requester,
    r.user AS user,
    r.client AS client,
    r.session AS session,
    r.intent AS intent,
    r.tool AS tool,
    r.risk AS risk,
    r.approval AS approval,
    r.action AS action,
    r.target AS target,
    r.result AS result,
    r.verification AS verification,
    r.timestamp AS timestamp,
    r.trace_id AS trace_id,
    r.details_json AS details_json
"""

_APPEND = """
    CREATE (r:AuditRecord {
        id: $id,
        requester: $requester,
        user: $user,
        client: $client,
        session: $session,
        intent: $intent,
        tool: $tool,
        risk: $risk,
        approval: $approval,
        action: $action,
        target: $target,
        result: $result,
        verification: $verification,
        timestamp: $timestamp,
        trace_id: $trace_id,
        details_json: $details_json
    })
"""


def _row_to_record(row: dict[str, Any]) -> AuditRecord:
    details_raw = row.get("details_json")
    details = json.loads(details_raw) if details_raw else {}
    return AuditRecord(
        id=row["id"],
        requester=row.get("requester"),
        user=row.get("user"),
        client=row["client"],
        session=row.get("session"),
        intent=row.get("intent"),
        tool=row.get("tool"),
        risk=row.get("risk"),
        approval=row.get("approval"),
        action=row.get("action"),
        target=row.get("target"),
        result=row["result"],
        verification=row.get("verification"),
        timestamp=row["timestamp"],
        trace_id=row.get("trace_id"),
        details={str(k): str(v) for k, v in details.items()},
    )


def _write_params(record: AuditRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "requester": record.requester,
        "user": record.user,
        "client": record.client,
        "session": record.session,
        "intent": record.intent,
        "tool": record.tool,
        "risk": record.risk,
        "approval": record.approval,
        "action": record.action,
        "target": record.target,
        "result": record.result,
        "verification": record.verification,
        "timestamp": record.timestamp,
        "trace_id": record.trace_id,
        "details_json": json.dumps(record.details, sort_keys=True),
    }


class NornicAuditRepository:
    def __init__(self, client: NornicClient) -> None:
        self._client = client

    async def append(self, record: AuditRecord) -> AuditRecord:
        await self._client.write(_APPEND, **_write_params(record))
        stored = await self._get(record.id)
        return stored or record

    async def list_recent(self, *, limit: int = 100) -> list[AuditRecord]:
        rows = await self._client.read(
            f"""
            MATCH (r:AuditRecord)
            RETURN {_RETURN}
            ORDER BY r.timestamp DESC, r.id DESC
            LIMIT $limit
            """,
            limit=limit,
        )
        return [_row_to_record(r) for r in rows]

    async def list_for_target(self, target: str, *, limit: int = 100) -> list[AuditRecord]:
        rows = await self._client.read(
            f"""
            MATCH (r:AuditRecord) WHERE r.target = $target
            RETURN {_RETURN}
            ORDER BY r.timestamp DESC, r.id DESC
            LIMIT $limit
            """,
            target=target,
            limit=limit,
        )
        return [_row_to_record(r) for r in rows]

    async def _get(self, record_id: str) -> AuditRecord | None:
        rows = await self._client.read(
            f"MATCH (r:AuditRecord {{id: $id}}) RETURN {_RETURN}", id=record_id
        )
        return _row_to_record(rows[0]) if rows else None
