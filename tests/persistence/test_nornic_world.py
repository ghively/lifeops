"""World repository behaviour against a live NornicDB (BUILD_SPEC 36–39, 92).

The fakes prove the domain rules; only these prove the Cypher is right. Two
things here exist specifically because NornicDB does not behave like Neo4j:

  * ``facts`` round-trips through a JSON string property, because map-valued
    properties are rejected at write time;
  * neighbourhood expansion is an explicit breadth-first walk of *directed*
    single hops, because undirected and variable-length patterns return
    phantom rows (found in Phase 2).

If either regressed, the fakes would stay green and only these tests would
fail — which is the point of having them.

Skipped automatically when NornicDB is not reachable.
"""

from __future__ import annotations

import pytest

from lifeops.domain.people import Person
from lifeops.domain.preferences import Preference, PreferenceSource
from lifeops.domain.world import (
    WorldEntity,
    WorldEntityType,
    WorldRelationship,
)
from lifeops.ids import PREFIX_PERSON, slug_id
from lifeops.repositories.nornic.client import NornicClient
from lifeops.repositories.nornic.people import NornicPersonRepository
from lifeops.repositories.nornic.preferences import NornicPreferenceRepository
from lifeops.repositories.nornic.world import NornicWorldRepository

pytestmark = [pytest.mark.integration, pytest.mark.persistence]

TS = "2026-01-01T00:00:00Z"


@pytest.fixture
async def world(nornic_client: NornicClient, test_label: str):
    """The repository plus a label unique to this test, and a cleanup sweep.

    Every entity a test creates is named with ``test_label`` so the teardown
    can remove exactly its own residue from a shared database.
    """
    repo = NornicWorldRepository(nornic_client)
    people = NornicPersonRepository(nornic_client)
    created: list[str] = []

    def make(entity_type: WorldEntityType, name: str, **facts: str) -> WorldEntity:
        entity = WorldEntity(
            id=WorldEntity.make_id(entity_type, f"{name} {test_label}"),
            entity_type=entity_type,
            display_name=name,
            facts=facts,
            created_at=TS,
            updated_at=TS,
            created_by_client="lifeops-console",
        )
        created.append(entity.id)
        return entity

    async def make_person(name: str) -> WorldEntity:
        """Write a Person through the repository that owns it.

        The world repository refuses to create persons — they carry their own
        model — so a graph test needing one goes through the person
        repository, exactly as production does.
        """
        person = Person(
            id=slug_id(PREFIX_PERSON, f"{name} {test_label}"),
            display_name=name,
            is_primary=False,
            created_at=TS,
            updated_at=TS,
        )
        await people.upsert(person)
        created.append(person.id)
        projected = await repo.get(person.id)
        assert projected is not None
        return projected

    try:
        yield repo, make, make_person
    finally:
        for entity_id in created:
            await nornic_client.write(
                "MATCH (n {id: $id}) DETACH DELETE n", id=entity_id
            )


class TestEntityRoundTrip:
    async def test_create_and_get(self, world) -> None:
        repo, make, make_person = world
        entity = await repo.create(
            make(WorldEntityType.PROVIDER, "ABC Electric", phone="555-0100")
        )

        fetched = await repo.get(entity.id)
        assert fetched is not None
        assert fetched.id == entity.id
        assert fetched.display_name == "ABC Electric"
        assert fetched.entity_type is WorldEntityType.PROVIDER
        assert fetched.created_by_client == "lifeops-console"

    async def test_facts_survive_the_json_property_round_trip(self, world) -> None:
        """Map-valued properties are rejected by NornicDB; facts are a JSON string."""
        repo, make, make_person = world
        entity = await repo.create(
            make(
                WorldEntityType.ASSET,
                "Land Rover",
                insurance="Progressive",
                mileage="114203",
            )
        )

        fetched = await repo.get(entity.id)
        assert fetched is not None
        assert fetched.facts == {"insurance": "Progressive", "mileage": "114203"}

    async def test_an_entity_with_no_facts_reads_back_as_an_empty_bag(
        self, world
    ) -> None:
        repo, make, make_person = world
        entity = await repo.create(make(WorldEntityType.HOUSEHOLD, "Main House"))

        fetched = await repo.get(entity.id)
        assert fetched is not None
        assert fetched.facts == {}

    async def test_exists_reflects_reality(self, world) -> None:
        repo, make, make_person = world
        entity = make(WorldEntityType.PROVIDER, "ABC Electric")
        assert await repo.exists(entity.id) is False
        await repo.create(entity)
        assert await repo.exists(entity.id) is True

    async def test_get_returns_none_for_an_absent_entity(self, world) -> None:
        repo, make, make_person = world
        entity = make(WorldEntityType.ASSET, "Never Created")
        assert await repo.get(entity.id) is None

    async def test_create_is_idempotent_on_id(self, world) -> None:
        """MERGE on id: re-creating updates rather than duplicating the node."""
        repo, make, make_person = world
        entity = make(WorldEntityType.PROVIDER, "ABC Electric", phone="555-0100")
        await repo.create(entity)
        await repo.create(entity.model_copy(update={"facts": {"phone": "555-0199"}}))

        listed = [e for e in await repo.list_entities() if e.id == entity.id]
        assert len(listed) == 1
        assert listed[0].facts == {"phone": "555-0199"}


