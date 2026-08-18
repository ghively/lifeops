"""NornicBillRepository — bills and payees in NornicDB (BUILD_SPEC 72, 99).

Graph shape:

    (:Bill {id, payee_id, description, amount, currency, due_at, status, ...})
    (:Payee {id, display_name, secret_ref, approved_at, ...})

    (:Bill)-[:OWED_TO]->(:Payee)
    (:Payee)-[:PAYEE_FOR]->(entity)     when the payee is a known provider

``amount`` is stored as the string the domain validated, never as a float:
money in binary floating point is how 89.10 becomes 89.09999999999999, and
this value is hashed into an approval binding where a representation-induced
difference of a cent would silently invalidate — or worse, fail to invalidate
— a human's decision.

``coalesce`` is deliberately absent from every SET clause here — see
``upsert_payee`` for what it does on this database.

No credential is ever written here. A Payee carries ``secret_ref``, a handle
into the encrypted secret store; section 72 requires that credentials are
never exposed to Hermes, and the simplest way to guarantee that is for them
never to enter the graph at all.
"""

from __future__ import annotations

from typing import Any

from lifeops.domain.bills import Bill, BillStatus, Payee
from lifeops.errors import NotFoundError
from lifeops.repositories.nornic.client import NornicClient

_BILL_RETURN = """
    b.id AS id,
    b.payee_id AS payee_id,
    b.description AS description,
    b.amount AS amount,
    b.currency AS currency,
    b.due_at AS due_at,
    b.status AS status,
    b.action_id AS action_id,
    b.paid_at AS paid_at,
    b.external_reference AS external_reference,
    b.source_document_id AS source_document_id,
    b.created_at AS created_at,
    b.updated_at AS updated_at,
    b.created_by_client AS created_by_client
"""

_PAYEE_RETURN = """
    p.id AS id,
    p.display_name AS display_name,
    p.provider_entity_id AS provider_entity_id,
    p.secret_ref AS secret_ref,
    p.created_at AS created_at,
    p.approved_at AS approved_at,
    p.approved_by AS approved_by,
    p.created_by_client AS created_by_client
"""


