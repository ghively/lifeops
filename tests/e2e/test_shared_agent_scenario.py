"""BUILD_SPEC section 102 — the Shared-Agent Acceptance Scenario.

    Hermes:      Remember I prefer appointments after ten.
    Claude Code: What are the current scheduling preferences?
    Expected:    Appointments after 10 AM.
    Claude Code: Create a task to call the dentist.
    Hermes:      What tasks are open?
    Expected:    Call dentist.

Section 102 states what this proves: *"state belongs to LifeOps."*

Every session below is a real MCP subprocess speaking the real protocol, and
the two identities are genuinely different clients with different capability
grants. Nothing is shared between them except NornicDB — which is the point.
If this passed because state sat in a Python object, the architecture would be
wrong and the test would still be green.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from tests.e2e.test_phase0_exit import _call, mcp_session

pytestmark = [pytest.mark.integration, pytest.mark.persistence]

HERMES = "hermes-personal"
CODING_CLIENT = "claude-code"

PREFERENCE_KEY = "scheduling.earliest_appointment_time"
PREFERENCE_VALUE = "Appointments after 10 AM."
TASK_TITLE = "Call dentist"


@pytest.fixture(autouse=True)
async def clean_state() -> AsyncIterator[None]:
    from lifeops.repositories.nornic.client import NornicClient
    from lifeops.settings import Settings

    async def purge() -> None:
        client = NornicClient(Settings())
        await client.connect()
        try:
            await client.write(
                "MATCH (p:Preference) WHERE p.key = $key DETACH DELETE p",
                key=PREFERENCE_KEY,
            )
            await client.write(
                "MATCH (t:Task) WHERE t.title = $title DETACH DELETE t",
                title=TASK_TITLE,
            )
        finally:
            await client.close()

    await purge()
    yield
    await purge()


class TestSharedAgentScenario:
    async def test_state_belongs_to_lifeops_not_to_an_agent(self) -> None:
        # Hermes: "Remember I prefer appointments after ten."
        async with mcp_session(HERMES) as session:
            saved = await _call(
                session,
                "save_preference",
                key=PREFERENCE_KEY,
                value=PREFERENCE_VALUE,
                source_type="user_explicit",
            )
            assert saved["ok"] is True, saved

        # Claude Code: "What are the current scheduling preferences?"
        # A different identity, a different process, the same state.
        async with mcp_session(CODING_CLIENT) as session:
            result = await _call(session, "get_preferences", key_prefix="scheduling")
        values = {p["key"]: p["value"] for p in result["preferences"]}
        assert values[PREFERENCE_KEY] == PREFERENCE_VALUE

        # Claude Code: "Create a task to call the dentist."
        async with mcp_session(CODING_CLIENT) as session:
            created = await _call(session, "create_task", title=TASK_TITLE)
            assert created["ok"] is True, created

        # Hermes: "What tasks are open?"
        async with mcp_session(HERMES) as session:
            tasks = await _call(session, "list_tasks")
        assert TASK_TITLE in {t["title"] for t in tasks["tasks"]}

    async def test_the_two_clients_are_genuinely_different_identities(self) -> None:
        """The scenario would prove nothing if both sessions were the same
        client wearing two names — section 34 binds identity per connection,
        and the grants differ."""
        from lifeops.policy import resolve_client
        from lifeops.policy.capabilities import Capability

        hermes = resolve_client(HERMES)
        coder = resolve_client(CODING_CLIENT)

        assert hermes.client_id != coder.client_id
        # The coding agent's job is the repository, not the user's life.
        assert hermes.has(Capability.WRITE_PREFERENCE)
        assert not coder.has(Capability.WRITE_PREFERENCE)
        assert not coder.has(Capability.BOOK_APPOINTMENT)
        assert not coder.has(Capability.FINANCIAL_PAYMENT)

    async def test_a_coding_agent_cannot_rewrite_a_stated_preference(self) -> None:
        """It can read the user's world and file a task; it cannot restate
        what the user prefers."""
        async with mcp_session(HERMES) as session:
            await _call(
                session, "save_preference", key=PREFERENCE_KEY, value=PREFERENCE_VALUE
            )

        async with mcp_session(CODING_CLIENT) as session:
            denied = await _call(
                session,
                "save_preference",
                key=PREFERENCE_KEY,
                value="Appointments any time.",
            )
        assert denied["ok"] is False
        assert denied["error"] == "capability_denied"

        async with mcp_session(HERMES) as session:
            result = await _call(session, "get_preferences", key_prefix="scheduling")
        values = {p["key"]: p["value"] for p in result["preferences"]}
        assert values[PREFERENCE_KEY] == PREFERENCE_VALUE
