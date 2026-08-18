"""Service request persistence against a live NornicDB (BUILD_SPEC section 97).

The reason this suite exists: Phase 8 joined ``availability`` with ``;`` into
one fact, on the stated premise that NornicDB cannot store lists. It can —
``Person.aliases`` and ``Memory.entity_ids`` have been native string arrays
since Phase 0. ``test_a_slot_containing_a_semicolon_survives`` is the case the
join would have silently corrupted, so it is the test that proves the debt is
paid rather than moved.
"""

from __future__ import annotations

import pytest

from lifeops.domain.service_request import ServiceRequest, ServiceRequestStatus
from lifeops.repositories.nornic.client import NornicClient
from lifeops.repositories.nornic.service_requests import NornicServiceRequestRepository

pytestmark = [pytest.mark.integration, pytest.mark.persistence]

TS = "2026-01-01T00:00:00Z"


@pytest.fixture
async def requests(nornic_client: NornicClient, test_label: str):
    repo = NornicServiceRequestRepository(nornic_client)
    created: list[str] = []

    def make(name: str, **overrides) -> ServiceRequest:
        request_id = f"servicerequest_{test_label}_{name}"
        created.append(request_id)
        base = dict(
            id=request_id,
            subject=f"{name} {test_label}",
            created_at=TS,
            updated_at=TS,
        )
        return ServiceRequest(**{**base, **overrides})

    try:
        yield repo, make
    finally:
        for request_id in created:
            await nornic_client.write(
                "MATCH (r:ServiceRequest {id: $id}) DETACH DELETE r", id=request_id
            )


class TestAvailabilityIsARealList:
    async def test_slots_round_trip_in_order(self, requests) -> None:
        repo, make = requests
        slots = [
            "2026-02-02T13:00:00Z",
            "2026-02-03T09:00:00Z",
            "2026-02-04T15:00:00Z",
        ]
        request = make("slots", availability=slots)
        await repo.upsert(request)

        stored = await repo.get(request.id)
        assert stored is not None
        assert stored.availability == slots

    async def test_a_slot_containing_a_semicolon_survives(self, requests) -> None:
        """The case a ';'-joined string would have silently split in two."""
        repo, make = requests
        slots = ["Thursday 1-3pm; ask for Dave", "Friday 9am"]
        request = make("semicolon", availability=slots)
        await repo.upsert(request)

        stored = await repo.get(request.id)
        assert stored is not None
        assert stored.availability == slots
        assert len(stored.availability) == 2

    async def test_an_empty_availability_round_trips(self, requests) -> None:
        repo, make = requests
        request = make("empty")
        await repo.upsert(request)

        stored = await repo.get(request.id)
        assert stored is not None
        assert stored.availability == []

    async def test_upsert_replaces_rather_than_appends(self, requests) -> None:
        repo, make = requests
        request = make("revised", availability=["a", "b"])
        await repo.upsert(request)

        request.availability = ["c"]
        await repo.upsert(request)

        stored = await repo.get(request.id)
        assert stored is not None
        assert stored.availability == ["c"]


class TestProviderHistory:
    async def test_requests_are_found_by_provider(self, requests) -> None:
        """Section 101 step 3 asks for provider history; this is the query."""
        repo, make = requests
        mine = make("mine", provider_entity_id="provider_abc_electric")
        other = make("other", provider_entity_id="provider_zephyr")
        await repo.upsert(mine)
        await repo.upsert(other)

        found = {r.id for r in await repo.list_for_provider("provider_abc_electric")}
        assert mine.id in found
        assert other.id not in found

    async def test_status_and_fee_survive(self, requests) -> None:
        repo, make = requests
        request = make(
            "quoted",
            status=ServiceRequestStatus.QUOTE_COLLECTED,
            diagnostic_fee="89.00",
        )
        await repo.upsert(request)

        stored = await repo.get(request.id)
        assert stored is not None
        assert stored.status is ServiceRequestStatus.QUOTE_COLLECTED
        assert stored.diagnostic_fee == "89.00"