class TestPreferenceProjection:
    """BUILD_SPEC section 15 draws a Preference node in the World graph.

    The node is written by the preference repository with an entirely
    different property shape — ``key``/``value``/``valid_from``, no
    ``display_name`` and no ``facts_json``. Only this suite proves the world
    repository's projection reads a real one; the fake projects from its own
    model and would stay green through a broken Cypher alias.
    """

    async def test_a_real_preference_node_projects_into_the_graph(
        self, world, nornic_client: NornicClient, test_label: str
    ) -> None:
        repo, _, _ = world
        preferences = NornicPreferenceRepository(nornic_client)
        preference = Preference(
            id=f"preference_{test_label}",
            subject_id=f"person_{test_label}",
            key="scheduling.earliest_appointment_time",
            value="After 10 AM",
            source_type=PreferenceSource.USER_EXPLICIT,
            observed_at=TS,
            created_at=TS,
            valid_from=TS,
            created_by_client="lifeops-console",
        )
        await preferences.save_superseding(preference, supersedes=None)
        try:
            projected = await repo.get(preference.id)
            assert projected is not None
            assert projected.entity_type is WorldEntityType.PREFERENCE
            # Section 15 labels the node with the value, not the key.
            assert projected.display_name == "After 10 AM"
            assert projected.facts["key"] == "scheduling.earliest_appointment_time"
            assert projected.created_by_client == "lifeops-console"

            listed = await repo.list_entities(types=[WorldEntityType.PREFERENCE])
            assert preference.id in {e.id for e in listed}
        finally:
            await nornic_client.write(
                "MATCH (p:Preference {id: $id}) DETACH DELETE p", id=preference.id
            )

    async def test_a_superseded_preference_leaves_the_graph(
        self, world, nornic_client: NornicClient, test_label: str
    ) -> None:
        """Section 15 shows the current world; the old value is history."""
        repo, _, _ = world
        preferences = NornicPreferenceRepository(nornic_client)
        old = Preference(
            id=f"preference_old_{test_label}",
            subject_id=f"person_{test_label}",
            key="scheduling.earliest",
            value="After 10 AM",
            observed_at=TS,
            created_at=TS,
            valid_from=TS,
            valid_to="2026-02-01T00:00:00Z",
        )
        await preferences.save_superseding(old, supersedes=None)
        try:
            assert await repo.get(old.id) is None
            assert await repo.exists(old.id) is False
            listed = await repo.list_entities(types=[WorldEntityType.PREFERENCE])
            assert old.id not in {e.id for e in listed}
        finally:
            await nornic_client.write(
                "MATCH (p:Preference {id: $id}) DETACH DELETE p", id=old.id
            )


