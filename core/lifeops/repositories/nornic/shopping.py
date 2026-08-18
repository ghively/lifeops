"""Shopping lists in NornicDB (BUILD_SPEC section 98).

Items are real nodes, not a JSON string:

    (:ShoppingList {id, title, status, cart_reference, ...})
    (:ShoppingList)-[:CONTAINS]->(:ShoppingItem {name, quantity, ...})

Phase 9 originally projected a list into the world graph with its items packed
into a single ``items_json`` fact. That worked and was tested, but it made the
contents unqueryable — "which lists contain milk" had no answer — and it put
an unbounded blob inside a facts bag whose whole purpose is to stay small.

Items get a position rather than relying on insertion order: NornicDB returns
relationships in no guaranteed order, and a shopping list whose lines shuffle
between reads is a different list to the person holding it.

``coalesce`` appears in no SET clause here; on this database it persists its
own expression text when the parameter is null (see CLAUDE.md).
"""

from __future__ import annotations

from typing import Any

from lifeops.domain.shopping import ShoppingItem, ShoppingList, ShoppingListStatus
from lifeops.repositories.nornic.client import NornicClient

_LIST_RETURN = """
    s.id AS id,
    s.title AS title,
    s.store AS store,
    s.task_id AS task_id,
    s.status AS status,
    s.cart_reference AS cart_reference,
    s.order_reference AS order_reference,
    s.cart_action_id AS cart_action_id,
    s.checkout_action_id AS checkout_action_id,
    s.total_estimate AS total_estimate,
    s.created_at AS created_at,
    s.updated_at AS updated_at,
    s.created_by_client AS created_by_client
"""

_ITEM_RETURN = """
    i.position AS position,
    i.name AS name,
    i.quantity AS quantity,
    i.notes AS notes,
    i.substitution_allowed AS substitution_allowed,
    i.substituted_with AS substituted_with,
    i.substitution_reason AS substitution_reason,
    i.estimated_price AS estimated_price
"""


def _row_to_item(row: dict[str, Any]) -> ShoppingItem:
    return ShoppingItem(
        name=row["name"],
        quantity=row.get("quantity") or "1",
        notes=row.get("notes") or "",
        substitution_allowed=bool(row.get("substitution_allowed", True)),
        substituted_with=row.get("substituted_with"),
        substitution_reason=row.get("substitution_reason"),
        estimated_price=row.get("estimated_price"),
    )


