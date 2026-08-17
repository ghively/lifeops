"""BUILD_SPEC enumerations must survive contact with the code.

Phase 3 implemented four of section 39's twenty relationship types and wrote
the narrowing up as a principle. Sections 36 and 39 both give their lists as
*Initial* and then warn against adding to them — a bound on invention, not
licence to implement less. These tests turn that from a judgement call into a
red build.
"""

from __future__ import annotations

from lifeops.domain.world import WorldEntityType, WorldRelationship
from tests.spec.spec_source import fenced_fields, fenced_list, snake

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


class TestPhase4Schemas:
    """Phase 4's schemas, pinned before they are implemented.

    AGENTS.md: when a phase adds an enumeration to BUILD_SPEC, pin it here
    first. These are the section 54/59/60 records the durable-work phase
    builds; the assertions fail until the models carry every field the spec
    names, and keep failing if one is later dropped.
    """

    def test_waiting_item_carries_every_section_54_field(self) -> None:
        from lifeops.domain.waiting import WaitingItem

        assert set(fenced_fields(54)) <= set(WaitingItem.model_fields)

    def test_action_carries_every_section_60_field(self) -> None:
        from lifeops.domain.actions import Action

        # The spec names the identifier `action_id`; the model calls it `id`,
        # as every other LifeOps record does. Compare the rest verbatim.
        spec = {f for f in fenced_fields(60) if f != "action_id"}
        assert spec <= set(Action.model_fields)
        assert "id" in Action.model_fields

    def test_approval_carries_every_section_59_field(self) -> None:
        from lifeops.domain.approvals import Approval

        spec = {f for f in fenced_fields(59) if f != "approval_id"}
        assert spec <= set(Approval.model_fields)
        assert "id" in Approval.model_fields

    def test_audit_record_carries_every_section_62_field(self) -> None:
        from lifeops.domain.audit import AuditRecord

        assert set(fenced_fields(62)) <= set(AuditRecord.model_fields)

    def test_continuation_state_lives_on_the_waiting_item(self) -> None:
        """Section 55: durable continuation state is stored in NornicDB, with
        a lease so one worker claims an item at a time.

        Section 55's ``wake_at`` is section 54's ``next_action_at`` — the same
        instant under two names — so the model carries one field, not two.
        ``attempt_count`` stays distinct from ``followup_count``: a worker
        attempt that fails is not a follow-up the provider ever saw.
        """
        from lifeops.domain.waiting import WaitingItem

        for field in ("next_action_at", "attempt_count", "lease_owner", "lease_until"):
            assert field in WaitingItem.model_fields, field