class TestRelationships:
    async def test_link_and_read_back(self, world) -> None:
        repo, make, make_person = world
        household = await repo.create(make(WorldEntityType.HOUSEHOLD, "Main House"))
        provider = await repo.create(make(WorldEntityType.PROVIDER, "ABC Electric"))

        await repo.link(
            household.id, provider.id, WorldRelationship.USES_PROVIDER
        )

        edges = await repo.list_edges_for(household.id)
        assert (edges[0].source, edges[0].target, edges[0].type) == (
            household.id,
            provider.id,
            WorldRelationship.USES_PROVIDER,
        )

    async def test_linking_twice_does_not_multiply_the_edge(self, world) -> None:
        repo, make, make_person = world
        household = await repo.create(make(WorldEntityType.HOUSEHOLD, "Main House"))
        provider = await repo.create(make(WorldEntityType.PROVIDER, "ABC Electric"))

        await repo.link(household.id, provider.id, WorldRelationship.USES_PROVIDER)
        await repo.link(household.id, provider.id, WorldRelationship.USES_PROVIDER)

        assert len(await repo.list_edges_for(household.id)) == 1

    async def test_edges_are_found_from_either_endpoint(self, world) -> None:
        """Two directed queries, not one undirected match (see module docstring)."""
        repo, make, make_person = world
        household = await repo.create(make(WorldEntityType.HOUSEHOLD, "Main House"))
        provider = await repo.create(make(WorldEntityType.PROVIDER, "ABC Electric"))
        await repo.link(household.id, provider.id, WorldRelationship.USES_PROVIDER)

        from_source = await repo.list_edges_for(household.id)
        from_target = await repo.list_edges_for(provider.id)
        assert from_source == from_target
        assert len(from_target) == 1

    async def test_unlink_removes_only_that_edge(self, world) -> None:
        repo, make, make_person = world
        household = await repo.create(make(WorldEntityType.HOUSEHOLD, "Main House"))
        asset = await repo.create(make(WorldEntityType.ASSET, "Land Rover"))

        await repo.link(household.id, asset.id, WorldRelationship.OWNS)
        await repo.link(household.id, asset.id, WorldRelationship.RELATED_TO)

        assert await repo.unlink(household.id, asset.id, WorldRelationship.OWNS) is True

        remaining = await repo.list_edges_for(household.id)
        assert [e.type for e in remaining] == [WorldRelationship.RELATED_TO]

    async def test_unlinking_an_absent_edge_reports_false(self, world) -> None:
        repo, make, make_person = world
        household = await repo.create(make(WorldEntityType.HOUSEHOLD, "Main House"))
        asset = await repo.create(make(WorldEntityType.ASSET, "Land Rover"))

        assert await repo.unlink(household.id, asset.id, WorldRelationship.OWNS) is False

    async def test_rel_type_filter_narrows_edges(self, world) -> None:
        repo, make, make_person = world
        household = await repo.create(make(WorldEntityType.HOUSEHOLD, "Main House"))
        asset = await repo.create(make(WorldEntityType.ASSET, "Land Rover"))
        await repo.link(household.id, asset.id, WorldRelationship.OWNS)
        await repo.link(household.id, asset.id, WorldRelationship.RELATED_TO)

        edges = await repo.list_edges_for(
            household.id, rel_types=[WorldRelationship.OWNS]
        )
        assert [e.type for e in edges] == [WorldRelationship.OWNS]


