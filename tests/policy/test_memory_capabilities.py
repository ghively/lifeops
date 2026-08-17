"""Memory capability policy (BUILD_SPEC sections 34, 35, 44, 91).

The grant shape mirrors the rest of the manifest: the Console and the primary
assistant read and write memory; the engineering assistant reads only, because
its job is the repository, not the user's recollections.
"""

from __future__ import annotations

import pytest

from lifeops.clock import FrozenClock
from lifeops.core import LifeOpsCore
from lifeops.domain.memory import MemoryDraft
from lifeops.domain.people import Person
from lifeops.errors import CapabilityDeniedError, SafeModeError
from lifeops.policy import (
    CODING_CLIENT,
    CONSOLE,
    HERMES,
    INTERACTIVE_CLIENT,
    Capability,
    require,
)
from lifeops.policy.capabilities import SAFE_MODE_BLOCKED
from lifeops.repositories.fakes import (
    FakeMemoryRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
)


@pytest.fixture
async def core() -> LifeOpsCore:
    people = FakePersonRepository()
    await people.upsert(
        Person(
            id="person_policy_user",
            display_name="Policy User",
            is_primary=True,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
    )
    return LifeOpsCore(
        people=people,
        preferences=FakePreferenceRepository(),
        tasks=FakeTaskRepository(),
        memory=FakeMemoryRepository(),
        clock=FrozenClock(),
    )


class TestMemoryGrantShape:
    def test_console_and_primary_assistant_read_and_write(self) -> None:
        for client in (CONSOLE, HERMES):
            assert client.has(Capability.READ_MEMORY), client.client_id
            assert client.has(Capability.WRITE_MEMORY), client.client_id

    def test_engineering_assistant_reads_but_never_writes(self) -> None:
        assert CODING_CLIENT.has(Capability.READ_MEMORY)
        assert not CODING_CLIENT.has(Capability.WRITE_MEMORY)

    def test_other_interactive_clients_read_but_never_write(self) -> None:
        # Durable recollection of the user's life is the primary assistant's
        # job; a third-party chat surface may recall, not record.
        assert INTERACTIVE_CLIENT.has(Capability.READ_MEMORY)
        assert not INTERACTIVE_CLIENT.has(Capability.WRITE_MEMORY)

    def test_memory_is_not_safe_mode_blocked(self) -> None:
        # Memory is local and reversible (R0/R1); an emergency stop must not
        # blind the assistant (section 83 keeps reads and local state live).
        assert Capability.READ_MEMORY not in SAFE_MODE_BLOCKED
        assert Capability.WRITE_MEMORY not in SAFE_MODE_BLOCKED
        require(HERMES, Capability.WRITE_MEMORY, safe_mode=True)

    def test_safe_mode_still_blocks_external_capabilities(self) -> None:
        with pytest.raises(SafeModeError):
            require(HERMES, Capability.SEND_EXTERNAL_MESSAGE, safe_mode=True)


class TestEnforcementThroughCore:
    async def test_engineering_assistant_may_recall(
        self, core: LifeOpsCore
    ) -> None:
        saved = await core.remember(
            HERMES, MemoryDraft(content="the build server lives in the basement rack")
        )
        recalled = await core.recall(CODING_CLIENT, query="build server")
        assert [m.id for m in recalled] == [saved.id]

    async def test_engineering_assistant_may_not_remember(
        self, core: LifeOpsCore
    ) -> None:
        with pytest.raises(CapabilityDeniedError) as exc:
            await core.remember(
                CODING_CLIENT, MemoryDraft(content="a fact the coding agent learned")
            )
        assert exc.value.details["capability"] == "write_memory"

    async def test_engineering_assistant_may_not_invalidate_or_correct(
        self, core: LifeOpsCore
    ) -> None:
        saved = await core.remember(HERMES, MemoryDraft(content="user likes espresso"))
        with pytest.raises(CapabilityDeniedError):
            await core.invalidate_memory(CODING_CLIENT, memory_id=saved.id)
        with pytest.raises(CapabilityDeniedError):
            await core.correct_memory(
                CODING_CLIENT, memory_id=saved.id, new_content="user likes tea"
            )

    async def test_interactive_client_may_not_remember(
        self, core: LifeOpsCore
    ) -> None:
        with pytest.raises(CapabilityDeniedError):
            await core.remember(
                INTERACTIVE_CLIENT, MemoryDraft(content="a durable fact")
            )
