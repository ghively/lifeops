"""World HTTP API (BUILD_SPEC sections 36, 39, 92).

These run the real ``LifeOpsCore`` over in-memory repositories. That matters
more here than elsewhere: the world surface spans four repositories, and an
adapter test against a stubbed core would prove only that the adapter agrees
with the stub.

What is pinned: routes, status codes, stable error codes, capability
enforcement, and the graph read model's shape. Graph assembly rules live in the
domain suite, and Cypher behaviour in the persistence suite.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager  # type: ignore[import-not-found]

from lifeops.api.http import create_app, get_client
from lifeops.clock import FrozenClock
from lifeops.config.service import ConfigurationService
from lifeops.core import LifeOpsCore
from lifeops.domain.memory import MemoryDraft, MemoryType
from lifeops.domain.people import Person
from lifeops.domain.preferences import PreferenceDraft
from lifeops.domain.tasks import TaskDraft
from lifeops.domain.world import WorldEntity, WorldEntityType, WorldRelationship
from lifeops.events import WORLD_CHANGED, EventBus
from lifeops.policy import Capability, ClientIdentity, ClientRole
from lifeops.policy.capabilities import CONSOLE
from lifeops.repositories.fakes import (
    FakeMemoryRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
    FakeWorldRepository,
)
from lifeops.secrets.local_encrypted import InMemorySecretStore
from lifeops.settings import Settings

API = "/api/v1"

PRIMARY = "person_world_api_user"


class StubContainer:
    """A Container with fakes in place of NornicDB.

    The person repository and the world repository both hold the primary
    person: persons are their own aggregate but appear in the graph as
    projections, which is exactly how NornicDB stores them (one ``:Person``
    node read by two repositories).
    """

    def __init__(self, tmp_path: Path) -> None:
        self.settings = Settings(state_dir=tmp_path / "state")
        self.settings.ensure_dirs()
        self.clock = FrozenClock()
        self.secret_store = InMemorySecretStore()
        self.config = ConfigurationService(
            config_dir=self.settings.config_dir,
            secret_store=self.secret_store,
            clock=self.clock,
        )
        self.events = EventBus()
        self.people = FakePersonRepository()
        self.preferences = FakePreferenceRepository()
        self.tasks = FakeTaskRepository()
        self.memories = FakeMemoryRepository()
        # One store, two readers — as NornicDB has it.
        self.world = FakeWorldRepository(preferences=self.preferences)
        self.core = LifeOpsCore(
            people=self.people,
            preferences=self.preferences,
            tasks=self.tasks,
            memory=self.memories,
            world=self.world,
            clock=self.clock,
            events=self.events,
        )

    async def startup(self) -> None:
        person = Person(
            id=PRIMARY,
            display_name="World API User",
            is_primary=True,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        await self.people.upsert(person)
        self.world.seed(
            WorldEntity(
                id=PRIMARY,
                entity_type=WorldEntityType.PERSON,
                display_name=person.display_name,
                created_at=person.created_at,
                updated_at=person.updated_at,
            )
        )

    async def shutdown(self) -> None:
        return None

    async def health(self) -> dict[str, Any]:
        return {
            "lifeops_core": {"healthy": True, "detail": "running"},
            "nornicdb": {"healthy": True, "detail": "fake"},
            "secret_store": {"healthy": True, "detail": "in-memory"},
            "safe_mode": self.core.safe_mode,
        }


@pytest.fixture
async def env(
    tmp_path: Path,
) -> AsyncIterator[tuple[httpx.AsyncClient, Any, StubContainer]]:
    container = StubContainer(tmp_path)
    app = create_app(container=container, settings=container.settings)  # type: ignore[arg-type]
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://lifeops.test"
        ) as http_client:
            yield http_client, app, container


Env = tuple[httpx.AsyncClient, Any, "StubContainer"]


async def _create(
    client: httpx.AsyncClient,
    entity_type: str,
    display_name: str,
    **facts: str,
) -> httpx.Response:
    return await client.post(
        f"{API}/world/entities",
        json={
            "entity_type": entity_type,
            "display_name": display_name,
            "facts": facts,
        },
    )


async def _link(
    client: httpx.AsyncClient, source_id: str, target_id: str, rel_type: str
) -> httpx.Response:
    return await client.post(
        f"{API}/world/relationships",
        json={"source_id": source_id, "target_id": target_id, "rel_type": rel_type},
    )


class TestWorldGraph:
    async def test_graph_starts_with_only_the_primary_person(self, env: Env) -> None:
        client, _, _ = env
        response = await client.get(f"{API}/world/graph")
        assert response.status_code == 200
        body = response.json()
        assert [node["id"] for node in body["nodes"]] == [PRIMARY]
        assert body["edges"] == []

    async def test_graph_reflects_created_entities_and_links(self, env: Env) -> None:
        client, _, _ = env
        household = (await _create(client, "household", "Main House")).json()["id"]
        provider = (await _create(client, "provider", "ABC Electric")).json()["id"]
        assert (await _link(client, PRIMARY, household, "MEMBER_OF")).status_code == 201
        assert (
            await _link(client, household, provider, "USES_PROVIDER")
        ).status_code == 201

        body = (await client.get(f"{API}/world/graph")).json()
        assert {node["id"] for node in body["nodes"]} == {PRIMARY, household, provider}
        assert {(e["source"], e["target"], e["type"]) for e in body["edges"]} == {
            (PRIMARY, household, "MEMBER_OF"),
            (household, provider, "USES_PROVIDER"),
        }

    async def test_type_filter_narrows_nodes_and_drops_dangling_edges(
        self, env: Env
    ) -> None:
        """A filtered-out endpoint must take its edges with it (section 15)."""
        client, _, _ = env
        household = (await _create(client, "household", "Main House")).json()["id"]
        provider = (await _create(client, "provider", "ABC Electric")).json()["id"]
        await _link(client, household, provider, "USES_PROVIDER")

        body = (await client.get(f"{API}/world/graph?types=provider")).json()
        assert [node["id"] for node in body["nodes"]] == [provider]
        assert body["edges"] == []

    async def test_repeated_types_parameter_filters_on_both(self, env: Env) -> None:
        client, _, _ = env
        household = (await _create(client, "household", "Main House")).json()["id"]
        provider = (await _create(client, "provider", "ABC Electric")).json()["id"]
        await _create(client, "asset", "Land Rover")

        body = (
            await client.get(f"{API}/world/graph?types=household&types=provider")
        ).json()
        assert {node["id"] for node in body["nodes"]} == {household, provider}

    async def test_unknown_type_filter_is_422(self, env: Env) -> None:
        """A typo returns an error, not an empty world."""
        client, _, _ = env
        response = await client.get(f"{API}/world/graph?types=spaceship")
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"

    async def test_query_narrows_to_matching_entities(self, env: Env) -> None:
        client, _, _ = env
        await _create(client, "provider", "ABC Electric")
        await _create(client, "provider", "Zephyr Plumbing")

        body = (await client.get(f"{API}/world/graph?query=electric")).json()
        assert [node["label"] for node in body["nodes"]] == ["ABC Electric"]

    async def test_limit_is_bounded(self, env: Env) -> None:
        client, _, _ = env
        assert (await client.get(f"{API}/world/graph?limit=0")).status_code == 422
        assert (await client.get(f"{API}/world/graph?limit=5000")).status_code == 422


class TestPreferenceNodes:
    """BUILD_SPEC section 15 draws ``Gene ─PREFERS→ "After 10 AM"``.

    Preferences are projected into the graph, never created through it: the
    node is owned by the preference layer, which supersedes rather than
    overwrites (section 40).
    """

    async def test_section_15_example_renders(self, env: Env) -> None:
        client, _, container = env
        preference = await container.core.save_preference(
            CONSOLE,
            PreferenceDraft(
                key="scheduling.earliest_appointment_time",
                value="After 10 AM",
                subject_id=PRIMARY,
            ),
        )
        await _link(client, PRIMARY, preference.id, "PREFERS")

        body = (await client.get(f"{API}/world/graph")).json()
        labels = {node["id"]: node["label"] for node in body["nodes"]}
        assert labels[preference.id] == "After 10 AM"
        assert (PRIMARY, preference.id, "PREFERS") in {
            (e["source"], e["target"], e["type"]) for e in body["edges"]
        }

    async def test_the_preference_key_travels_as_a_fact(self, env: Env) -> None:
        """A bare value is ambiguous; the inspector must say which preference."""
        client, _, container = env
        preference = await container.core.save_preference(
            CONSOLE,
            PreferenceDraft(
                key="scheduling.earliest_appointment_time",
                value="After 10 AM",
                subject_id=PRIMARY,
            ),
        )

        body = (await client.get(f"{API}/world/entities/{preference.id}")).json()
        assert body["entity"]["entity_type"] == "preference"
        assert body["entity"]["display_name"] == "After 10 AM"
        assert body["entity"]["facts"]["key"] == "scheduling.earliest_appointment_time"

    async def test_a_superseded_preference_leaves_the_graph(self, env: Env) -> None:
        """Section 15 shows the current world; the old value is history."""
        client, _, container = env
        first = await container.core.save_preference(
            CONSOLE,
            PreferenceDraft(key="scheduling.earliest", value="After 10 AM",
                            subject_id=PRIMARY),
        )
        await _link(client, PRIMARY, first.id, "PREFERS")
        second = await container.core.save_preference(
            CONSOLE,
            PreferenceDraft(key="scheduling.earliest", value="After 9 AM",
                            subject_id=PRIMARY),
        )

        body = (await client.get(f"{API}/world/graph")).json()
        ids = {node["id"] for node in body["nodes"]}
        assert second.id in ids
        assert first.id not in ids
        # Its PREFERS edge goes with it rather than pointing at nothing.
        assert all(e["target"] != first.id for e in body["edges"])

    async def test_preferences_can_be_filtered_out(self, env: Env) -> None:
        client, _, container = env
        await container.core.save_preference(
            CONSOLE,
            PreferenceDraft(key="scheduling.earliest", value="After 10 AM",
                            subject_id=PRIMARY),
        )
        body = (await client.get(f"{API}/world/graph?types=preference")).json()
        assert [n["entity_type"] for n in body["nodes"]] == ["preference"]

    async def test_creating_a_preference_through_the_world_api_is_422(
        self, env: Env
    ) -> None:
        """Section 40: a preference opens a new version, it is never created flat."""
        client, _, _ = env
        response = await _create(client, "preference", "After 10 AM")
        assert response.status_code == 422


class TestNeighborhood:
    async def test_depth_one_reaches_direct_neighbours_only(self, env: Env) -> None:
        client, _, _ = env
        household = (await _create(client, "household", "Main House")).json()["id"]
        provider = (await _create(client, "provider", "ABC Electric")).json()["id"]
        await _link(client, PRIMARY, household, "MEMBER_OF")
        await _link(client, household, provider, "USES_PROVIDER")

        body = (
            await client.get(f"{API}/world/neighborhood?entity_id={PRIMARY}&depth=1")
        ).json()
        assert {node["id"] for node in body["nodes"]} == {PRIMARY, household}

        body = (
            await client.get(f"{API}/world/neighborhood?entity_id={PRIMARY}&depth=2")
        ).json()
        assert {node["id"] for node in body["nodes"]} == {PRIMARY, household, provider}

    async def test_unknown_entity_is_404(self, env: Env) -> None:
        client, _, _ = env
        response = await client.get(
            f"{API}/world/neighborhood?entity_id=provider_nope"
        )
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_depth_is_bounded(self, env: Env) -> None:
        client, _, _ = env
        response = await client.get(
            f"{API}/world/neighborhood?entity_id={PRIMARY}&depth=9"
        )
        assert response.status_code == 422


class TestEntityDetail:
    async def test_detail_aggregates_entity_relationships_and_neighbours(
        self, env: Env
    ) -> None:
        client, _, _ = env
        asset = (
            await _create(client, "asset", "Land Rover", insurance="Progressive")
        ).json()["id"]
        await _link(client, PRIMARY, asset, "OWNS")

        body = (await client.get(f"{API}/world/entities/{asset}")).json()
        assert body["entity"]["id"] == asset
        assert body["entity"]["entity_type"] == "asset"
        assert body["entity"]["facts"] == {"insurance": "Progressive"}
        assert body["relationships"] == [
            {"source": PRIMARY, "target": asset, "type": "OWNS"}
        ]
        # Section 16 renders names, so the far endpoint arrives labelled.
        assert [(n["id"], n["label"]) for n in body["neighbors"]] == [
            (PRIMARY, "World API User")
        ]

    async def test_detail_includes_related_tasks_and_memories(self, env: Env) -> None:
        client, _, container = env
        asset = (await _create(client, "asset", "Land Rover")).json()["id"]
        await container.core.create_task(
            CONSOLE, TaskDraft(title="Oil change", related_entity_ids=[asset])
        )
        await container.core.remember(
            CONSOLE,
            MemoryDraft(
                content="The Land Rover is insured with Progressive",
                type=MemoryType.SEMANTIC,
                entity_ids=[asset],
            ),
        )

        body = (await client.get(f"{API}/world/entities/{asset}")).json()
        assert [t["title"] for t in body["related_tasks"]] == ["Oil change"]
        assert len(body["related_memories"]) == 1
        # Provenance travels on the record itself (section 16).
        assert body["related_memories"][0]["source_type"]
        assert body["entity"]["created_by_client"] == CONSOLE.client_id

    async def test_a_task_edge_is_shown_as_a_task_not_a_relationship(
        self, env: Env
    ) -> None:
        """ABOUT and ASSIGNED_TO point at Tasks, which the graph does not draw.

        The tasks repository writes those edges, so the world surface meets
        them on every read. Section 16 gives tasks their own panel, so the
        edge belongs there rather than as an unlabelled row under
        Relationships — and nothing raises on the way through.
        """
        client, _, container = env
        asset = (await _create(client, "asset", "Land Rover")).json()["id"]
        task = await container.core.create_task(
            CONSOLE, TaskDraft(title="Oil change", related_entity_ids=[asset])
        )
        # Written by NornicTaskRepository in production; seeded directly here.
        await container.world.link(task.id, asset, WorldRelationship.ABOUT)

        body = (await client.get(f"{API}/world/entities/{asset}")).json()
        assert body["relationships"] == []
        assert body["neighbors"] == []
        # Reported where section 16 puts it, with its title rather than an id.
        assert [t["title"] for t in body["related_tasks"]] == ["Oil change"]

    async def test_a_foreign_endpoint_is_dropped_from_the_graph(
        self, env: Env
    ) -> None:
        """No arrow into a node the World screen never renders."""
        client, _, container = env
        asset = (await _create(client, "asset", "Land Rover")).json()["id"]
        task = await container.core.create_task(
            CONSOLE, TaskDraft(title="Oil change", related_entity_ids=[asset])
        )
        await container.world.link(task.id, asset, WorldRelationship.ABOUT)

        assert (await client.get(f"{API}/world/graph")).json()["edges"] == []
        hood = (
            await client.get(f"{API}/world/neighborhood?entity_id={asset}&depth=2")
        ).json()
        assert [n["id"] for n in hood["nodes"]] == [asset]

    async def test_unknown_entity_is_404_with_a_code(self, env: Env) -> None:
        client, _, _ = env
        response = await client.get(f"{API}/world/entities/provider_nope")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_a_non_world_id_is_422(self, env: Env) -> None:
        """A task ID is addressable, but it is not a world entity."""
        client, _, _ = env
        response = await client.get(f"{API}/world/entities/task_01abc")
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"


class TestEntityHistory:
    async def test_history_returns_memories_including_closed_windows(
        self, env: Env
    ) -> None:
        client, _, container = env
        provider = (await _create(client, "provider", "ABC Electric")).json()["id"]
        memory = await container.core.remember(
            CONSOLE,
            MemoryDraft(
                content="ABC Electric handles the wiring",
                type=MemoryType.SEMANTIC,
                entity_ids=[provider],
            ),
        )
        await container.core.correct_memory(
            CONSOLE, memory_id=memory.id, new_content="ABC Electric rewired the kitchen"
        )

        body = (await client.get(f"{API}/world/entities/{provider}/history")).json()
        assert body["entity_id"] == provider
        # Both the closed original and its replacement.
        assert len(body["memories"]) == 2
        assert any(m["valid_to"] is not None for m in body["memories"])
        assert body["fact_history"] == []
        assert body["covers"] == [
            "every version of every fact this entity has carried",
            "memories referencing this entity, including closed versions",
        ]

    async def test_unknown_history_is_404(self, env: Env) -> None:
        client, _, _ = env
        response = await client.get(f"{API}/world/entities/provider_nope/history")
        assert response.status_code == 404


class TestCreateEntity:
    async def test_create_returns_201_with_a_slug_id(self, env: Env) -> None:
        client, _, _ = env
        response = await _create(client, "provider", "ABC Electric", phone="555-0100")
        assert response.status_code == 201
        body = response.json()
        assert body["id"] == "provider_abc_electric"
        assert body["entity_type"] == "provider"
        assert body["display_name"] == "ABC Electric"
        assert body["facts"] == {"phone": "555-0100"}
        assert body["created_by_client"] == CONSOLE.client_id

    async def test_creating_a_person_is_422(self, env: Env) -> None:
        """Persons carry primary-user semantics and use the person surface."""
        client, _, _ = env
        response = await _create(client, "person", "Someone Else")
        assert response.status_code == 422

    async def test_missing_display_name_is_422(self, env: Env) -> None:
        client, _, _ = env
        response = await client.post(
            f"{API}/world/entities", json={"entity_type": "asset", "display_name": ""}
        )
        assert response.status_code == 422

    async def test_unsluggable_display_name_is_422(self, env: Env) -> None:
        client, _, _ = env
        response = await _create(client, "asset", "!!!")
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"

    async def test_duplicate_entity_is_409(self, env: Env) -> None:
        client, _, _ = env
        assert (await _create(client, "provider", "ABC Electric")).status_code == 201
        response = await _create(client, "provider", "ABC Electric")
        assert response.status_code == 409
        assert response.json()["code"] == "conflict"

    async def test_create_publishes_a_world_changed_event(self, env: Env) -> None:
        client, _, container = env
        subscription = container.events.subscribe()
        await _create(client, "provider", "ABC Electric")
        event = await subscription.get()
        assert event["type"] == WORLD_CHANGED
        assert event["entity_id"] == "provider_abc_electric"


class TestUpdateEntity:
    """Per-fact history (section 16): PATCH revises current facts and every
    change is recorded, the same "current state is a projection, history is
    the source of truth" split preferences already have."""

    async def test_revising_a_fact_updates_current_state(self, env: Env) -> None:
        client, _, _ = env
        provider = (
            await _create(client, "provider", "ABC Electric", phone="555-0100")
        ).json()["id"]

        response = await client.patch(
            f"{API}/world/entities/{provider}", json={"facts": {"phone": "555-9999"}}
        )
        assert response.status_code == 200
        assert response.json()["facts"] == {"phone": "555-9999"}

    async def test_the_old_value_is_recoverable_from_history(self, env: Env) -> None:
        client, _, _ = env
        provider = (
            await _create(client, "provider", "ABC Electric", phone="555-0100")
        ).json()["id"]
        await client.patch(
            f"{API}/world/entities/{provider}", json={"facts": {"phone": "555-9999"}}
        )

        body = (await client.get(f"{API}/world/entities/{provider}/history")).json()
        history = [f for f in body["fact_history"] if f["key"] == "phone"]
        assert len(history) == 2
        current = next(f for f in history if f["valid_to"] is None)
        closed = next(f for f in history if f["valid_to"] is not None)
        assert current["value"] == "555-9999"
        assert closed["value"] == "555-0100"
        assert current["supersedes"] == closed["id"]

    async def test_re_stating_the_same_value_is_a_no_op(self, env: Env) -> None:
        client, _, _ = env
        provider = (
            await _create(client, "provider", "ABC Electric", phone="555-0100")
        ).json()["id"]
        await client.patch(
            f"{API}/world/entities/{provider}", json={"facts": {"phone": "555-0100"}}
        )

        body = (await client.get(f"{API}/world/entities/{provider}/history")).json()
        history = [f for f in body["fact_history"] if f["key"] == "phone"]
        assert len(history) == 1

    async def test_a_new_fact_key_is_seeded_with_its_own_history(self, env: Env) -> None:
        client, _, _ = env
        provider = (await _create(client, "provider", "ABC Electric")).json()["id"]
        response = await client.patch(
            f"{API}/world/entities/{provider}", json={"facts": {"trade": "electrician"}}
        )
        assert response.json()["facts"] == {"trade": "electrician"}

        body = (await client.get(f"{API}/world/entities/{provider}/history")).json()
        history = [f for f in body["fact_history"] if f["key"] == "trade"]
        assert len(history) == 1
        assert history[0]["supersedes"] is None

    async def test_unrelated_facts_are_left_alone(self, env: Env) -> None:
        client, _, _ = env
        provider = (
            await _create(client, "provider", "ABC Electric", phone="555-0100", trade="electrician")
        ).json()["id"]
        response = await client.patch(
            f"{API}/world/entities/{provider}", json={"facts": {"phone": "555-9999"}}
        )
        assert response.json()["facts"] == {"phone": "555-9999", "trade": "electrician"}

    async def test_unknown_entity_is_404(self, env: Env) -> None:
        client, _, _ = env
        response = await client.patch(
            f"{API}/world/entities/provider_nope", json={"facts": {"phone": "555-0100"}}
        )
        assert response.status_code == 404