class TestNeighborhood:
    async def test_depth_one_stops_at_direct_neighbours(self, world) -> None:
        repo, make, make_person = world
        person = await make_person("Neighbour Walker")
        household = await repo.create(make(WorldEntityType.HOUSEHOLD, "Main House"))
        provider = await repo.create(make(WorldEntityType.PROVIDER, "ABC Electric"))
        await repo.link(person.id, household.id, WorldRelationship.MEMBER_OF)
        await repo.link(household.id, provider.id, WorldRelationship.USES_PROVIDER)

        entities, _ = await repo.neighborhood(person.id, depth=1)
        assert {e.id for e in entities} == {person.id, household.id}

    async def test_depth_two_reaches_the_second_hop(self, world) -> None:
        repo, make, make_person = world
        person = await make_person("Neighbour Walker")
        household = await repo.create(make(WorldEntityType.HOUSEHOLD, "Main House"))
        provider = await repo.create(make(WorldEntityType.PROVIDER, "ABC Electric"))
        await repo.link(person.id, household.id, WorldRelationship.MEMBER_OF)
        await repo.link(household.id, provider.id, WorldRelationship.USES_PROVIDER)

        entities, edges = await repo.neighborhood(person.id, depth=2)
        assert {e.id for e in entities} == {person.id, household.id, provider.id}
        assert len(edges) == 2

    async def test_the_walk_crosses_edges_against_their_direction(self, world) -> None:
        """A household must find its members even though MEMBER_OF points inward."""
        repo, make, make_person = world
        person = await make_person("Neighbour Walker")
        household = await repo.create(make(WorldEntityType.HOUSEHOLD, "Main House"))
        await repo.link(person.id, household.id, WorldRelationship.MEMBER_OF)

        entities, _ = await repo.neighborhood(household.id, depth=1)
        assert {e.id for e in entities} == {person.id, household.id}

    async def test_a_cycle_terminates(self, world) -> None:
        """The walk must not revisit entities it has already reached."""
        repo, make, make_person = world
        a = await repo.create(make(WorldEntityType.ASSET, "Cycle A"))
        b = await repo.create(make(WorldEntityType.ASSET, "Cycle B"))
        await repo.link(a.id, b.id, WorldRelationship.RELATED_TO)
        await repo.link(b.id, a.id, WorldRelationship.RELATED_TO)

        entities, edges = await repo.neighborhood(a.id, depth=3)
        assert {e.id for e in entities} == {a.id, b.id}
        assert len(edges) == 2

    async def test_an_unknown_entity_yields_nothing(self, world) -> None:
        repo, make, make_person = world
        absent = make(WorldEntityType.ASSET, "Never Created")
        assert await repo.neighborhood(absent.id, depth=1) == ([], [])

    async def test_an_edge_to_a_non_world_node_does_not_break_the_walk(
        self, world, nornic_client: NornicClient, test_label: str
    ) -> None:
        """The tasks repository writes `(:Task)-[:ABOUT]->(entity)`.

        Those edges are in the database whether the world layer wants them or
        not, and a Task has no world label to resolve. Only this suite proves
        the walk survives one: the fake would need the same bug to fail.
        """
        repo, make, make_person = world
        asset = await repo.create(make(WorldEntityType.ASSET, "Land Rover"))
        task_id = f"task_{test_label}"
        await nornic_client.write(
            "CREATE (t:Task {id: $task_id, title: $title})",
            task_id=task_id,
            title="Oil change",
        )
        try:
            await nornic_client.write(
                "MATCH (t:Task {id: $task_id}) MATCH (a {id: $asset_id}) "
                "MERGE (t)-[:ABOUT]->(a)",
                task_id=task_id,
                asset_id=asset.id,
            )

            edges = await repo.list_edges_for(asset.id)
            assert (task_id, asset.id, WorldRelationship.ABOUT) in {
                (e.source, e.target, e.type) for e in edges
            }

            # The walk must not try to resolve a label for the Task.
            entities, _ = await repo.neighborhood(asset.id, depth=2)
            assert [e.id for e in entities] == [asset.id]
        finally:
            await nornic_client.write(
                "MATCH (t:Task {id: $task_id}) DETACH DELETE t", task_id=task_id
            )

    async def test_an_isolated_entity_returns_only_itself(self, world) -> None:
        repo, make, make_person = world
        lonely = await repo.create(make(WorldEntityType.ASSET, "Lonely Asset"))

        entities, edges = await repo.neighborhood(lonely.id, depth=2)
        assert [e.id for e in entities] == [lonely.id]
        assert edges == []


class TestListing:
    async def test_type_filter_selects_by_label(self, world) -> None:
        repo, make, make_person = world
        provider = await repo.create(make(WorldEntityType.PROVIDER, "ABC Electric"))
        asset = await repo.create(make(WorldEntityType.ASSET, "Land Rover"))

        listed = {
            e.id
            for e in await repo.list_entities(types=[WorldEntityType.PROVIDER])
        }
        assert provider.id in listed
        assert asset.id not in listed

    async def test_listing_spans_every_world_label(self, world) -> None:
        repo, make, make_person = world
        ids = {(await make_person("Span Person")).id}
        for entity_type, name in (
            (WorldEntityType.HOUSEHOLD, "Span House"),
            (WorldEntityType.PROVIDER, "Span Provider"),
            (WorldEntityType.ASSET, "Span Asset"),
        ):
            ids.add((await repo.create(make(entity_type, name))).id)

        listed = {e.id for e in await repo.list_entities(limit=2000)}
        assert ids <= listed


@pytest.fixture
async def phase7_cleanup(nornic_client: NornicClient):
    """Phase 7 entities are built directly, not through ``world``'s ``make``
    helper (they are outside ``CREATABLE_ENTITY_TYPES``), so they need their
    own teardown list rather than riding on that fixture's."""
    created: list[str] = []
    try:
        yield created
    finally:
        for entity_id in created:
            await nornic_client.write(
                "MATCH (n {id: $id}) DETACH DELETE n", id=entity_id
            )


