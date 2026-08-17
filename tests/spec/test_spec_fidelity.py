"""BUILD_SPEC enumerations must survive contact with the code.

Phase 3 implemented four of section 39's twenty relationship types and wrote
the narrowing up as a principle. Sections 36 and 39 both give their lists as
*Initial* and then warn against adding to them — a bound on invention, not
licence to implement less. These tests turn that from a judgement call into a
red build.
"""

from __future__ import annotations

from lifeops.domain.world import WorldEntityType, WorldRelationship
from tests.spec.spec_source import fenced_list, snake

#: Every section 36 canonical entity type, mapped to the phase that owns it.
#: Mirrors section 7 of the program roadmap. A type may be deferred, but only
#: out loud: "unscheduled" is a decision, a missing key is an accident.
PHASE_FOR_ENTITY_TYPE: dict[str, str] = {
    "Person": "0",
    "Preference": "0",
    "Task": "0",
    "Memory": "2",
    "Household": "3",
    "Provider": "3",
    "Asset": "3",
    "WaitingItem": "4",
    "Action": "4",
    "Approval": "4",
    "Appointment": "7",
    "Event": "7",
    "Document": "7",
    "ServiceRequest": "8",
    "ShoppingList": "9",
    "Bill": "10",
    "WorkflowTemplate": "11",
    "Knowledge": "unscheduled",
}


class TestRelationshipVocabulary:
    def test_the_whole_section_39_vocabulary_is_implemented(self) -> None:
        """All twenty types, in the spec's order."""
        assert [str(r) for r in WorldRelationship] == fenced_list(39)


class TestEntityTypes:
    def test_every_section_36_type_is_assigned_a_phase(self) -> None:
        """Nothing from the spec's list may vanish without a decision."""
        assert set(PHASE_FOR_ENTITY_TYPE) == set(fenced_list(36))

    def test_the_world_graph_renders_only_section_36_types(self) -> None:
        """The graph may render a subset (section 92 scopes Phase 3), but it
        may not invent a type the world model does not define."""
        spec_types = {snake(name) for name in fenced_list(36)}
        rendered = {str(entity_type) for entity_type in WorldEntityType}
        assert rendered <= spec_types

    def test_every_rendered_type_is_owned_by_a_delivered_phase(self) -> None:
        """A type the graph draws cannot still be marked unscheduled."""
        by_snake = {snake(name): phase for name, phase in PHASE_FOR_ENTITY_TYPE.items()}
        for entity_type in WorldEntityType:
            assert by_snake[str(entity_type)] != "unscheduled"