class TestRelationships:
    async def test_link_returns_201_with_the_edge(self, env: Env) -> None:
        client, _, _ = env
        household = (await _create(client, "household", "Main House")).json()["id"]
        response = await _link(client, PRIMARY, household, "MEMBER_OF")
        assert response.status_code == 201
        assert response.json() == {
            "source": PRIMARY,
            "target": household,
            "type": "MEMBER_OF",
        }

    async def test_relinking_is_idempotent(self, env: Env) -> None:
        """MERGE semantics: a retry must not multiply edges."""
        client, _, _ = env
        household = (await _create(client, "household", "Main House")).json()["id"]
        await _link(client, PRIMARY, household, "MEMBER_OF")
        assert (await _link(client, PRIMARY, household, "MEMBER_OF")).status_code == 201

        body = (await client.get(f"{API}/world/graph")).json()
        assert len(body["edges"]) == 1

    async def test_the_whole_section_39_vocabulary_is_accepted(self, env: Env) -> None:
        """Every type the spec defines links, not a chosen subset of them."""
        client, _, _ = env
        household = (await _create(client, "household", "Main House")).json()["id"]
        for rel_type in (
            "MEMBER_OF",
            "PREFERS",
            "AUTHORIZES",
            "WAITING_ON",
            "DERIVED_FROM",
            "REFERENCES",
        ):
            response = await _link(client, PRIMARY, household, rel_type)
            assert response.status_code == 201, rel_type
            assert response.json()["type"] == rel_type

    async def test_a_type_outside_the_vocabulary_is_422(self, env: Env) -> None:
        client, _, _ = env
        household = (await _create(client, "household", "Main House")).json()["id"]
        response = await _link(client, PRIMARY, household, "BEFRIENDS")
        assert response.status_code == 422

    async def test_linking_an_unknown_entity_is_404(self, env: Env) -> None:
        client, _, _ = env
        response = await _link(client, PRIMARY, "household_nope", "MEMBER_OF")
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_self_link_is_422(self, env: Env) -> None:
        client, _, _ = env
        response = await _link(client, PRIMARY, PRIMARY, "RELATED_TO")
        assert response.status_code == 422

    async def test_unlink_removes_the_edge(self, env: Env) -> None:
        client, _, _ = env
        household = (await _create(client, "household", "Main House")).json()["id"]
        await _link(client, PRIMARY, household, "MEMBER_OF")

        response = await client.delete(
            f"{API}/world/relationships"
            f"?source_id={PRIMARY}&target_id={household}&rel_type=MEMBER_OF"
        )
        assert response.status_code == 204
        assert (await client.get(f"{API}/world/graph")).json()["edges"] == []

    async def test_unlinking_an_unknown_relationship_is_404(self, env: Env) -> None:
        client, _, _ = env
        household = (await _create(client, "household", "Main House")).json()["id"]
        response = await client.delete(
            f"{API}/world/relationships"
            f"?source_id={PRIMARY}&target_id={household}&rel_type=MEMBER_OF"
        )
        assert response.status_code == 404

    async def test_unlink_with_an_invalid_rel_type_is_422(self, env: Env) -> None:
        client, _, _ = env
        response = await client.delete(
            f"{API}/world/relationships"
            f"?source_id={PRIMARY}&target_id=household_x&rel_type=NONSENSE"
        )
        assert response.status_code == 422