class TestPhase7EntityRoundTrip:
    """Appointment, CalendarEvent, and Document (BUILD_SPEC sections 63, 64,
    96) are projected through the same world repository as Household/
    Provider/Asset, but they are built with the domain conversion helpers
    rather than ``EntityDraft`` — they are outside ``CREATABLE_ENTITY_TYPES``
    on purpose (domain/world.py). This proves the wider
    ``WORLD_MANAGED_ENTITY_TYPES`` guard actually lets NornicDB accept them,
    and that every fact the domain model needs survives the JSON round trip.
    """

    async def test_an_appointment_round_trips_through_its_facts(
        self, world, phase7_cleanup: list[str], test_label: str
    ) -> None:
        from lifeops.domain.calendar import (
            Appointment,
            AppointmentStatus,
            appointment_to_entity,
            entity_to_appointment,
        )

        repo, _, _ = world
        appointment = Appointment(
            id=f"appointment_{test_label}",
            subject="Furnace tune-up",
            status=AppointmentStatus.HELD,
            provider_entity_id=f"provider_hvac_{test_label}",
            task_id=f"task_{test_label}",
            start_at="2026-03-01T14:00:00Z",
            end_at="2026-03-01T15:00:00Z",
            location="Home",
            notes="Front door code is on file",
            hold_reference="hold-abc-123",
            hold_expires_at="2026-03-01T13:30:00Z",
            created_at=TS,
            updated_at=TS,
            created_by_client="hermes-personal",
        )
        phase7_cleanup.append(appointment.id)

        created = await repo.create(appointment_to_entity(appointment))
        assert created.id == appointment.id

        fetched = await repo.get(appointment.id)
        assert fetched is not None
        roundtripped = entity_to_appointment(fetched)
        assert roundtripped.subject == appointment.subject
        assert roundtripped.status is AppointmentStatus.HELD
        assert roundtripped.provider_entity_id == appointment.provider_entity_id
        assert roundtripped.start_at == appointment.start_at
        assert roundtripped.end_at == appointment.end_at
        assert roundtripped.hold_reference == appointment.hold_reference
        assert roundtripped.external_event_id is None

    async def test_rewriting_an_appointment_updates_rather_than_duplicates(
        self, world, phase7_cleanup: list[str], test_label: str
    ) -> None:
        """The booking flow re-persists the same id after confirm_booking
        (core.py's ``mark_booked``); MERGE must update it in place."""
        from lifeops.domain.calendar import (
            Appointment,
            AppointmentStatus,
            appointment_to_entity,
            confirm_booking,
            entity_to_appointment,
        )

        repo, _, _ = world
        appointment = Appointment(
            id=f"appointment_{test_label}",
            subject="Furnace tune-up",
            start_at="2026-03-01T14:00:00Z",
            end_at="2026-03-01T15:00:00Z",
            hold_expires_at="2099-01-01T00:00:00Z",
            created_at=TS,
            updated_at=TS,
        )
        phase7_cleanup.append(appointment.id)
        await repo.create(appointment_to_entity(appointment))

        booked = confirm_booking(
            appointment,
            external_event_id="ext-evt-1",
            action_id=f"action_{test_label}",
            now="2026-03-01T09:00:00Z",
        )
        await repo.create(appointment_to_entity(booked))

        listed = [e for e in await repo.list_entities() if e.id == appointment.id]
        assert len(listed) == 1
        roundtripped = entity_to_appointment(listed[0])
        assert roundtripped.status is AppointmentStatus.BOOKED
        assert roundtripped.external_event_id == "ext-evt-1"

    async def test_a_calendar_event_round_trips(
        self, world, phase7_cleanup: list[str], test_label: str
    ) -> None:
        from lifeops.domain.calendar import (
            CalendarEvent,
            calendar_event_to_entity,
            entity_to_calendar_event,
        )

        repo, _, _ = world
        event = CalendarEvent(
            id=CalendarEvent.make_id("fake", f"ext-{test_label}"),
            external_event_id=f"ext-{test_label}",
            calendar_provider_id="fake",
            title="Dentist",
            start_at="2026-04-01T10:00:00Z",
            end_at="2026-04-01T10:30:00Z",
            location="Suite 4",
        )
        phase7_cleanup.append(event.id)

        await repo.create(calendar_event_to_entity(event, now=TS))
        fetched = await repo.get(event.id)
        assert fetched is not None
        roundtripped = entity_to_calendar_event(fetched)
        assert roundtripped.title == "Dentist"
        assert roundtripped.external_event_id == event.external_event_id
        assert roundtripped.start_at == event.start_at

    async def test_a_document_round_trips(
        self, world, phase7_cleanup: list[str], test_label: str
    ) -> None:
        from lifeops.domain.documents import (
            Document,
            document_to_entity,
            entity_to_document,
        )

        repo, _, _ = world
        document = Document(
            id=f"document_{test_label}",
            title="ABC Electric quote",
            source="email",
            source_ref="msg-123",
            mime_type="message/rfc822",
            summary="Quote for panel upgrade: $2,400",
            created_at=TS,
            updated_at=TS,
            created_by_client="hermes-personal",
        )
        phase7_cleanup.append(document.id)

        await repo.create(document_to_entity(document))
        fetched = await repo.get(document.id)
        assert fetched is not None
        roundtripped = entity_to_document(fetched)
        assert roundtripped.title == document.title
        assert roundtripped.source == "email"
        assert roundtripped.source_ref == "msg-123"
        assert roundtripped.summary == document.summary

    async def test_phase7_types_are_included_in_a_full_listing(
        self, world, phase7_cleanup: list[str], test_label: str
    ) -> None:
        from lifeops.domain.documents import Document, document_to_entity

        repo, _, _ = world
        document = Document(
            id=f"document_{test_label}",
            title="Listing check",
            source="manual",
            created_at=TS,
            updated_at=TS,
        )
        phase7_cleanup.append(document.id)
        await repo.create(document_to_entity(document))

        listed = {e.id for e in await repo.list_entities(limit=2000)}
        assert document.id in listed


