"""NornicPersonRepository — Person persistence in NornicDB."""

from __future__ import annotations

from typing import Any

from lifeops.domain.people import Person
from lifeops.repositories.nornic.client import NornicClient

# Listed explicitly rather than SET p += $props so that a future domain field
# cannot silently start writing itself to the database unreviewed.
_RETURN = """
    p.id AS id,
    p.display_name AS display_name,
    p.is_primary AS is_primary,
    p.aliases AS aliases,
    p.timezone AS timezone,
    p.created_at AS created_at,
    p.updated_at AS updated_at
"""


def _row_to_person(row: dict[str, Any]) -> Person:
    return Person(
        id=row["id"],
        display_name=row["display_name"],
        is_primary=bool(row.get("is_primary")),
        aliases=list(row.get("aliases") or []),
        timezone=row.get("timezone"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class NornicPersonRepository:
    def __init__(self, client: NornicClient) -> None:
        self._client = client

    async def get(self, person_id: str) -> Person | None:
        rows = await self._client.read(
            f"MATCH (p:Person {{id: $id}}) RETURN {_RETURN}", id=person_id
        )
        return _row_to_person(rows[0]) if rows else None

    async def get_primary(self) -> Person | None:
        rows = await self._client.read(
            f"MATCH (p:Person) WHERE p.is_primary = true RETURN {_RETURN} "
            "ORDER BY p.created_at ASC LIMIT 1"
        )
        return _row_to_person(rows[0]) if rows else None

    async def find_by_name(self, name: str) -> list[Person]:
        """Case-insensitive match on display name or alias.

        Substring rather than exact: callers are agents relaying what a human
        said ("Gene", "gene hively"), not systems quoting a key.
        """
        needle = name.strip().lower()
        rows = await self._client.read(
            f"""
            MATCH (p:Person)
            WHERE toLower(p.display_name) CONTAINS $needle
               OR any(a IN coalesce(p.aliases, []) WHERE toLower(a) CONTAINS $needle)
            RETURN {_RETURN}
            ORDER BY p.display_name ASC
            LIMIT 25
            """,
            needle=needle,
        )
        return [_row_to_person(r) for r in rows]

    async def list_all(self, *, limit: int = 100) -> list[Person]:
        rows = await self._client.read(
            f"MATCH (p:Person) RETURN {_RETURN} ORDER BY p.display_name ASC LIMIT $limit",
            limit=limit,
        )
        return [_row_to_person(r) for r in rows]

    async def upsert(self, person: Person) -> Person:
        statements: list[tuple[str, dict[str, Any]]] = []

        # Exactly one primary person. Demoting others in the same transaction
        # keeps "who does the assistant act for?" from ever being ambiguous.
        if person.is_primary:
            statements.append(
                (
                    "MATCH (other:Person) WHERE other.is_primary = true "
                    "AND other.id <> $id SET other.is_primary = false",
                    {"id": person.id},
                )
            )

        statements.append(
            (
                """
                MERGE (p:Person {id: $id})
                ON CREATE SET p.created_at = $created_at
                SET p.display_name = $display_name,
                    p.is_primary = $is_primary,
                    p.aliases = $aliases,
                    p.timezone = $timezone,
                    p.updated_at = $updated_at
                """,
                {
                    "id": person.id,
                    "display_name": person.display_name,
                    "is_primary": person.is_primary,
                    "aliases": person.aliases,
                    "timezone": person.timezone,
                    "created_at": person.created_at,
                    "updated_at": person.updated_at,
                },
            )
        )

        await self._client.write_many(statements)
        stored = await self.get(person.id)
        return stored or person