class TestRoundTrip:
    async def test_create_link_inspect_neighborhood_unlink(self, env: Env) -> None:
        """The World screen's whole loop over one graph (section 92)."""
        client, _, _ = env
        household = (await _create(client, "household", "Main House")).json()["id"]
        asset = (
            await _create(client, "asset", "Land Rover", mileage="114203")
        ).json()["id"]
        provider = (await _create(client, "provider", "ABC Auto")).json()["id"]

        await _link(client, PRIMARY, household, "MEMBER_OF")
        await _link(client, household, asset, "OWNS")
        await _link(client, asset, provider, "USES_PROVIDER")

        graph = (await client.get(f"{API}/world/graph")).json()
        assert len(graph["nodes"]) == 4
        assert len(graph["edges"]) == 3

        detail = (await client.get(f"{API}/world/entities/{asset}")).json()
        assert detail["entity"]["facts"] == {"mileage": "114203"}
        assert {n["id"] for n in detail["neighbors"]} == {household, provider}

        hood = (
            await client.get(f"{API}/world/neighborhood?entity_id={asset}&depth=1")
        ).json()
        assert {n["id"] for n in hood["nodes"]} == {asset, household, provider}

        assert (
            await client.delete(
                f"{API}/world/relationships"
                f"?source_id={asset}&target_id={provider}&rel_type=USES_PROVIDER"
            )
        ).status_code == 204
        assert len((await client.get(f"{API}/world/graph")).json()["edges"]) == 2