def _row_to_bill(row: dict[str, Any]) -> Bill:
    return Bill(
        id=row["id"],
        payee_id=row["payee_id"],
        description=row["description"],
        amount=row["amount"],
        currency=row.get("currency") or "USD",
        due_at=row.get("due_at"),
        status=BillStatus(row["status"]),
        action_id=row.get("action_id"),
        paid_at=row.get("paid_at"),
        external_reference=row.get("external_reference"),
        source_document_id=row.get("source_document_id"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by_client=row.get("created_by_client"),
    )


def _row_to_payee(row: dict[str, Any]) -> Payee:
    return Payee(
        id=row["id"],
        display_name=row["display_name"],
        provider_entity_id=row.get("provider_entity_id"),
        secret_ref=row.get("secret_ref"),
        created_at=row["created_at"],
        approved_at=row.get("approved_at"),
        approved_by=row.get("approved_by"),
        created_by_client=row.get("created_by_client"),
    )


def _bill_params(bill: Bill) -> dict[str, Any]:
    return bill.model_dump(mode="json")


class NornicBillRepository:
    def __init__(self, client: NornicClient) -> None:
        self._client = client

    async def get(self, bill_id: str) -> Bill | None:
        rows = await self._client.read(
            f"MATCH (b:Bill {{id: $id}}) RETURN {_BILL_RETURN}", id=bill_id
        )
        return _row_to_bill(rows[0]) if rows else None

    async def list_bills(
        self, *, statuses: list[BillStatus] | None = None, limit: int = 100
    ) -> list[Bill]:
        if statuses is None:
            rows = await self._client.read(
                f"MATCH (b:Bill) RETURN {_BILL_RETURN} "
                "ORDER BY b.due_at ASC, b.id ASC LIMIT $limit",
                limit=limit,
            )
        else:
            rows = await self._client.read(
                f"MATCH (b:Bill) WHERE b.status IN $statuses RETURN {_BILL_RETURN} "
                "ORDER BY b.due_at ASC, b.id ASC LIMIT $limit",
                statuses=[str(s) for s in statuses],
                limit=limit,
            )
        return [_row_to_bill(r) for r in rows]

    async def list_for_payee(self, payee_id: str) -> list[Bill]:
        rows = await self._client.read(
            f"MATCH (b:Bill {{payee_id: $payee_id}}) RETURN {_BILL_RETURN} "
            "ORDER BY b.created_at DESC, b.id DESC",
            payee_id=payee_id,
        )
        return [_row_to_bill(r) for r in rows]

    async def create(self, bill: Bill) -> Bill:
        # The bill and its OWED_TO edge go in one transaction. The Payee node
        # was written earlier by auto-commit ``write`` (``upsert_payee``), and
        # auto-commit-to-transaction visibility races on NornicDB — so the
        # MATCH below can miss a freshly created payee and the MERGE silently
        # no-ops. That is survivable only because ``b.payee_id`` is the source
        # of truth (``list_for_payee`` reads the property, never the edge);
        # the edge is display-only and a dropped one degrades, not corrupts.
        await self._client.write_many(
            [
                (
                    """
                    MERGE (b:Bill {id: $id})
                    SET b.payee_id = $payee_id,
                        b.description = $description,
                        b.amount = $amount,
                        b.currency = $currency,
                        b.due_at = $due_at,
                        b.status = $status,
                        b.action_id = $action_id,
                        b.paid_at = $paid_at,
                        b.external_reference = $external_reference,
                        b.source_document_id = $source_document_id,
                        b.created_at = $created_at,
                        b.updated_at = $updated_at,
                        b.created_by_client = $created_by_client
                    """,
                    _bill_params(bill),
                ),
                (
                    """
                    MATCH (b:Bill {id: $id})
                    MATCH (p:Payee {id: $payee_id})
                    MERGE (b)-[:OWED_TO]->(p)
                    """,
                    {"id": bill.id, "payee_id": bill.payee_id},
                ),
            ]
        )
        stored = await self.get(bill.id)
        return stored or bill

    async def update(self, bill: Bill) -> Bill:
        existing = await self.get(bill.id)
        if existing is None:
            raise NotFoundError(f"bill {bill.id} does not exist", bill_id=bill.id)
        await self._client.write(
            """
            MATCH (b:Bill {id: $id})
            SET b.payee_id = $payee_id,
                b.description = $description,
                b.amount = $amount,
                b.currency = $currency,
                b.due_at = $due_at,
                b.status = $status,
                b.action_id = $action_id,
                b.paid_at = $paid_at,
                b.external_reference = $external_reference,
                b.source_document_id = $source_document_id,
                b.updated_at = $updated_at
            """,
            **_bill_params(bill),
        )
        stored = await self.get(bill.id)
        return stored or bill

    async def get_payee(self, payee_id: str) -> Payee | None:
        rows = await self._client.read(
            f"MATCH (p:Payee {{id: $id}}) RETURN {_PAYEE_RETURN}", id=payee_id
        )
        return _row_to_payee(rows[0]) if rows else None

    async def list_payees(self) -> list[Payee]:
        rows = await self._client.read(
            f"MATCH (p:Payee) RETURN {_PAYEE_RETURN} ORDER BY p.display_name ASC"
        )
        return [_row_to_payee(r) for r in rows]

    async def upsert_payee(self, payee: Payee) -> Payee:
        """Create or update a payee, preserving an existing approval.

        The preservation is done in Python, not with ``coalesce`` in the SET
        clause. NornicDB does not evaluate ``coalesce(p.x, $param)`` when
        creating a node with a null parameter — it stores the *expression
        text* as the property value. That produced a non-null
        ``approved_at`` of ``"coalesce(p.approved_at, null)"``, which read as
        approved, which would have made every new payee look like one a human
        had already accepted. Section 72's gate would have been defeated by a
        Cypher builtin.
        """
        existing = await self.get_payee(payee.id)
        merged = payee.model_copy(deep=True)
        if existing is not None:
            merged.created_at = existing.created_at or merged.created_at
            # Approval is a fact about a payee, not a field a later write may
            # reset. Carried forward when the incoming record is unapproved;
            # an incoming approval is a human's newer decision and wins, so
            # ``approved_by`` keeps agreeing with the audit line that named
            # the approving client.
            if existing.is_approved and not merged.is_approved:
                merged.approved_at = existing.approved_at
                merged.approved_by = existing.approved_by

        await self._client.write(
            """
            MERGE (p:Payee {id: $id})
            SET p.display_name = $display_name,
                p.provider_entity_id = $provider_entity_id,
                p.secret_ref = $secret_ref,
                p.created_at = $created_at,
                p.approved_at = $approved_at,
                p.approved_by = $approved_by,
                p.created_by_client = $created_by_client
            """,
            **merged.model_dump(mode="json"),
        )
        stored = await self.get_payee(merged.id)
        return stored or merged

    async def clear_payee_approval(self, payee_id: str) -> Payee:
        existing = await self.get_payee(payee_id)
        if existing is None:
            raise NotFoundError(f"no such payee: {payee_id}", payee_id=payee_id)
        await self._client.write(
            """
            MATCH (p:Payee {id: $id})
            SET p.approved_at = null,
                p.approved_by = null
            """,
            id=payee_id,
        )
        existing.approved_at = None
        existing.approved_by = None
        stored = await self.get_payee(payee_id)
        return stored or existing
