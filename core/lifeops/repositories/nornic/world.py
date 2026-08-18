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
    WORLD_MANAGED_ENTITY_TYPES,
    WORLD_RELATIONSHIP_TYPES,
    EntityFact,
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
    # Phase 7 (section 96): Appointment carries its own booking state machine
    # and Event/Document are written by the calendar and email flows, so all
    # three are projected here the same way Person is — readable through the
    # generic entity path, written through ``WORLD_MANAGED_ENTITY_TYPES``
    # rather than the narrower ``CREATABLE_ENTITY_TYPES`` generic-create guard.
    WorldEntityType.APPOINTMENT: "Appointment",
    WorldEntityType.EVENT: "Event",
    WorldEntityType.DOCUMENT: "Document",
    # Phase 8 (section 97): a ServiceRequest carries its own workflow status
    # the same way Appointment carries a booking status, so it is written
    # through ``WORLD_MANAGED_ENTITY_TYPES`` rather than the generic-create
    # path too.
    WorldEntityType.SERVICE_REQUEST: "ServiceRequest",
    # Phase 9 (section 98): a ShoppingList carries its own cart/checkout
    # status the same way Appointment carries a booking status, so it is
    # written through ``WORLD_MANAGED_ENTITY_TYPES`` rather than the
    # generic-create path too.
    WorldEntityType.SHOPPING_LIST: "ShoppingList",
    # Knowledge (section 18) is written through ``record_knowledge``, the
    # same non-generic path Document uses, for the same reason: free-text
    # content deserves its own draft shape rather than the generic entity
    # path's bare key/value validation.
    WorldEntityType.KNOWLEDGE: "Knowledge",
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


#: EntityFact is a plain versioned record, not a shaped entity — no label
#: lookup, no facts_json, matched by (entity_id, key) properties exactly the
#: way Preference is matched by (subject_id, key).
_FACT_RETURN = """
    f.id AS id,
    f.entity_id AS entity_id,
    f.key AS key,
    f.value AS value,
    f.valid_from AS valid_from,
    f.valid_to AS valid_to,
    f.supersedes AS supersedes,
    f.created_by_client AS created_by_client
"""


def _row_to_fact(row: dict[str, Any]) -> EntityFact:
    return EntityFact(
        id=row["id"],
        entity_id=row["entity_id"],
        key=row["key"],
        value=row["value"],
        valid_from=row["valid_from"],
        valid_to=row.get("valid_to"),
        supersedes=row.get("supersedes"),
        created_by_client=row.get("created_by_client"),
    )


def _fact_write_params(fact: EntityFact) -> dict[str, Any]:
    return {
        "id": fact.id,
        "entity_id": fact.entity_id,
        "key": fact.key,
        "value": fact.value,
        "valid_from": fact.valid_from,
        "valid_to": fact.valid_to,
        "supersedes": fact.supersedes,
        "created_by_client": fact.created_by_client,
    }


_CREATE_FACT = """
    MERGE (f:EntityFact {id: $id})
    SET f.entity_id = $entity_id,
        f.key = $key,
        f.value = $value,
        f.valid_from = $valid_from,
        f.valid_to = $valid_to,
        f.supersedes = $supersedes,
        f.created_by_client = $created_by_client
"""


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
        # with the wrong property shape. ``WORLD_MANAGED_ENTITY_TYPES`` is
        # wider than the generic-create ``CREATABLE_ENTITY_TYPES``: Appointment,
        # Event, and Document are written by dedicated LifeOpsCore flows that
        # build the ``WorldEntity`` themselves rather than through
        # ``EntityDraft``, so this guard checks the broader set while the
        # generic Console/MCP "add an entity" path stays closed to them.
        if entity.entity_type not in WORLD_MANAGED_ENTITY_TYPES:
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

    # --- per-fact history (section 16) --------------------------------------

    async def current_facts(self, entity_id: str) -> dict[str, EntityFact]:
        rows = await self._client.read(
            f"""
            MATCH (f:EntityFact)
            WHERE f.entity_id = $entity_id AND f.valid_to IS NULL
            RETURN {_FACT_RETURN}
            """,
            entity_id=entity_id,
        )
        facts = [_row_to_fact(r) for r in rows]
        return {fact.key: fact for fact in facts}

    async def fact_history(
        self, entity_id: str, *, key: str | None = None
    ) -> list[EntityFact]:
        where = "f.entity_id = $entity_id"
        params: dict[str, Any] = {"entity_id": entity_id}
        if key is not None:
            where += " AND f.key = $key"
            params["key"] = key
        rows = await self._client.read(
            f"""
            MATCH (f:EntityFact)
            WHERE {where}
            RETURN {_FACT_RETURN}
            ORDER BY f.valid_from DESC, f.id DESC
            """,
            **params,
        )
        return [_row_to_fact(r) for r in rows]

    async def seed_fact_versions(self, versions: list[EntityFact]) -> None:
        if not versions:
            return
        await self._client.write_many(
            [(_CREATE_FACT, _fact_write_params(v)) for v in versions]
        )

    async def update_facts(
        self,
        entity: WorldEntity,
        *,
        new_versions: list[EntityFact],
        superseded_ids: list[str],
    ) -> WorldEntity:
        if entity.entity_type not in WORLD_MANAGED_ENTITY_TYPES:
            raise ValueError(
                f"{entity.entity_type} is not written by the world repository"
            )
        label = _LABEL_FOR_TYPE[entity.entity_type]
        statements: list[tuple[str, dict[str, Any]]] = [
            (
                f"""
                MATCH (n:{label} {{id: $id}})
                SET n.facts_json = $facts_json,
                    n.updated_at = $updated_at
                """,
                {
                    "id": entity.id,
                    "facts_json": json.dumps(entity.facts, sort_keys=True),
                    "updated_at": entity.updated_at,
                },
            )
        ]
        for old_id in superseded_ids:
            statements.append(
                (
                    "MATCH (old:EntityFact {id: $old_id}) SET old.valid_to = $valid_to",
                    {"old_id": old_id, "valid_to": entity.updated_at},
                )
            )
        for version in new_versions:
            statements.append((_CREATE_FACT, _fact_write_params(version)))
            if version.supersedes:
                statements.append(
                    (
                        """
                        MATCH (new:EntityFact {id: $new_id})
                        MATCH (old:EntityFact {id: $old_id})
                        MERGE (new)-[:SUPERSEDES]->(old)
                        """,
                        {"new_id": version.id, "old_id": version.supersedes},
                    )
                )
        await self._client.write_many(statements)
        stored = await self.get(entity.id)
        return stored or entity