class TestCapabilities:
    """The world surface is capability-gated like every other (section 50)."""

    @staticmethod
    def _override(app: Any, client: ClientIdentity) -> None:
        app.dependency_overrides[get_client] = lambda: client

    async def test_read_without_read_world_is_403(self, env: Env) -> None:
        client, app, _ = env
        self._override(
            app,
            ClientIdentity(
                client_id="no-caps",
                role=ClientRole.ENGINEERING_ASSISTANT,
                display_name="No capabilities",
                capabilities=frozenset(),
            ),
        )
        response = await client.get(f"{API}/world/graph")
        assert response.status_code == 403
        assert response.json()["code"] == "capability_denied"

    async def test_write_requires_write_world_not_just_read(self, env: Env) -> None:
        client, app, _ = env
        self._override(
            app,
            ClientIdentity(
                client_id="reader",
                role=ClientRole.ENGINEERING_ASSISTANT,
                display_name="Reader",
                capabilities=frozenset({Capability.READ_WORLD}),
            ),
        )
        assert (await client.get(f"{API}/world/graph")).status_code == 200
        response = await _create(client, "provider", "ABC Electric")
        assert response.status_code == 403
        assert response.json()["code"] == "capability_denied"

    async def test_update_facts_requires_write_world_not_just_read(
        self, env: Env
    ) -> None:
        client, app, _ = env
        provider = (
            await _create(client, "provider", "ABC Electric", phone="555-0100")
        ).json()["id"]
        self._override(
            app,
            ClientIdentity(
                client_id="reader",
                role=ClientRole.ENGINEERING_ASSISTANT,
                display_name="Reader",
                capabilities=frozenset({Capability.READ_WORLD}),
            ),
        )
        response = await client.patch(
            f"{API}/world/entities/{provider}", json={"facts": {"phone": "555-9999"}}
        )
        assert response.status_code == 403
        assert response.json()["code"] == "capability_denied"

    async def test_inspector_degrades_rather_than_denying(self, env: Env) -> None:
        """A client that may see the graph but not tasks gets an empty panel.

        Returning 403 for the whole inspector would make the graph unusable
        for read-limited clients; the aggregate narrows to what they may see.
        """
        http, app, container = env
        asset = (await _create(http, "asset", "Land Rover")).json()["id"]
        await container.core.create_task(
            CONSOLE, TaskDraft(title="Oil change", related_entity_ids=[asset])
        )

        self._override(
            app,
            ClientIdentity(
                client_id="world-only",
                role=ClientRole.ENGINEERING_ASSISTANT,
                display_name="World only",
                capabilities=frozenset({Capability.READ_WORLD}),
            ),
        )
        body = (await http.get(f"{API}/world/entities/{asset}")).json()
        assert body["entity"]["id"] == asset
        assert body["related_tasks"] == []
        assert body["related_memories"] == []