class TestFactHistory:
    """Per-fact supersession (section 16), against real NornicDB Cypher —
    the fakes prove the domain rule (only a changed value gets a new
    version); only this suite proves the transaction actually closes the old
    version and opens the new one together, the same discipline
    ``NornicPreferenceRepository.save_superseding`` already has.

    ``EntityFact`` nodes are not entities the ``world`` fixture's own
    teardown knows about, so every test tracks its fact ids on
    ``phase7_cleanup`` (its cleanup behaviour is not phase-specific — see
    that fixture's own docstring).
    """

    async def test_seeding_writes_the_first_version_of_each_fact(
        self, world, phase7_cleanup: list[str], test_label: str
    ) -> None:
        from lifeops.domain.world import EntityFact

        repo, make, _ = world
        entity = await repo.create(
            make(WorldEntityType.PROVIDER, "ABC Electric", phone="555-0100")
        )
        version = EntityFact(
            id=EntityFact.make_id(),
            entity_id=entity.id,
            key="phone",
            value="555-0100",
            valid_from=TS,
            created_by_client="lifeops-console",
        )
        phase7_cleanup.append(version.id)
        await repo.seed_fact_versions([version])

        current = await repo.current_facts(entity.id)
        assert current["phone"].id == version.id
        assert current["phone"].value == "555-0100"
        assert current["phone"].supersedes is None

        history = await repo.fact_history(entity.id, key="phone")
        assert [f.id for f in history] == [version.id]

    async def test_update_facts_closes_the_old_version_and_opens_the_new_one(
        self, world, phase7_cleanup: list[str], test_label: str
    ) -> None:
        from lifeops.domain.world import EntityFact

        repo, make, _ = world
        entity = await repo.create(
            make(WorldEntityType.PROVIDER, "ABC Electric", phone="555-0100")
        )
        old_version = EntityFact(
            id=EntityFact.make_id(),
            entity_id=entity.id,
            key="phone",
            value="555-0100",
            valid_from=TS,
            created_by_client="lifeops-console",
        )
        phase7_cleanup.append(old_version.id)
        await repo.seed_fact_versions([old_version])

        later = "2026-02-01T00:00:00Z"
        new_version = EntityFact(
            id=EntityFact.make_id(),
            entity_id=entity.id,
            key="phone",
            value="555-9999",
            valid_from=later,
            supersedes=old_version.id,
            created_by_client="lifeops-console",
        )
        phase7_cleanup.append(new_version.id)
        updated_entity = entity.model_copy(
            update={"facts": {"phone": "555-9999"}, "updated_at": later}
        )
        saved = await repo.update_facts(
            updated_entity, new_versions=[new_version], superseded_ids=[old_version.id]
        )

        # The entity's own current-state property changed...
        assert saved.facts == {"phone": "555-9999"}
        fetched = await repo.get(entity.id)
        assert fetched is not None
        assert fetched.facts == {"phone": "555-9999"}

        # ...and the version history agrees: exactly one current version,
        # the old one closed at the moment the new one opened.
        current = await repo.current_facts(entity.id)
        assert current["phone"].id == new_version.id

        history = await repo.fact_history(entity.id, key="phone")
        assert [f.id for f in history] == [new_version.id, old_version.id]
        closed = next(f for f in history if f.id == old_version.id)
        assert closed.valid_to == later

    async def test_fact_history_without_a_key_returns_every_fact(
        self, world, phase7_cleanup: list[str], test_label: str
    ) -> None:
        from lifeops.domain.world import EntityFact

        repo, make, _ = world
        entity = await repo.create(
            make(
                WorldEntityType.ASSET, "Land Rover", mileage="114203", insurance="Progressive"
            )
        )
        mileage_version = EntityFact(
            id=EntityFact.make_id(),
            entity_id=entity.id,
            key="mileage",
            value="114203",
            valid_from=TS,
        )
        insurance_version = EntityFact(
            id=EntityFact.make_id(),
            entity_id=entity.id,
            key="insurance",
            value="Progressive",
            valid_from=TS,
        )
        phase7_cleanup.extend([mileage_version.id, insurance_version.id])
        await repo.seed_fact_versions([mileage_version, insurance_version])

        history = await repo.fact_history(entity.id)
        assert {f.key for f in history} == {"mileage", "insurance"}

    async def test_current_facts_excludes_superseded_versions(
        self, world, phase7_cleanup: list[str], test_label: str
    ) -> None:
        from lifeops.domain.world import EntityFact

        repo, make, _ = world
        entity = await repo.create(
            make(WorldEntityType.ASSET, "Land Rover", mileage="100000")
        )
        old_version = EntityFact(
            id=EntityFact.make_id(),
            entity_id=entity.id,
            key="mileage",
            value="100000",
            valid_from=TS,
        )
        phase7_cleanup.append(old_version.id)
        await repo.seed_fact_versions([old_version])

        later = "2026-03-01T00:00:00Z"
        new_version = EntityFact(
            id=EntityFact.make_id(),
            entity_id=entity.id,
            key="mileage",
            value="108900",
            valid_from=later,
            supersedes=old_version.id,
        )
        phase7_cleanup.append(new_version.id)
        updated_entity = entity.model_copy(
            update={"facts": {"mileage": "108900"}, "updated_at": later}
        )
        await repo.update_facts(
            updated_entity, new_versions=[new_version], superseded_ids=[old_version.id]
        )

        current = await repo.current_facts(entity.id)
        assert len(current) == 1
        assert current["mileage"].value == "108900"


