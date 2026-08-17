"""NornicWorldRepository — the world graph in NornicDB (BUILD_SPEC 36–39, 92).

Graph shape:

    (:Household {id, display_name, facts_json, created_at, updated_at, ...})
    (:Provider  {...})   (:Asset {...})   (:Person {...})   (Person: Phase 0)
    (:Preference {id, key, value, valid_from, valid_to, ...})  (Phase 0)

    (a)-[:MEMBER_OF]->(b)      (a)-[:OWNS]->(b)
    (a)-[:USES_PROVIDER]->(b)  (a)-[:RELATED_TO]->(b)

Two deliberate storage choices:

  * ``facts`` is stored as a JSON string (``facts_json``). Neo4j-compatible
    property values cannot be maps, so a dict property would fail at write
    time. Keys are sorted before serialisation so identical facts compare equal.

  * Every graph read is built from directed single-hop matches walked in
    Python. Undirected or variable-length patterns return phantom rows on
    NornicDB (verified in Phase 2), so neighbourhood expansion is an explicit
    breadth-first walk of single hops in each direction.
"""

from __future__ import annotations

import json
from typing import Any

from lifeops.domain.world import (
    CREATABLE_ENTITY_TYPES,
    WORLD_RELATIONSHIP_TYPES,
    WorldEdge,
    WorldEntity,
    WorldEntityType,
    WorldRelationship,
    entity_type_for_id,
    is_world_entity_id,
)
from lifeops.repositories.nornic.client import NornicClient

_LABEL_FOR_TYPE: dict[WorldEntityType, str] = {
    WorldEntityType.PERSON: "Person",
    WorldEntityType.HOUSEHOLD: "Household",
    WorldEntityType.PROVIDER: "Provider",
    WorldEntityType.ASSET: "Asset",
    WorldEntityType.PREFERENCE: "Preference",
}

# Labels come from this module's own constant map keyed on the ID prefix —
# never from caller input — so interpolating them into Cypher is safe.

#: The shaped world entities: one display name and a JSON facts bag.
_ENTITY_RETURN = """
    n.id AS id,
    n.display_name AS display_name,
    n.facts_json AS facts_json,
    n.created_at AS created_at,
    n.updated_at AS updated_at,
    n.created_by_client AS created_by_client
"""

#: Preferences are projected, not reshaped. The node belongs to the preference
#: layer — this aliases its columns into the graph's vocabulary so the World
#: screen can draw section 15's ``Gene ─PREFERS→ "After 10 AM"`` without the
#: world repository owning preference storage. ``valid_from`` stands in for
#: ``updated_at``: a preference is never edited, a new version opens instead.
_PREFERENCE_RETURN = """
    n.id AS id,
    n.value AS display_name,
    n.key AS pref_key,
    n.source_type AS pref_source,
    n.confidence AS pref_confidence,
    n.created_at AS created_at,
    n.valid_from AS updated_at,
    n.created_by_client AS created_by_client
"""

#: Only current preferences are world nodes (section 15's current view). A
#: superseded one keeps its PREFERS edge, and graph assembly drops that edge
#: once the node is gone.
_CURRENT_ONLY: dict[WorldEntityType, str] = {
    WorldEntityType.PREFERENCE: "WHERE n.valid_to IS NULL",
}


def _returns_for(entity_type: WorldEntityType) -> str:
    if entity_type is WorldEntityType.PREFERENCE:
        return _PREFERENCE_RETURN
    return _ENTITY_RETURN


