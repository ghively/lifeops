"""World domain rules (BUILD_SPEC sections 36–39).

Pure functions only: no repository, no adapter, no database. These are the
rules both the HTTP and MCP surfaces inherit, so they are pinned here once
rather than twice at the edges.
"""

from __future__ import annotations

import pytest

from lifeops.domain.world import (
    EntityDraft,
    WorldEdge,
    WorldEntity,
    WorldEntityType,
    WorldGraph,
    WorldRelationship,
    assemble_world_graph,
    entity_type_for_id,
    parse_entity_types,
    parse_relationship,
    validate_facts,
)
from lifeops.errors import ValidationError

TS = "2026-01-01T00:00:00Z"


def _entity(entity_id: str, entity_type: WorldEntityType, name: str) -> WorldEntity:
    return WorldEntity(
        id=entity_id,
        entity_type=entity_type,
        display_name=name,
        created_at=TS,
        updated_at=TS,
    )


class TestEntityIds:
    def test_id_is_derived_from_type_and_name(self) -> None:
        assert (
            WorldEntity.make_id(WorldEntityType.PROVIDER, "ABC Electric")
            == "provider_abc_electric"
        )

    def test_unicode_folds_so_one_entity_does_not_become_two(self) -> None:
        assert WorldEntity.make_id(
            WorldEntityType.ASSET, "Zoë"
        ) == WorldEntity.make_id(WorldEntityType.ASSET, "Zoe")

    @pytest.mark.parametrize(
        ("entity_id", "expected"),
        [
            ("person_gene", WorldEntityType.PERSON),
            ("household_main", WorldEntityType.HOUSEHOLD),
            ("provider_abc_electric", WorldEntityType.PROVIDER),
            ("asset_land_rover", WorldEntityType.ASSET),
        ],
    )
    def test_type_is_recoverable_from_the_id(
        self, entity_id: str, expected: WorldEntityType
    ) -> None:
        assert entity_type_for_id(entity_id) == expected

    def test_a_task_id_is_addressable_but_not_a_world_entity(self) -> None:
        with pytest.raises(ValidationError):
            entity_type_for_id("task_01j5x")

    def test_a_malformed_id_is_rejected_rather_than_guessed(self) -> None:
        with pytest.raises(ValidationError):
            entity_type_for_id("Not An Id")


class TestEntityDraft:
    def test_persons_are_not_created_through_the_entity_surface(self) -> None:
        """They carry primary-user semantics and use ``create_person``."""
        with pytest.raises(ValueError):
            EntityDraft(entity_type=WorldEntityType.PERSON, display_name="Gene")

    def test_the_three_world_types_are_accepted(self) -> None:
        for entity_type in (
            WorldEntityType.HOUSEHOLD,
            WorldEntityType.PROVIDER,
            WorldEntityType.ASSET,
        ):
            assert EntityDraft(entity_type=entity_type, display_name="X")


class TestRelationshipVocabulary:
    def test_names_are_parsed_case_insensitively(self) -> None:
        assert parse_relationship("member_of") is WorldRelationship.MEMBER_OF
        assert parse_relationship("  OWNS ") is WorldRelationship.OWNS

    def test_the_whole_section_39_vocabulary_is_accepted(self) -> None:
        """All twenty, in the spec's order.

        Section 39 gives this as the initial vocabulary and warns against
        inventing more; it does not license implementing fewer. Pinned
        literally so narrowing the enum fails here rather than silently
        rejecting a relationship the spec defines.
        """
        assert [str(r) for r in WorldRelationship] == [
            "MEMBER_OF",
            "RELATED_TO",
            "PREFERS",
            "OWNS",
            "USES_PROVIDER",
            "ASSIGNED_TO",
            "ABOUT",
            "WITH_PROVIDER",
            "FOR_ASSET",
            "WAITING_ON",
            "REQUIRES_APPROVAL",
            "AUTHORIZES",
            "CREATED_BY",
            "REQUESTED_BY",
            "EXECUTED_BY",
            "VERIFIED_BY",
            "DERIVED_FROM",
            "SUPERSEDES",
            "RELATED_MEMORY",
            "REFERENCES",
        ]
        for relationship in WorldRelationship:
            assert parse_relationship(str(relationship)) is relationship

    def test_a_type_outside_the_vocabulary_is_refused(self) -> None:
        """Section 39: do not invent relationships beyond the initial list."""
        with pytest.raises(ValidationError):
            parse_relationship("BEFRIENDS")


class TestEntityTypeFilters:
    def test_none_means_no_filter(self) -> None:
        assert parse_entity_types(None) is None

    def test_names_are_parsed_and_deduplicated(self) -> None:
        assert parse_entity_types(["asset", "ASSET", " provider "]) == [
            WorldEntityType.ASSET,
            WorldEntityType.PROVIDER,
        ]

    def test_a_typo_is_an_error_not_an_empty_world(self) -> None:
        with pytest.raises(ValidationError):
            parse_entity_types(["spaceship"])


class TestFacts:
    def test_keys_and_values_are_stripped(self) -> None:
        assert validate_facts({"  mileage  ": " 114203 "}) == {"mileage": "114203"}

    def test_an_empty_key_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            validate_facts({"   ": "value"})

    def test_the_bag_is_capped(self) -> None:
        """An agent must not be able to turn one entity into a document store."""
        with pytest.raises(ValidationError):
            validate_facts({f"key{i}": "v" for i in range(51)})

    def test_an_oversized_value_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            validate_facts({"notes": "x" * 501})

    def test_an_empty_bag_is_fine(self) -> None:
        assert validate_facts({}) == {}


class TestGraphAssembly:
    def test_nodes_carry_the_label_the_screen_renders(self) -> None:
        graph = assemble_world_graph(
            [_entity("provider_abc", WorldEntityType.PROVIDER, "ABC Electric")],
            [],
            limit=10,
        )
        assert graph.nodes[0].label == "ABC Electric"
        assert graph.nodes[0].entity_type is WorldEntityType.PROVIDER

    def test_edges_with_a_missing_endpoint_are_dropped(self) -> None:
        """The Console must never render an arrow into nowhere."""
        graph = assemble_world_graph(
            [_entity("household_main", WorldEntityType.HOUSEHOLD, "Main")],
            [
                WorldEdge(
                    source="household_main",
                    target="provider_gone",
                    type=WorldRelationship.USES_PROVIDER,
                )
            ],
            limit=10,
        )
        assert graph.edges == []

    def test_duplicate_nodes_and_edges_collapse(self) -> None:
        household = _entity("household_main", WorldEntityType.HOUSEHOLD, "Main")
        provider = _entity("provider_abc", WorldEntityType.PROVIDER, "ABC")
        edge = WorldEdge(
            source="household_main",
            target="provider_abc",
            type=WorldRelationship.USES_PROVIDER,
        )
        graph = assemble_world_graph(
            [household, provider, household], [edge, edge], limit=10
        )
        assert len(graph.nodes) == 2
        assert len(graph.edges) == 1

    def test_the_limit_caps_nodes_and_takes_their_edges_with_them(self) -> None:
        entities = [
            _entity(f"asset_a{i}", WorldEntityType.ASSET, f"Asset {i}") for i in range(5)
        ]
        edge = WorldEdge(
            source="asset_a0", target="asset_a4", type=WorldRelationship.RELATED_TO
        )
        graph = assemble_world_graph(entities, [edge], limit=2)
        assert len(graph.nodes) == 2
        assert graph.edges == []

    def test_an_empty_world_is_an_empty_graph(self) -> None:
        assert assemble_world_graph([], [], limit=10) == WorldGraph()