class TestKnowledgeEntityRoundTrip:
    """Knowledge (BUILD_SPEC sections 18, 36), projected the same way
    Document is — outside ``CREATABLE_ENTITY_TYPES``, written through its own
    draft rather than the generic entity path. Reuses ``phase7_cleanup``: its
    teardown behaviour is not phase-specific.
    """

    async def test_a_knowledge_entity_round_trips(
        self, world, phase7_cleanup: list[str], test_label: str
    ) -> None:
        from lifeops.domain.knowledge import (
            Knowledge,
            entity_to_knowledge,
            knowledge_to_entity,
        )

        repo, _, _ = world
        knowledge = Knowledge(
            id=f"knowledge_{test_label}",
            title="Water heater warranty",
            category="warranty",
            content="10-year tank warranty, registered 2024-03-01.",
            source_document_id="document_9",
            created_at=TS,
            updated_at=TS,
            created_by_client="console",
        )
        phase7_cleanup.append(knowledge.id)

        await repo.create(knowledge_to_entity(knowledge))
        fetched = await repo.get(knowledge.id)
        assert fetched is not None
        roundtripped = entity_to_knowledge(fetched)
        assert roundtripped.title == knowledge.title
        assert roundtripped.category == "warranty"
        assert roundtripped.content == knowledge.content
        assert roundtripped.source_document_id == "document_9"

    async def test_knowledge_is_included_in_a_full_listing(
        self, world, phase7_cleanup: list[str], test_label: str
    ) -> None:
        from lifeops.domain.knowledge import Knowledge, knowledge_to_entity

        repo, _, _ = world
        knowledge = Knowledge(
            id=f"knowledge_{test_label}",
            title="Listing check",
            created_at=TS,
            updated_at=TS,
        )
        phase7_cleanup.append(knowledge.id)
        await repo.create(knowledge_to_entity(knowledge))

        listed = {e.id for e in await repo.list_entities(limit=2000)}
        assert knowledge.id in listed


