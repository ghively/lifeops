"""Shopping list persistence against a live NornicDB (BUILD_SPEC section 98).

This suite exists because of a specific piece of debt. Phase 9 packed a list's
items into a single ``items_json`` fact — which worked, and which made the
contents unqueryable. ``test_lists_can_be_found_by_the_items_they_contain`` is
the question that could not previously be answered, so it is the test that
proves the debt is paid rather than moved.

The ordering test matters for the same practical reason: NornicDB returns
relationships in no guaranteed order, and a shopping list whose lines shuffle
between reads is a different list to the person holding it.
"""

from __future__ import annotations

import pytest

from lifeops.domain.shopping import ShoppingItem, ShoppingList, ShoppingListStatus
from lifeops.repositories.nornic.client import NornicClient
from lifeops.repositories.nornic.shopping import NornicShoppingRepository

pytestmark = [pytest.mark.integration, pytest.mark.persistence]

TS = "2026-01-01T00:00:00Z"


@pytest.fixture
async def shopping(nornic_client: NornicClient, test_label: str):
    repo = NornicShoppingRepository(nornic_client)
    created: list[str] = []

    def make(name: str, items: list[ShoppingItem] | None = None) -> ShoppingList:
        list_id = f"shoppinglist_{test_label}_{name}"
        created.append(list_id)
        return ShoppingList(
            id=list_id,
            title=f"{name} {test_label}",
            items=items or [],
            created_at=TS,
            updated_at=TS,
        )

    try:
        yield repo, make
    finally:
        for list_id in created:
            await nornic_client.write(
                "MATCH (s:ShoppingList {id: $id}) "
                "OPTIONAL MATCH (s)-[:CONTAINS]->(i:ShoppingItem) "
                "DETACH DELETE s, i",
                id=list_id,
            )


class TestItemsAreRealNodes:
    async def test_items_round_trip_with_all_their_fields(self, shopping) -> None:
        repo, make = shopping
        items = [
            ShoppingItem(name="Milk", quantity="2", notes="semi-skimmed"),
            ShoppingItem(name="Bread", substitution_allowed=False),
        ]
        await repo.upsert(make("weekly", items))

        stored = await repo.get(make("weekly").id)
        assert stored is not None
        assert [i.name for i in stored.items] == ["Milk", "Bread"]
        assert stored.items[0].quantity == "2"
        assert stored.items[0].notes == "semi-skimmed"
        assert stored.items[1].substitution_allowed is False

    async def test_order_survives(self, shopping) -> None:
        """Relationships come back in no guaranteed order; a list whose lines
        shuffle is a different list to the person holding it."""
        repo, make = shopping
        names = [f"Item {n:02d}" for n in range(12)]
        await repo.upsert(make("ordered", [ShoppingItem(name=n) for n in names]))

        stored = await repo.get(make("ordered").id)
        assert stored is not None
        assert [i.name for i in stored.items] == names

    async def test_lists_can_be_found_by_the_items_they_contain(self, shopping) -> None:
        """The question the JSON blob could not answer."""
        repo, make = shopping
        await repo.upsert(make("has_milk", [ShoppingItem(name="Milk")]))
        await repo.upsert(make("no_milk", [ShoppingItem(name="Bread")]))

        found = {s.id for s in await repo.find_lists_containing("milk")}
        assert make("has_milk").id in found
        assert make("no_milk").id not in found

    async def test_upsert_replaces_items_rather_than_accumulating(
        self, shopping
    ) -> None:
        """A diff that mis-identifies a line leaves a phantom item in a cart."""
        repo, make = shopping
        listing = make("revised", [ShoppingItem(name="Milk"), ShoppingItem(name="Eggs")])
        await repo.upsert(listing)

        listing.items = [ShoppingItem(name="Milk")]
        await repo.upsert(listing)

        stored = await repo.get(listing.id)
        assert stored is not None
        assert [i.name for i in stored.items] == ["Milk"]

    async def test_an_empty_list_round_trips(self, shopping) -> None:
        repo, make = shopping
        await repo.upsert(make("empty"))
        stored = await repo.get(make("empty").id)
        assert stored is not None
        assert stored.items == []

    async def test_deleting_removes_the_items_too(self, shopping, nornic_client) -> None:
        """Orphaned ShoppingItem nodes would accumulate invisibly."""
        repo, make = shopping
        listing = make("gone", [ShoppingItem(name="Milk")])
        await repo.upsert(listing)

        assert await repo.delete(listing.id) is True
        rows = await nornic_client.read(
            "MATCH (i:ShoppingItem {name: 'Milk'})<-[:CONTAINS]-(s:ShoppingList {id: $id}) "
            "RETURN count(i) AS n",
            id=listing.id,
        )
        assert rows[0]["n"] == 0


class TestListState:
    async def test_status_and_references_survive(self, shopping) -> None:
        repo, make = shopping
        listing = make("checkout", [ShoppingItem(name="Milk")])
        listing.status = ShoppingListStatus.SUBMITTED
        listing.order_reference = "ORDER-123"
        await repo.upsert(listing)

        stored = await repo.get(listing.id)
        assert stored is not None
        assert stored.status is ShoppingListStatus.SUBMITTED
        assert stored.order_reference == "ORDER-123"
