"""BUILD_SPEC section 86 scenario 6: duplicate MCP request.

Real subprocess, real NornicDB — the same discipline
``test_phase0_exit.py`` uses, and this file reuses its ``mcp_session``/
``_call``/``_payload`` helpers directly rather than redefining them.

Most of the narrow ``write_world`` MCP surface (``record_provider``,
``record_asset``) has no natural "same request twice" contract — calling
``record_provider`` twice legitimately records two providers, by design
(the tool's own description tells the caller to check ``get_provider``
first; LifeOps does not dedup on its behalf). ``place_phone_call`` is
different: it goes through the action outbox's idempotency-key mechanism
(``core.py``'s ``request_provider_call`` -> ``prepare_action``), the same
path ``book_appointment`` and every other consequential-action tool uses.
This is the one MCP write where "duplicate request must not double the
external commitment" is actually a contract to test — and, until now,
nothing exercised it at the real transport layer, only at ``core.py``
directly (``tests/unit/test_bills.py`` and friends) or as a raw NornicDB
constraint (``tests/persistence/test_nornic_durable_work.py``).

Cleanup is explicit per test (delete exactly the ids this test created),
not a generic autouse purge — a content-matching ``DETACH DELETE`` against
an ``Action`` node's ``payload`` risks silently matching nothing (or too
much) depending on how it happens to be serialised, which would make the
test suite dirty the shared dev database without ever failing loudly.
"""

from __future__ import annotations

import pytest

from tests.e2e.test_phase0_exit import _call, mcp_session

pytestmark = [pytest.mark.integration, pytest.mark.persistence]

HERMES = "hermes-personal"
SUBJECT = "Chaos scenario 6 duplicate-request test"
PROVIDER_NAME = "Chaos Scenario 6 Test Provider"


@pytest.fixture(scope="module", autouse=True)
def require_nornic() -> None:
    import os
    import socket

    uri = os.environ.get("LIFEOPS_NORNIC_URI", "bolt://127.0.0.1:7687")
    host, _, port = uri.rsplit("/", 1)[-1].partition(":")
    try:
        with socket.create_connection((host, int(port or 7687)), timeout=3):
            pass
    except OSError:
        pytest.skip(f"NornicDB is not reachable at {uri}")


async def _delete_by_id(labels_and_ids: list[tuple[str, str]]) -> None:
    from lifeops.repositories.nornic.client import NornicClient
    from lifeops.settings import Settings

    client = NornicClient(Settings())
    await client.connect()
    try:
        for label, node_id in labels_and_ids:
            await client.write(
                f"MATCH (n:{label} {{id: $id}}) DETACH DELETE n", id=node_id
            )
    finally:
        await client.close()


class TestDuplicateMcpRequest:
    async def test_two_identical_place_phone_call_requests_yield_one_action(
        self,
    ) -> None:
        created: list[tuple[str, str]] = []
        try:
            async with mcp_session(HERMES) as session:
                service_request = await _call(
                    session, "create_service_request", subject=SUBJECT
                )
                assert service_request["ok"] is True
                service_request_id = service_request["service_request"]["id"]
                created.append(("ServiceRequest", service_request_id))

                provider = await _call(
                    session,
                    "record_provider",
                    display_name=PROVIDER_NAME,
                    # place_phone_call refuses a provider with no number on
                    # file: LifeOps resolves a real destination rather than
                    # dialling a placeholder. The scenario under test is
                    # duplicate *requests*, so the provider has to be dialable
                    # for the test to reach the idempotency path at all.
                    facts={"phone": "+15555550100"},
                )
                assert provider["ok"] is True
                provider_entity_id = provider["provider"]["id"]
                created.append(("Provider", provider_entity_id))

                call_args = dict(
                    service_request_id=service_request_id,
                    provider_entity_id=provider_entity_id,
                    objective="chaos_scenario_6",
                    collect=["availability"],
                )

                first = await _call(session, "place_phone_call", **call_args)
                second = await _call(session, "place_phone_call", **call_args)

            assert first["ok"] is True
            assert second["ok"] is True
            created.append(("Action", first["action"]["id"]))
            if second["action"]["id"] != first["action"]["id"]:
                created.append(("Action", second["action"]["id"]))

            # Identical objective, same service request, same provider -> the
            # same payload -> the same idempotency key. The second request
            # must return the action prepare() already created, not a second
            # one.
            assert first["action"]["id"] == second["action"]["id"]
        finally:
            await _delete_by_id(created)

    async def test_two_requests_across_separate_sessions_still_dedup(
        self,
    ) -> None:
        """The dedup is durable (NornicDB's idempotency-key constraint), not
        an in-process cache — this proves it survives the MCP client
        actually disconnecting and reconnecting between the two requests,
        the way a real Hermes retry after a dropped connection would."""
        created: list[tuple[str, str]] = []
        try:
            async with mcp_session(HERMES) as session:
                service_request = await _call(
                    session, "create_service_request", subject=SUBJECT
                )
                service_request_id = service_request["service_request"]["id"]
                created.append(("ServiceRequest", service_request_id))

                provider = await _call(
                    session,
                    "record_provider",
                    display_name=PROVIDER_NAME,
                    # place_phone_call refuses a provider with no number on
                    # file: LifeOps resolves a real destination rather than
                    # dialling a placeholder. The scenario under test is
                    # duplicate *requests*, so the provider has to be dialable
                    # for the test to reach the idempotency path at all.
                    facts={"phone": "+15555550100"},
                )
                provider_entity_id = provider["provider"]["id"]
                created.append(("Provider", provider_entity_id))

                call_args = dict(
                    service_request_id=service_request_id,
                    provider_entity_id=provider_entity_id,
                    objective="chaos_scenario_6_cross_session",
                    collect=["availability"],
                )
                first = await _call(session, "place_phone_call", **call_args)

            async with mcp_session(HERMES) as session:
                second = await _call(session, "place_phone_call", **call_args)

            assert first["ok"] is True
            assert second["ok"] is True
            created.append(("Action", first["action"]["id"]))
            if second["action"]["id"] != first["action"]["id"]:
                created.append(("Action", second["action"]["id"]))
            assert first["action"]["id"] == second["action"]["id"]
        finally:
            await _delete_by_id(created)
