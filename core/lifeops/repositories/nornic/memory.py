"""NornicMemoryRepository — temporal memory persistence (BUILD_SPEC 42–47).

Graph shape:

    (:Person)-[:REMEMBERS]->(:Memory)
    (:Memory)-[:SUPERSEDES]->(:Memory)

"Current" means ``valid_to IS NULL``. Corrected and invalidated memories stay
in the graph so provenance (section 45) is real data, not a log line.

Recall uses NornicDB's Lucene-backed fulltext index (BM25 scoring) over
``Memory.content`` — the best ranking available without an embedding provider,
which this deployment deliberately leaves off. If the index is absent (a
backend without fulltext support) or a query is rejected, the repository falls
back to a case-insensitive all-terms substring match. An embedding-backed
vector path can later be added alongside the fulltext branch behind a setting,
without touching callers.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from lifeops.domain.memory import MemoryRecord, MemorySource, MemoryType
from lifeops.errors import ConcurrentWriteError, RepositoryError
from lifeops.repositories.nornic.client import NornicClient


def _score(value: Any, *, default: float) -> float:
    """A stored 0..1 score, defaulting when the property is absent."""
    return default if value is None else float(value)

logger = logging.getLogger(__name__)

#: Boot-time schema (client.py) creates this index; the name is a module
#: constant rather than a parameter because Cypher procedure arguments are
#: part of the query plan, and because it is never user input.
_FULLTEXT_INDEX = "lifeops_memory_content"

_RETURN = """
    m.id AS id,
    m.subject_id AS subject_id,
    m.type AS type,
    m.content AS content,
    m.source_type AS source_type,
    m.source_id AS source_id,
    m.confidence AS confidence,
    m.importance AS importance,
    m.observed_at AS observed_at,
    m.created_at AS created_at,
    m.valid_from AS valid_from,
    m.valid_to AS valid_to,
    m.supersedes AS supersedes,
    m.entity_ids AS entity_ids,
    m.created_by_client AS created_by_client,
    m.invalidation_reason AS invalidation_reason
"""

_CREATE = """
    MERGE (m:Memory {id: $id})
    SET m.subject_id = $subject_id,
        m.type = $type,
        m.content = $content,
        m.source_type = $source_type,
        m.source_id = $source_id,
        m.confidence = $confidence,
        m.importance = $importance,
        m.observed_at = $observed_at,
        m.created_at = $created_at,
        m.valid_from = $valid_from,
        m.valid_to = $valid_to,
        m.supersedes = $supersedes,
        m.entity_ids = $entity_ids,
        m.created_by_client = $created_by_client,
        m.invalidation_reason = $invalidation_reason
