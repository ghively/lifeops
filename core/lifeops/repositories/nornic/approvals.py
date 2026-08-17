"""NornicApprovalRepository — approvals in NornicDB (BUILD_SPEC 57-59).

Graph shape:

    (:Approval {id, action_id, payload_hash, requested_by, approved_by,
                approved_at, expires_at, consumed_at, status, action_type,
                target_entity_id, amount, created_at})

    (:Approval)-[:AUTHORIZES]->(:Action)   section 59's binding to the action
    (:Person)-[:APPROVED]->(:Approval)     section 59's binding to the human

The ``APPROVED`` edge is written once ``approved_by`` is set — before that
there is no human to point at yet. A dangling ``approved_by`` that is not a
known ``Person`` id (a client identifier, say) matches nothing and simply
leaves no edge, the same dangling-id discipline ``tasks.py`` uses for
``related_entity_ids``.
"""

from __future__ import annotations

from typing import Any

from lifeops.domain.approvals import Approval, ApprovalStatus
from lifeops.errors import NotFoundError
from lifeops.repositories.nornic.client import NornicClient

_RETURN = """
    ap.id AS id,
    ap.action_id AS action_id,
    ap.payload_hash AS payload_hash,
    ap.requested_by AS requested_by,
    ap.approved_by AS approved_by,
    ap.approved_at AS approved_at,
    ap.expires_at AS expires_at,
    ap.consumed_at AS consumed_at,
    ap.status AS status,
    ap.action_type AS action_type,
    ap.authorises_action AS authorises_action,
    ap.does_not_authorise AS does_not_authorise,
    ap.target_entity_id AS target_entity_id,
    ap.amount AS amount,
    ap.created_at AS created_at
"""

_WRITE = """
    MERGE (ap:Approval {id: $id})
    SET ap.action_id = $action_id,
        ap.payload_hash = $payload_hash,
        ap.requested_by = $requested_by,
        ap.approved_by = $approved_by,
        ap.approved_at = $approved_at,
        ap.expires_at = $expires_at,
        ap.consumed_at = $consumed_at,
        ap.status = $status,
        ap.action_type = $action_type,
        ap.authorises_action = $authorises_action,
        ap.does_not_authorise = $does_not_authorise,
        ap.target_entity_id = $target_entity_id,
        ap.amount = $amount,
        ap.created_at = $created_at
"""


def _row_to_approval(row: dict[str, Any]) -> Approval:
    return Approval(
        id=row["id"],
        action_id=row["action_id"],
        payload_hash=row["payload_hash"],
        requested_by=row["requested_by"],
        approved_by=row.get("approved_by"),
        approved_at=row.get("approved_at"),
        expires_at=row["expires_at"],
        consumed_at=row.get("consumed_at"),
        status=ApprovalStatus(row.get("status") or "pending"),
        action_type=row["action_type"],
        authorises_action=row.get("authorises_action") or "",
        does_not_authorise=list(row.get("does_not_authorise") or []),
        target_entity_id=row.get("target_entity_id"),
        amount=row.get("amount"),
        created_at=row["created_at"],
    )


def _write_params(approval: Approval) -> dict[str, Any]:
    return {
        "id": approval.id,
        "action_id": approval.action_id,
        "payload_hash": approval.payload_hash,
        "requested_by": approval.requested_by,
        "approved_by": approval.approved_by,
        "approved_at": approval.approved_at,
        "expires_at": approval.expires_at,
        "consumed_at": approval.consumed_at,
        "status": str(approval.status),
        "action_type": approval.action_type,
        "authorises_action": approval.authorises_action,
        "does_not_authorise": list(approval.does_not_authorise),
        "target_entity_id": approval.target_entity_id,
        "amount": approval.amount,
        "created_at": approval.created_at,
    }


def _authorizes_statement(approval: Approval) -> tuple[str, dict[str, Any]]:
    return (
        """
        MATCH (ap:Approval {id: $approval_id})
        MATCH (a:Action {id: $action_id})
        MERGE (ap)-[:AUTHORIZES]->(a)
        """,
        {"approval_id": approval.id, "action_id": approval.action_id},
    )


def _approved_statement(approval: Approval) -> tuple[str, dict[str, Any]] | None:
    if not approval.approved_by:
        return None
    return (
        """
        MATCH (p:Person {id: $person_id})
        MATCH (ap:Approval {id: $approval_id})
        MERGE (p)-[:APPROVED]->(ap)
        """,
        {"person_id": approval.approved_by, "approval_id": approval.id},
    )


class NornicApprovalRepository:
    def __init__(self, client: NornicClient) -> None:
        self._client = client

    async def get(self, approval_id: str) -> Approval | None:
        rows = await self._client.read(
            f"MATCH (ap:Approval {{id: $id}}) RETURN {_RETURN}", id=approval_id
        )
        return _row_to_approval(rows[0]) if rows else None

    async def get_for_action(self, action_id: str) -> Approval | None:
        rows = await self._client.read(
            f"""
            MATCH (ap:Approval) WHERE ap.action_id = $action_id
            RETURN {_RETURN}
            ORDER BY ap.created_at DESC, ap.id DESC
            LIMIT 1
            """,
            action_id=action_id,
        )
        return _row_to_approval(rows[0]) if rows else None

    async def list_pending(self, *, limit: int = 50) -> list[Approval]:
        rows = await self._client.read(
            f"""
            MATCH (ap:Approval) WHERE ap.status = $status
            RETURN {_RETURN}
            ORDER BY ap.created_at ASC, ap.id ASC
            LIMIT $limit
            """,
            status=str(ApprovalStatus.PENDING),
            limit=limit,
        )
        return [_row_to_approval(r) for r in rows]

    async def create(self, approval: Approval) -> Approval:
        statements: list[tuple[str, dict[str, Any]]] = [
            (_WRITE, _write_params(approval)),
            _authorizes_statement(approval),
        ]
        approved_edge = _approved_statement(approval)
        if approved_edge is not None:
            statements.append(approved_edge)
        await self._client.write_many(statements)
        stored = await self.get(approval.id)
        return stored or approval

    async def update(self, approval: Approval) -> Approval:
        existing = await self.get(approval.id)
        if existing is None:
            raise NotFoundError(
                f"approval {approval.id} does not exist", approval_id=approval.id
            )

        statements: list[tuple[str, dict[str, Any]]] = [(_WRITE, _write_params(approval))]

        if existing.approved_by != approval.approved_by:
            approved_edge = _approved_statement(approval)
            if approved_edge is not None:
                statements.append(approved_edge)

        await self._client.write_many(statements)
        stored = await self.get(approval.id)
        return stored or approval