def _row_to_list(row: dict[str, Any], items: list[ShoppingItem]) -> ShoppingList:
    return ShoppingList(
        id=row["id"],
        title=row["title"],
        store=row.get("store") or "",
        task_id=row.get("task_id"),
        items=items,
        status=ShoppingListStatus(row["status"]),
        cart_reference=row.get("cart_reference"),
        order_reference=row.get("order_reference"),
        cart_action_id=row.get("cart_action_id"),
        checkout_action_id=row.get("checkout_action_id"),
        total_estimate=row.get("total_estimate"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by_client=row.get("created_by_client"),
    )


class NornicShoppingRepository:
    def __init__(self, client: NornicClient) -> None:
        self._client = client

    async def _items_for(self, list_id: str) -> list[ShoppingItem]:
        rows = await self._client.read(
            f"""
            MATCH (s:ShoppingList {{id: $id}})-[:CONTAINS]->(i:ShoppingItem)
            RETURN {_ITEM_RETURN}
            ORDER BY i.position ASC
            """,
            id=list_id,
        )
        return [_row_to_item(r) for r in rows]

    async def get(self, list_id: str) -> ShoppingList | None:
        rows = await self._client.read(
            f"MATCH (s:ShoppingList {{id: $id}}) RETURN {_LIST_RETURN}", id=list_id
        )
        if not rows:
            return None
        return _row_to_list(rows[0], await self._items_for(list_id))

    async def list_all(self, *, limit: int = 100) -> list[ShoppingList]:
        rows = await self._client.read(
            f"MATCH (s:ShoppingList) RETURN {_LIST_RETURN} "
            "ORDER BY s.created_at DESC, s.id DESC LIMIT $limit",
            limit=limit,
        )
        return [_row_to_list(r, await self._items_for(r["id"])) for r in rows]

    async def find_lists_containing(self, item_name: str) -> list[ShoppingList]:
        """Every list carrying an item by name.

        The question the JSON blob could not answer, and the reason items are
        nodes.
        """
        # Two steps rather than one: matching ids first and re-reading each
        # list keeps the projection off a DISTINCT, which does not reliably
        # dedupe aliased columns on this database.
        rows = await self._client.read(
            """
            MATCH (s:ShoppingList)-[:CONTAINS]->(i:ShoppingItem)
            WHERE toLower(i.name) CONTAINS $needle
            RETURN s.id AS id
            """,
            # Lowered in Python: toLower() applied to a *parameter* does not
            # evaluate on NornicDB, so the comparison silently never matched.
            # tasks.py and people.py already do it this way.
            needle=item_name.strip().lower(),
        )
        found: list[ShoppingList] = []
        for list_id in dict.fromkeys(row["id"] for row in rows):
            listing = await self.get(list_id)
            if listing is not None:
                found.append(listing)
        found.sort(key=lambda s: (s.created_at, s.id), reverse=True)
        return found

    async def upsert(self, shopping_list: ShoppingList) -> ShoppingList:
        """Write the list and replace its items.

        Items are deleted and rewritten rather than diffed: a list is small,
        and a diff that mis-identifies a line leaves a phantom item in
        someone's cart. One transaction, so a partial rewrite cannot survive.
        """
        statements: list[tuple[str, dict[str, Any]]] = [
            (
                """
                MERGE (s:ShoppingList {id: $id})
                SET s.title = $title,
                    s.store = $store,
                    s.task_id = $task_id,
                    s.status = $status,
                    s.cart_reference = $cart_reference,
                    s.order_reference = $order_reference,
                    s.cart_action_id = $cart_action_id,
                    s.checkout_action_id = $checkout_action_id,
                    s.total_estimate = $total_estimate,
                    s.created_at = $created_at,
                    s.updated_at = $updated_at,
                    s.created_by_client = $created_by_client
                """,
                {
                    "id": shopping_list.id,
                    "title": shopping_list.title,
                    "store": shopping_list.store,
                    "task_id": shopping_list.task_id,
                    "status": str(shopping_list.status),
                    "cart_reference": shopping_list.cart_reference,
                    "order_reference": shopping_list.order_reference,
                    "cart_action_id": shopping_list.cart_action_id,
                    "checkout_action_id": shopping_list.checkout_action_id,
                    "total_estimate": shopping_list.total_estimate,
                    "created_at": shopping_list.created_at,
                    "updated_at": shopping_list.updated_at,
                    "created_by_client": shopping_list.created_by_client,
                },
            ),
            (
                "MATCH (s:ShoppingList {id: $id})-[:CONTAINS]->(i:ShoppingItem) "
                "DETACH DELETE i",
                {"id": shopping_list.id},
            ),
        ]
        for position, item in enumerate(shopping_list.items):
            statements.append(
                (
                    """
                    MATCH (s:ShoppingList {id: $id})
                    CREATE (s)-[:CONTAINS]->(i:ShoppingItem {
                        position: $position,
                        name: $name,
                        quantity: $quantity,
                        notes: $notes,
                        substitution_allowed: $substitution_allowed,
                        substituted_with: $substituted_with,
                        substitution_reason: $substitution_reason,
                        estimated_price: $estimated_price
                    })
                    """,
                    {"id": shopping_list.id, "position": position, **item.model_dump()},
                )
            )

        await self._client.write_many(statements)
        stored = await self.get(shopping_list.id)
        return stored or shopping_list

    async def delete(self, list_id: str) -> bool:
        rows = await self._client.write(
            """
            MATCH (s:ShoppingList {id: $id})
            OPTIONAL MATCH (s)-[:CONTAINS]->(i:ShoppingItem)
            DETACH DELETE s, i
            RETURN count(s) AS removed
            """,
            id=list_id,
        )
        return bool(rows and rows[0]["removed"])