def _row_to_entity(row: dict[str, Any]) -> WorldEntity:
    entity_type = entity_type_for_id(row["id"])
    if entity_type is WorldEntityType.PREFERENCE:
        # The key and provenance become facts, so the inspector shows *which*
        # preference this is rather than a bare value.
        facts = {"key": row.get("pref_key") or "", "source": row.get("pref_source") or ""}
        confidence = row.get("pref_confidence")
        if confidence is not None:
            facts["confidence"] = str(confidence)
        facts = {k: v for k, v in facts.items() if v}
    else:
        facts_raw = row.get("facts_json")
        loaded = json.loads(facts_raw) if facts_raw else {}
        facts = {str(k): str(v) for k, v in loaded.items()}

    return WorldEntity(
        id=row["id"],
        entity_type=entity_type,
        display_name=row.get("display_name") or row["id"],
        facts=facts,
        created_at=row.get("created_at") or "",
        updated_at=row.get("updated_at") or "",
        created_by_client=row.get("created_by_client"),
    )


def _row_to_edge(row: dict[str, Any]) -> WorldEdge:
    return WorldEdge(
        source=row["source"],
        target=row["target"],
        type=WorldRelationship(row["type"]),
    )


def _type_params(rel_types: list[WorldRelationship] | None) -> list[str]:
    chosen = rel_types if rel_types is not None else list(WORLD_RELATIONSHIP_TYPES)
    return [str(r) for r in chosen]