"""

#: Lucene query syntax treats these as operators; user text is never meant to
#: be a query language, so they are stripped rather than escaped.
_FULLTEXT_SPECIALS = re.compile(r"[+\-=&|><!(){}[\]^\"~*?:\\/]")

#: Terms beyond this in the substring fallback are ignored; the fulltext path
#: handles arbitrary-length queries, the fallback only needs to be decent.
_FALLBACK_MAX_TERMS = 8


def _to_fulltext_query(query: str) -> str:
    return " ".join(_FULLTEXT_SPECIALS.sub(" ", query).split())


def _row_to_memory(row: dict[str, Any]) -> MemoryRecord:
    return MemoryRecord(
        id=row["id"],
        subject_id=row["subject_id"],
        type=MemoryType(row.get("type") or "semantic"),
        content=row["content"],
        source_type=MemorySource(row.get("source_type") or "conversation"),
        source_id=row.get("source_id"),
        confidence=_score(row.get("confidence"), default=1.0),
        importance=_score(row.get("importance"), default=0.5),
        observed_at=row["observed_at"],
        created_at=row["created_at"],
        valid_from=row["valid_from"],
        valid_to=row.get("valid_to"),
        supersedes=row.get("supersedes"),
        entity_ids=list(row.get("entity_ids") or []),
        created_by_client=row.get("created_by_client"),
        invalidation_reason=row.get("invalidation_reason"),
    )


def _write_params(memory: MemoryRecord) -> dict[str, Any]:
    return {
        "id": memory.id,
        "subject_id": memory.subject_id,
        "type": str(memory.type),
        "content": memory.content,
        "source_type": str(memory.source_type),
        "source_id": memory.source_id,
        "confidence": memory.confidence,
        "importance": memory.importance,
        "observed_at": memory.observed_at,
        "created_at": memory.created_at,
        "valid_from": memory.valid_from,
        "valid_to": memory.valid_to,
        "supersedes": memory.supersedes,
        "entity_ids": list(memory.entity_ids),
        "created_by_client": memory.created_by_client,
        "invalidation_reason": memory.invalidation_reason,
    }


def _filters() -> str:
    """The current-only/scope predicates shared by every read query."""
    return """
        m.valid_to IS NULL
        AND ($subject_id IS NULL OR m.subject_id = $subject_id)
        AND ($memory_types IS NULL OR m.type IN $memory_types)
    """


class NornicMemoryRepository:
    def __init__(self, client: NornicClient) -> None:
        self._client = client

    async def get(self, memory_id: str) -> MemoryRecord | None:
        rows = await self._client.read(
            f"MATCH (m:Memory {{id: $id}}) RETURN {_RETURN}", id=memory_id
        )
        return _row_to_memory(rows[0]) if rows else None

    async def list_current(
        self,
        subject_id: str | None = None,
        *,
        memory_types: list[MemoryType] | None = None,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        rows = await self._client.read(
            f"""
            MATCH (m:Memory)
            WHERE {_filters()}
            RETURN {_RETURN}
            ORDER BY m.importance DESC, m.observed_at DESC, m.id DESC
            LIMIT $limit
            """,
            subject_id=subject_id,
            memory_types=[str(t) for t in memory_types] if memory_types else None,
            limit=limit,
        )
        return [_row_to_memory(r) for r in rows]

    async def list_invalidated(
        self,
        subject_id: str | None = None,
        *,
        memory_types: list[MemoryType] | None = None,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        """The Memory screen's "invalidated/superseded history" view
        (section 17) — closed records only, newest-closed first."""
        rows = await self._client.read(
            f"""
            MATCH (m:Memory)
            WHERE m.valid_to IS NOT NULL
              AND ($subject_id IS NULL OR m.subject_id = $subject_id)
              AND ($memory_types IS NULL OR m.type IN $memory_types)
            RETURN {_RETURN}
            ORDER BY m.valid_to DESC, m.id DESC
            LIMIT $limit
            """,
            subject_id=subject_id,
            memory_types=[str(t) for t in memory_types] if memory_types else None,
            limit=limit,
        )
        return [_row_to_memory(r) for r in rows]

    async def search(
        self,
        query: str,
        *,
        subject_id: str | None = None,
        memory_types: list[MemoryType] | None = None,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        """Ranked recall over current memories.

        BM25 fulltext first; on any repository-level failure (index absent,
        query rejected) falls back to a substring match so recall degrades
        instead of breaking.
        """
        fulltext_query = _to_fulltext_query(query)
        if fulltext_query:
            try:
                return await self._fulltext_search(
                    fulltext_query,
                    subject_id=subject_id,
                    memory_types=memory_types,
                    limit=limit,
                )
            except RepositoryError:
                logger.warning(
                    "fulltext memory search unavailable; falling back to substring",
                    exc_info=True,
                )
        return await self._substring_search(
            query, subject_id=subject_id, memory_types=memory_types, limit=limit
        )

    async def _fulltext_search(
        self,
        fulltext_query: str,
        *,
        subject_id: str | None,
        memory_types: list[MemoryType] | None,
        limit: int,
    ) -> list[MemoryRecord]:
        rows = await self._client.read(
            f"""
            CALL db.index.fulltext.queryNodes('{_FULLTEXT_INDEX}', $fts_query)
            YIELD node, score
            WITH node AS m, score
            WHERE {_filters()}
            RETURN {_RETURN}, score
            ORDER BY score DESC
            LIMIT $limit
            """,
            fts_query=fulltext_query,
            subject_id=subject_id,
            memory_types=[str(t) for t in memory_types] if memory_types else None,
            limit=limit,
        )
        return [_row_to_memory(r) for r in rows]

    async def _substring_search(
        self,
        query: str,
        *,
        subject_id: str | None,
        memory_types: list[MemoryType] | None,
        limit: int,
    ) -> list[MemoryRecord]:
        # All query terms must appear in the content. Terms are bound as
        # individual parameters — never interpolated — because list predicates
        # like ALL(term IN $terms ...) are not portable across backends
        # (NornicDB silently matches nothing), and interpolating user text
        # into Cypher is not an option. Ranking is importance then recency.
        terms = query.strip().lower().split()[:_FALLBACK_MAX_TERMS]
        if not terms:
            return []
        term_clause = " AND ".join(
            f"toLower(m.content) CONTAINS $term_{i}" for i in range(len(terms))
        )
        rows = await self._client.read(
            f"""
            MATCH (m:Memory)
            WHERE {_filters()}
              AND {term_clause}
            RETURN {_RETURN}
            ORDER BY m.importance DESC, m.observed_at DESC, m.id DESC
            LIMIT $limit
            """,
            subject_id=subject_id,
            memory_types=[str(t) for t in memory_types] if memory_types else None,
            limit=limit,
            **{f"term_{i}": term for i, term in enumerate(terms)},
        )
        return [_row_to_memory(r) for r in rows]

    async def list_history(self, memory_id: str) -> list[MemoryRecord]:
        """The whole SUPERSEDES chain a record belongs to, newest first.

        Implemented as single-hop walks rather than a variable-length path
        query: chains are linear and short, and directed single-hop matches
        are the most portable Cypher there is.
        """
        start = await self.get(memory_id)
        if start is None:
            return []

        chain: dict[str, MemoryRecord] = {start.id: start}

        # Walk to older versions via the supersedes pointer.
        current = start
        while current.supersedes is not None and current.supersedes not in chain:
            older = await self.get(current.supersedes)
            if older is None:
                break
            chain[older.id] = older
            current = older

        # Walk to newer versions via the reverse lookup.
        current = start
        while True:
            rows = await self._client.read(
                f"MATCH (m:Memory) WHERE m.supersedes = $id RETURN {_RETURN}",
                id=current.id,
            )
            newer = [_row_to_memory(r) for r in rows if r["id"] not in chain]
            if not newer:
                break
            chain[newer[0].id] = newer[0]
            current = newer[0]

        return sorted(chain.values(), key=lambda m: (m.valid_from, m.id), reverse=True)

    async def get_current_duplicate(
        self, subject_id: str, memory_type: MemoryType, content: str
    ) -> MemoryRecord | None:
        rows = await self._client.read(
            f"""
            MATCH (m:Memory)
            WHERE m.subject_id = $subject_id
              AND m.type = $type
              AND m.content = $content
              AND m.valid_to IS NULL
            RETURN {_RETURN}
            ORDER BY m.valid_from DESC
            LIMIT 1
            """,
            subject_id=subject_id,
            type=str(memory_type),
            content=content,
        )
        return _row_to_memory(rows[0]) if rows else None

    async def list_for_entity(
        self, entity_id: str, *, current_only: bool = True, limit: int = 50
    ) -> list[MemoryRecord]:
        current_filter = "AND m.valid_to IS NULL" if current_only else ""
        rows = await self._client.read(
            f"""
            MATCH (m:Memory)
            WHERE $entity_id IN coalesce(m.entity_ids, [])
            {current_filter}
            RETURN {_RETURN}
            ORDER BY m.created_at DESC, m.id DESC
            LIMIT $limit
            """,
            entity_id=entity_id,
            limit=limit,
        )
        return [_row_to_memory(r) for r in rows]

    async def save_superseding(
        self, memory: MemoryRecord, *, supersedes: MemoryRecord | None
    ) -> MemoryRecord:
        """Close the old window and open the new one in one transaction.

        Same invariant as preferences: committing only one half would leave
        either two current versions of a memory or none.
        """
        statements: list[tuple[str, dict[str, Any]]] = []

        if supersedes is not None:
            statements.append(
                (
                    "MATCH (old:Memory {id: $old_id}) SET old.valid_to = $valid_to",
                    {"old_id": supersedes.id, "valid_to": memory.valid_from},
                )
            )

        statements.append((_CREATE, _write_params(memory)))

        # Attach to the subject so the World graph can traverse
        # Person -> Memory without a property scan.
        statements.append(
            (
                """
                MATCH (m:Memory {id: $memory_id})
                MATCH (subject:Person {id: $subject_id})
                MERGE (subject)-[:REMEMBERS]->(m)
                """,
                {"memory_id": memory.id, "subject_id": memory.subject_id},
            )
        )

        if supersedes is not None:
            statements.append(
                (
                    """
                    MATCH (new:Memory {id: $new_id})
                    MATCH (old:Memory {id: $old_id})
                    MERGE (new)-[:SUPERSEDES]->(old)
                    """,
                    {"new_id": memory.id, "old_id": supersedes.id},
                )
            )

        await self._client.write_many(statements)
        stored = await self.get(memory.id)
        return stored or memory

    async def invalidate(
        self, memory_id: str, *, at: str, reason: str | None = None
    ) -> MemoryRecord | None:
        try:
            rows = await self._client.write(
                f"MATCH (m:Memory {{id: $id}}) WHERE m.valid_to IS NULL "
                f"SET m.valid_to = $at, m.invalidation_reason = $reason "
                f"RETURN {_RETURN}",
                id=memory_id,
                at=at,
                reason=reason,
            )
        except ConcurrentWriteError:
            # Another transaction closed this window first — the same None as
            # "there was nothing open to invalidate".
            return None
        if rows:
            # The write's own row, not a follow-up read — which can be stale
            # right after an auto-commit write (CLAUDE.md) and report the
            # record still valid after a successful invalidation.
            return _row_to_memory(rows[0])
        # Nothing matched: already invalidated, or missing. The read answers.
        return await self.get(memory_id)
