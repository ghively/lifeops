"""Universal search over people, preferences, and tasks (BUILD_SPEC 19)."""

from __future__ import annotations

import pytest

from lifeops.core import LifeOpsCore
from lifeops.domain.people import PersonDraft
from lifeops.domain.preferences import PreferenceDraft
from lifeops.domain.tasks import TaskDraft
from lifeops.errors import CapabilityDeniedError
from lifeops.policy.capabilities import CONSOLE, ClientIdentity, ClientRole

NO_ACCESS = ClientIdentity(
    client_id="no-access",
    role=ClientRole.ENGINEERING_ASSISTANT,
    display_name="No Access",
    capabilities=frozenset(),
)


async def _seed(core: LifeOpsCore) -> None:
    await core.create_person(CONSOLE, PersonDraft(display_name="Tori Hively"))
    await core.save_preference(
        CONSOLE, PreferenceDraft(key="coffee.roast", value="light roast")
    )
    await core.create_task(
        CONSOLE, TaskDraft(title="Repair living room outlet", description="call Tori")
    )


class TestSearch:
    async def test_matches_across_all_three_domains(self, core: LifeOpsCore) -> None:
        await _seed(core)

        by_name = await core.search(CONSOLE, query="tori")
        assert [p.display_name for p in by_name.people] == ["Tori Hively"]
        assert [t.title for t in by_name.tasks] == ["Repair living room outlet"]
        assert by_name.preferences == []

        by_key = await core.search(CONSOLE, query="ROAST")
        assert [p.key for p in by_key.preferences] == ["coffee.roast"]

    async def test_substring_and_case_insensitive(self, core: LifeOpsCore) -> None:
        await _seed(core)
        results = await core.search(CONSOLE, query="OUTLET")
        assert [t.title for t in results.tasks] == ["Repair living room outlet"]

    async def test_superseded_preferences_do_not_match(self, core: LifeOpsCore) -> None:
        await core.save_preference(CONSOLE, PreferenceDraft(key="coffee.roast", value="dark"))
        await core.save_preference(CONSOLE, PreferenceDraft(key="coffee.roast", value="light"))

        results = await core.search(CONSOLE, query="dark")
        assert results.preferences == []

    async def test_no_matches_returns_empty_groups(self, core: LifeOpsCore) -> None:
        results = await core.search(CONSOLE, query="zzzz-nothing")
        assert results.people == [] and results.preferences == [] and results.tasks == []

    async def test_limit_bounds_each_group(self, core: LifeOpsCore) -> None:
        for index in range(8):
            await core.create_task(CONSOLE, TaskDraft(title=f"chore {index}"))
        results = await core.search(CONSOLE, query="chore", limit=3)
        assert len(results.tasks) == 3

    async def test_requires_read_world(self, core: LifeOpsCore) -> None:
        with pytest.raises(CapabilityDeniedError):
            await core.search(NO_ACCESS, query="anything")

    async def test_people_search_matches_aliases(self, core: LifeOpsCore) -> None:
        await core.create_person(
            CONSOLE, PersonDraft(display_name="Tori Hively", aliases=["TJ"])
        )
        results = await core.search(CONSOLE, query="tj")
        assert [p.display_name for p in results.people] == ["Tori Hively"]
