"""NornicPreferenceRepository — temporal preference persistence.

Graph shape:

    (:Person)-[:PREFERS]->(:Preference)
    (:Preference)-[:SUPERSEDES]->(:Preference)

"Current" means ``valid_to IS NULL``. Superseded records stay in the graph so
that the history in BUILD_SPEC section 40 is real data rather than a log line.
"""

from __future__ import annotations

from typing import Any

from lifeops.domain.preferences import Preference, PreferenceSource
from lifeops.repositories.nornic.client import NornicClient

_RETURN = """
    p.id AS id,
    p.subject_id AS subject_id,
    p.key AS key,
    p.value AS value,
    p.source_type AS source_type,
    p.source_id AS source_id,
    p.confidence AS confidence,
    p.importance AS importance,
    p.observed_at AS observed_at,
    p.created_at AS created_at,
    p.valid_from AS valid_from,
    p.valid_to AS valid_to,
    p.supersedes AS supersedes,
    p.created_by_client AS created_by_client,
    p.notes AS notes
"""


def _row_to_preference(row: dict[str, Any]) -> Preference:
    return Preference(
        id=row["id"],
        subject_id=row["subject_id"],
        key=row["key"],
        value=row["value"],
        source_type=PreferenceSource(row.get("source_type") or "user_explicit"),
        source_id=row.get("source_id"),
        confidence=float(row.get("confidence") if row.get("confidence") is not None else 1.0),
        importance=float(row.get("importance") if row.get("importance") is not None else 0.5),
        observed_at=row["observed_at"],
        created_at=row["created_at"],
        valid_from=row["valid_from"],
        valid_to=row.get("valid_to"),
        supersedes=row.get("supersedes"),
        created_by_client=row.get("created_by_client"),
        notes=row.get("notes"),
    )


def _write_params(pref: Preference) -> dict[str, Any]:
    return {
        "id": pref.id,
        "subject_id": pref.subject_id,
        "key": pref.key,
        "value": pref.value,
        "source_type": str(pref.source_type),
        "source_id": pref.source_id,
        "confidence": pref.confidence,
        "importance": pref.importance,
        "observed_at": pref.observed_at,
        "created_at": pref.created_at,
        "valid_from": pref.valid_from,
        "valid_to": pref.valid_to,
        "supersedes": pref.supersedes,
        "created_by_client": pref.created_by_client,
        "notes": pref.notes,
    }


_CREATE = """
    MERGE (p:Preference {id: $id})
    SET p.subject_id = $subject_id,
        p.key = $key,
        p.value = $value,
        p.source_type = $source_type,
        p.source_id = $source_id,
        p.confidence = $confidence,
        p.importance = $importance,
        p.observed_at = $observed_at,
        p.created_at = $created_at,
        p.valid_from = $valid_from,
        p.valid_to = $valid_to,
        p.supersedes = $supersedes,
        p.created_by_client = $created_by_client,
        p.notes = $notes
"""


class NornicPreferenceRepository:
    def __init__(self, client: NornicClient) -> None:
        self._client = client

    async def get(self, preference_id: str) -> Preference | None:
        rows = await self._client.read(
            f"MATCH (p:Preference {{id: $id}}) RETURN {_RETURN}", id=preference_id
        )
        return _row_to_preference(rows[0]) if rows else None

    async def list_current(
        self, subject_id: str, *, key_prefix: str | None = None
    ) -> list[Preference]:
        if key_prefix:
            rows = await self._client.read(
                f"""
                MATCH (p:Preference)
                WHERE p.subject_id = $subject_id
                  AND p.valid_to IS NULL
                  AND p.key STARTS WITH $key_prefix
                RETURN {_RETURN}
                ORDER BY p.key ASC
                """,
                subject_id=subject_id,
                key_prefix=key_prefix,
            )
        else:
            rows = await self._client.read(
                f"""
                MATCH (p:Preference)
                WHERE p.subject_id = $subject_id AND p.valid_to IS NULL
                RETURN {_RETURN}
                ORDER BY p.key ASC
                """,
                subject_id=subject_id,
            )
        return [_row_to_preference(r) for r in rows]

    async def get_current_by_key(self, subject_id: str, key: str) -> Preference | None:
        rows = await self._client.read(
            f"""
            MATCH (p:Preference)
            WHERE p.subject_id = $subject_id AND p.key = $key AND p.valid_to IS NULL
            RETURN {_RETURN}
            ORDER BY p.valid_from DESC
            LIMIT 1
            """,
            subject_id=subject_id,
            key=key,
        )
        return _row_to_preference(rows[0]) if rows else None

    async def list_history(self, subject_id: str, key: str) -> list[Preference]:
        rows = await self._client.read(
            f"""
            MATCH (p:Preference)
            WHERE p.subject_id = $subject_id AND p.key = $key
            RETURN {_RETURN}
            ORDER BY p.valid_from DESC
            """,
            subject_id=subject_id,
            key=key,
        )
        return [_row_to_preference(r) for r in rows]

    async def save_superseding(
        self, preference: Preference, *, supersedes: Preference | None
    ) -> Preference:
        """Close the old window and open the new one atomically.

        Both writes share one transaction. Committing only the first would
        leave the subject with no current value for the key; committing only
        the second would leave two.
        """
        statements: list[tuple[str, dict[str, Any]]] = []

        if supersedes is not None:
            statements.append(
                (
                    "MATCH (old:Preference {id: $old_id}) SET old.valid_to = $valid_to",
                    {"old_id": supersedes.id, "valid_to": preference.valid_from},
                )
            )

        statements.append((_CREATE, _write_params(preference)))

        # Attach to the subject so the World graph can traverse Person -> Preference
        # without a property scan.
        statements.append(
            (
                """
                MATCH (p:Preference {id: $pref_id})
                MATCH (subject:Person {id: $subject_id})
                MERGE (subject)-[:PREFERS]->(p)
                """,
                {"pref_id": preference.id, "subject_id": preference.subject_id},
            )
        )

        if supersedes is not None:
            statements.append(
                (
                    """
                    MATCH (new:Preference {id: $new_id})
                    MATCH (old:Preference {id: $old_id})
                    MERGE (new)-[:SUPERSEDES]->(old)
                    """,
                    {"new_id": preference.id, "old_id": supersedes.id},
                )
            )

        await self._client.write_many(statements)
        stored = await self.get(preference.id)
        return stored or preference

    async def invalidate(self, preference_id: str, *, at: str) -> Preference | None:
        await self._client.write(
            "MATCH (p:Preference {id: $id}) WHERE p.valid_to IS NULL "
            "SET p.valid_to = $at",
            id=preference_id,
            at=at,
        )
        return await self.get(preference_id)