class TestStorageMovedOutOfTheFactsBag:
    """ShoppingList and ServiceRequest no longer round-trip through the world
    repository, and there is deliberately no test here that they do.

    Both once stored their whole record in a ``facts_json`` blob on a world
    node — a shopping cart's items JSON-encoded into one string, an
    availability list joined with semicolons. Both now have their own
    repositories with real item nodes and real list properties, so the
    round-trip those old tests asserted is a path production abandoned.

    What still matters is that they *render* on the World screen, which
    ``TestProjectedRecordsRenderOnTheGraph`` covers against the real
    repositories.
    """


class TestProjectedRecordsRenderOnTheGraph:
    """Entities that own their storage still have to draw (section 15).

    Shopping lists and service requests moved out of the world's facts-bag
    shape into their own repositories. Their nodes therefore carry no
    ``display_name`` and no ``facts_json`` — and the World screen kept reading
    exactly those, so a real list rendered as its raw id with no facts. The
    graph reads the fields these records actually have.
    """

    async def test_a_shopping_list_shows_its_title_and_status(
        self, world, nornic_client: NornicClient, test_label: str
    ) -> None:
        from lifeops.domain.shopping import ShoppingItem, ShoppingList
        from lifeops.repositories.nornic.shopping import NornicShoppingRepository

        repo, _, _ = world
        shopping = NornicShoppingRepository(nornic_client)
        listing = ShoppingList(
            id=f"shoppinglist_{test_label}",
            title="Weekly groceries",
            store="Kroger",
            items=[ShoppingItem(name="Milk")],
            created_at=TS,
            updated_at=TS,
        )
        await shopping.upsert(listing)
        try:
            found = [
                e
                for e in await repo.list_entities(
                    types=[WorldEntityType.SHOPPING_LIST], limit=500
                )
                if e.id == listing.id
            ]
            assert found, "the shopping list did not appear on the graph at all"
            assert found[0].display_name == "Weekly groceries"
            assert found[0].facts["status"] == "draft"
            assert found[0].facts["store"] == "Kroger"
        finally:
            await nornic_client.write(
                "MATCH (s:ShoppingList {id: $id}) "
                "OPTIONAL MATCH (s)-[:CONTAINS]->(i:ShoppingItem) DETACH DELETE s, i",
                id=listing.id,
            )

    async def test_a_service_request_shows_its_subject(
        self, world, nornic_client: NornicClient, test_label: str
    ) -> None:
        from lifeops.domain.service_request import ServiceRequest
        from lifeops.repositories.nornic.service_requests import (
            NornicServiceRequestRepository,
        )

        repo, _, _ = world
        requests = NornicServiceRequestRepository(nornic_client)
        request = ServiceRequest(
            id=f"servicerequest_{test_label}",
            subject="Outlet behind the TV",
            provider_entity_id="provider_abc_electric",
            created_at=TS,
            updated_at=TS,
        )
        await requests.upsert(request)
        try:
            found = [
                e
                for e in await repo.list_entities(
                    types=[WorldEntityType.SERVICE_REQUEST], limit=500
                )
                if e.id == request.id
            ]
            assert found, "the service request did not appear on the graph at all"
            assert found[0].display_name == "Outlet behind the TV"
            assert found[0].facts["provider"] == "provider_abc_electric"
        finally:
            await nornic_client.write(
                "MATCH (r:ServiceRequest {id: $id}) DETACH DELETE r", id=request.id
            )