class NornicWorldRepository:
    def __init__(self, client: NornicClient) -> None:
        self._client = client

    async def get(self, entity_id: str) -> WorldEntity | None:
        entity_type = entity_type_for_id(entity_id)
        # The current-only filter applies here too: the World screen shows the
        # current world, so a superseded preference is not a node you can
        # inspect or link. Its history lives on the Memory screen (section 17).
        rows = await self._client.read(
            f"MATCH (n:{_LABEL_FOR_TYPE[entity_type]} {{id: $id}}) "
            f"{_CURRENT_ONLY.get(entity_type, '')} "
            f"RETURN {_returns_for(entity_type)}",
            id=entity_id,
        )
        return _row_to_entity(rows[0]) if rows else None

    async def exists(self, entity_id: str) -> bool:
        entity_type = entity_type_for_id(entity_id)
        rows = await self._client.read(
            f"MATCH (n:{_LABEL_FOR_TYPE[entity_type]} {{id: $id}}) "
            f"{_CURRENT_ONLY.get(entity_type, '')} "
            "RETURN count(n) AS found",
            id=entity_id,
        )
        return bool(rows and rows[0]["found"])

    async def create(self, entity: WorldEntity) -> WorldEntity:
        # Only the shaped types are written here. Preferences and persons are
        # owned by their own repositories; the domain refuses them upstream,
        # and this guard keeps a future caller from writing a Preference node
        # with the wrong property shape.
        if entity.entity_type not in CREATABLE_ENTITY_TYPES:
            raise ValueError(
                f"{entity.entity_type} is not created by the world repository"
            )
        label = _LABEL_FOR_TYPE[entity.entity_type]
        await self._client.write(
            f"""
            MERGE (n:{label} {{id: $id}})
            SET n.display_name = $display_name,
                n.facts_json = $facts_json,
                n.created_at = $created_at,
                n.updated_at = $updated_at,
                n.created_by_client = $created_by_client
            """,
            id=entity.id,
            display_name=entity.display_name,
            facts_json=json.dumps(entity.facts, sort_keys=True),
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            created_by_client=entity.created_by_client,
        )
        stored = await self.get(entity.id)
        return stored or entity

    async def list_entities(
        self, *, types: list[WorldEntityType] | None = None, limit: int = 500
    ) -> list[WorldEntity]:
        wanted = types if types is not None else list(WorldEntityType)
        entities: list[WorldEntity] = []
        for entity_type in wanted:
            rows = await self._client.read(
                f"MATCH (n:{_LABEL_FOR_TYPE[entity_type]}) "
                f"{_CURRENT_ONLY.get(entity_type, '')} "
                f"RETURN {_returns_for(entity_type)} "
                "ORDER BY n.id ASC LIMIT $limit",
                limit=limit,
            )
            entities.extend(_row_to_entity(r) for r in rows)
        entities.sort(key=lambda e: e.id)
        return entities[:limit]

    async def list_edges(
        self,
        *,
        rel_types: list[WorldRelationship] | None = None,
        limit: int = 2000,
    ) -> list[WorldEdge]:
        rows = await self._client.read(
            """
            MATCH (a)-[r]->(b)
            WHERE type(r) IN $rel_types
            RETURN a.id AS source, b.id AS target, type(r) AS type
            ORDER BY source, target
            LIMIT $limit
            """,
            rel_types=_type_params(rel_types),
            limit=limit,
        )
        return [_row_to_edge(r) for r in rows]

    async def list_edges_for(
        self, entity_id: str, *, rel_types: list[WorldRelationship] | None = None
    ) -> list[WorldEdge]:
        # Two directed single-hop queries rather than one undirected match:
        # undirected patterns are exactly the NornicDB case that returns
        # phantom rows.
        edges: dict[tuple[str, str, str], WorldEdge] = {}
        for query in (
            """
            MATCH (a {id: $id})-[r]->(b)
            WHERE type(r) IN $rel_types
            RETURN a.id AS source, b.id AS target, type(r) AS type
            """,
            """
            MATCH (a)-[r]->(b {id: $id})
            WHERE type(r) IN $rel_types
            RETURN a.id AS source, b.id AS target, type(r) AS type
            """,
        ):
            rows = await self._client.read(
                query, id=entity_id, rel_types=_type_params(rel_types)
            )
            for row in rows:
                edge = _row_to_edge(row)
                edges[(edge.source, edge.target, str(edge.type))] = edge
        return sorted(edges.values(), key=lambda e: (e.source, e.target, str(e.type)))

    async def neighborhood(
        self,
        entity_id: str,
        *,
        depth: int,
        rel_types: list[WorldRelationship] | None = None,
    ) -> tuple[list[WorldEntity], list[WorldEdge]]:
        """Breadth-first walk of single-hop edges, in code (see module docstring)."""
        start = await self.get(entity_id)
        if start is None:
            return [], []

        entities: dict[str, WorldEntity] = {start.id: start}
        edges: dict[tuple[str, str, str], WorldEdge] = {}
        frontier = [entity_id]

        for _ in range(depth):
            next_frontier: list[str] = []
            for current_id in frontier:
                for edge in await self.list_edges_for(current_id, rel_types=rel_types):
                    edges[(edge.source, edge.target, str(edge.type))] = edge
                    for endpoint in (edge.source, edge.target):
                        # The vocabulary spans edges owned by other aggregates,
                        # so an endpoint may be a Task or Memory. Those are not
                        # world nodes: skip them here and let graph assembly
                        # drop the edge rather than resolving a label for a
                        # node the World screen does not draw.
                        if endpoint in entities or not is_world_entity_id(endpoint):
                            continue
                        found = await self.get(endpoint)
                        if found is not None:
                            entities[found.id] = found
                            next_frontier.append(found.id)
            frontier = next_frontier
            if not frontier:
                break

        return list(entities.values()), list(edges.values())

    async def link(
        self, source_id: str, target_id: str, rel_type: WorldRelationship
    ) -> WorldEdge:
        # MERGE keeps linking idempotent: a retried or repeated call must not
        # multiply edges.
        await self._client.write(
            f"""
            MATCH (a {{id: $source_id}})
            MATCH (b {{id: $target_id}})
            MERGE (a)-[r:{rel_type}]->(b)
            """,
            source_id=source_id,
            target_id=target_id,
        )
        return WorldEdge(source=source_id, target=target_id, type=rel_type)

    async def unlink(
        self, source_id: str, target_id: str, rel_type: WorldRelationship
    ) -> bool:
        rows = await self._client.write(
            f"""
            MATCH (a {{id: $source_id}})-[r:{rel_type}]->(b {{id: $target_id}})
            DELETE r
            RETURN count(r) AS removed
            """,
            source_id=source_id,
            target_id=target_id,
        )
        return bool(rows and rows[0]["removed"])
