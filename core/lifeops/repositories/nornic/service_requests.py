"""Service requests in NornicDB (BUILD_SPEC section 97).

    (:ServiceRequest {id, subject, status, availability, diagnostic_fee, ...})

``availability`` is a real list property. Phase 8 joined it with ``;`` into a
single fact, on the stated premise that "NornicDB property values cannot be
lists" — which is not true: ``Person.aliases``, ``Memory.entity_ids``, and
``Task.related_entity_ids`` are all stored as native string arrays and have
been since Phase 0. The join round-tripped, but it made the slots unqueryable
and would have lost data the first time a slot contained a semicolon.

``coalesce`` appears in no SET clause here; on this database it persists its
own expression text when the parameter is null (see CLAUDE.md).
"""

from __future__ import annotations

from typing import Any

from lifeops.domain.service_request import ServiceRequest, ServiceRequestStatus
from lifeops.repositories.nornic.client import NornicClient

_RETURN = """
    r.id AS id,
    r.subject AS subject,
    r.status AS status,
    r.task_id AS task_id,
    r.asset_entity_id AS asset_entity_id,
    r.provider_entity_id AS provider_entity_id,
    r.availability AS availability,
    r.diagnostic_fee AS diagnostic_fee,
    r.waiting_item_id AS waiting_item_id,
    r.contact_action_id AS contact_action_id,
    r.booking_action_id AS booking_action_id,
    r.appointment_id AS appointment_id,
    r.notes AS notes,
    r.created_at AS created_at,
    r.updated_at AS updated_at,
    r.created_by_client AS created_by_client
"""


def _row_to_request(row: dict[str, Any]) -> ServiceRequest:
    return ServiceRequest(
        id=row["id"],
        subject=row["subject"],
        status=ServiceRequestStatus(row["status"]),
        task_id=row.get("task_id"),
        asset_entity_id=row.get("asset_entity_id"),
        provider_entity_id=row.get("provider_entity_id"),
        availability=list(row.get("availability") or []),
        diagnostic_fee=row.get("diagnostic_fee"),
        waiting_item_id=row.get("waiting_item_id"),
        contact_action_id=row.get("contact_action_id"),
        booking_action_id=row.get("booking_action_id"),
        appointment_id=row.get("appointment_id"),
        notes=row.get("notes") or "",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by_client=row.get("created_by_client"),
    )


class NornicServiceRequestRepository:
    def __init__(self, client: NornicClient) -> None:
        self._client = client

    async def get(self, request_id: str) -> ServiceRequest | None:
        rows = await self._client.read(
            f"MATCH (r:ServiceRequest {{id: $id}}) RETURN {_RETURN}", id=request_id
        )
        return _row_to_request(rows[0]) if rows else None

    async def list_all(self, *, limit: int = 100) -> list[ServiceRequest]:
        rows = await self._client.read(
            f"MATCH (r:ServiceRequest) RETURN {_RETURN} "
            "ORDER BY r.created_at DESC, r.id DESC LIMIT $limit",
            limit=limit,
        )
        return [_row_to_request(r) for r in rows]

    async def list_for_provider(self, provider_entity_id: str) -> list[ServiceRequest]:
        rows = await self._client.read(
            f"MATCH (r:ServiceRequest {{provider_entity_id: $provider}}) RETURN {_RETURN} "
            "ORDER BY r.created_at DESC, r.id DESC",
            provider=provider_entity_id,
        )
        return [_row_to_request(r) for r in rows]

    async def upsert(self, request: ServiceRequest) -> ServiceRequest:
        await self._client.write(
            """
            MERGE (r:ServiceRequest {id: $id})
            SET r.subject = $subject,
                r.status = $status,
                r.task_id = $task_id,
                r.asset_entity_id = $asset_entity_id,
                r.provider_entity_id = $provider_entity_id,
                r.availability = $availability,
                r.diagnostic_fee = $diagnostic_fee,
                r.waiting_item_id = $waiting_item_id,
                r.contact_action_id = $contact_action_id,
                r.booking_action_id = $booking_action_id,
                r.appointment_id = $appointment_id,
                r.notes = $notes,
                r.created_at = $created_at,
                r.updated_at = $updated_at,
                r.created_by_client = $created_by_client
            """,
            id=request.id,
            subject=request.subject,
            status=str(request.status),
            task_id=request.task_id,
            asset_entity_id=request.asset_entity_id,
            provider_entity_id=request.provider_entity_id,
            availability=list(request.availability),
            diagnostic_fee=request.diagnostic_fee,
            waiting_item_id=request.waiting_item_id,
            contact_action_id=request.contact_action_id,
            booking_action_id=request.booking_action_id,
            appointment_id=request.appointment_id,
            notes=request.notes,
            created_at=request.created_at,
            updated_at=request.updated_at,
            created_by_client=request.created_by_client,
        )
        stored = await self.get(request.id)
        return stored or request
