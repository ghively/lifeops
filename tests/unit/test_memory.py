"""Memory domain behaviour (BUILD_SPEC sections 42–47).

Runs entirely against the in-memory fakes with a FrozenClock: durability
rules, temporal supersession, recall, and the section 44 guarantee that no
memory operation can touch transactional state.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from lifeops.clock import FrozenClock
from lifeops.core import LifeOpsCore
from lifeops.domain.memory import (
    MemoryDraft,
    MemoryType,
    is_filler_content,
    looks_like_secret,
)
from lifeops.domain.people import Person
from lifeops.domain.preferences import Preference, PreferenceSource
from lifeops.domain.tasks import Task
from lifeops.errors import (
    CapabilityDeniedError,
    ConfigurationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from lifeops.policy import CODING_CLIENT, HERMES
from lifeops.repositories.fakes import (
    FakeMemoryRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
)

PRIMARY_PERSON_ID = "person_memory_test_user"


class SpyPreferenceRepository(FakePreferenceRepository):
    """Records every call so tests can prove memory never touches it."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    def _record(self, name: str):  # noqa: ANN202
        self.calls.append(name)

    async def get(self, preference_id: str):  # noqa: ANN201
        self._record("get")
        return await super().get(preference_id)

    async def list_current(self, subject_id: str, *, key_prefix=None):  # noqa: ANN202
        self._record("list_current")
        return await super().list_current(subject_id, key_prefix=key_prefix)

    async def get_current_by_key(self, subject_id: str, key: str):  # noqa: ANN202
        self._record("get_current_by_key")
        return await super().get_current_by_key(subject_id, key)

    async def search(self, query: str, *, limit: int = 25):  # noqa: ANN202
        self._record("search")
        return await super().search(query, limit=limit)

    async def list_history(self, subject_id: str, key: str):  # noqa: ANN202
        self._record("list_history")
        return await super().list_history(subject_id, key)

    async def save_superseding(self, preference: Preference, *, supersedes):  # noqa: ANN202
        self._record("save_superseding")
        return await super().save_superseding(preference, supersedes=supersedes)

    async def invalidate(self, preference_id: str, *, at: str):  # noqa: ANN202
        self._record("invalidate")
        return await super().invalidate(preference_id, at=at)


class SpyTaskRepository(FakeTaskRepository):
    """Records every call so tests can prove memory never touches it."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    async def get(self, task_id: str):  # noqa: ANN202
        self.calls.append("get")
        return await super().get(task_id)

    async def list(self, **kwargs):  # noqa: ANN202
        self.calls.append("list")
        return await super().list(**kwargs)

    async def count_by_state(self):  # noqa: ANN202
        self.calls.append("count_by_state")
        return await super().count_by_state()

    async def search(self, query: str, *, limit: int = 25):  # noqa: ANN202
        self.calls.append("search")
        return await super().search(query, limit=limit)

    async def create(self, task: Task):  # noqa: ANN202
        self.calls.append("create")
        return await super().create(task)

    async def update(self, task: Task):  # noqa: ANN202
        self.calls.append("update")
        return await super().update(task)


@pytest.fixture
def people() -> FakePersonRepository:
    return FakePersonRepository()


@pytest.fixture
def preferences() -> SpyPreferenceRepository:
    return SpyPreferenceRepository()


@pytest.fixture
def tasks() -> SpyTaskRepository:
    return SpyTaskRepository()


@pytest.fixture
def memories() -> FakeMemoryRepository:
    return FakeMemoryRepository()


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock()


@pytest.fixture
async def core(
    people: FakePersonRepository,
    preferences: SpyPreferenceRepository,
    tasks: SpyTaskRepository,
    memories: FakeMemoryRepository,
    clock: FrozenClock,
) -> LifeOpsCore:
    await people.upsert(
        Person(
            id=PRIMARY_PERSON_ID,
            display_name="Memory Test User",
            is_primary=True,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
    )
    return LifeOpsCore(
        people=people,
        preferences=preferences,
        tasks=tasks,
        memory=memories,
        clock=clock,
    )


class TestDurabilityRules:
    """Section 47: not every utterance deserves permanence."""

    @pytest.mark.parametrize(
        "content",
        ["ok", "Thanks!", "hello", "hm", "yes", "got it", "x"],
    )
    def test_filler_is_rejected(self, content: str) -> None:
        assert is_filler_content(content)

    @pytest.mark.parametrize(
        "content",
        [
            "The user prefers morning appointments",
            "Thanks for the restaurant recommendation, I loved it",
            "Call the dentist about the crown",
        ],
    )
    def test_real_content_is_not_filler(self, content: str) -> None:
        assert not is_filler_content(content)

    @pytest.mark.parametrize(
        "content",
        [
            "my email password: hunter2",
            "api_key = sk-abcdefghij0123456789abcd",
            "token: xoxb-1234567890-abcdefghij",
            "-----BEGIN RSA PRIVATE KEY-----",
            "aws key AKIAIOSFODNN7EXAMPLE",
            "cvv: 123",
            "github token ghp_abcdefghij0123456789abcd",
        ],
    )
    def test_secret_looking_content_is_flagged(self, content: str) -> None:
        assert looks_like_secret(content)

    @pytest.mark.parametrize(
        "content",
        [
            "My password manager is Bitwarden",
            "The API key rotation is scheduled for next quarter",
            "We talked about token budgets for the project",
        ],
    )
    def test_mentioning_secrets_is_not_a_secret(self, content: str) -> None:
        assert not looks_like_secret(content)

    async def test_remember_rejects_filler(self, core: LifeOpsCore) -> None:
        with pytest.raises(ValidationError) as exc:
            await core.remember(HERMES, MemoryDraft(content="ok"))
        assert exc.value.details["reason"] == "filler_content"

    async def test_remember_rejects_secret_looking_content(
        self, core: LifeOpsCore
    ) -> None:
        with pytest.raises(ValidationError) as exc:
            await core.remember(HERMES, MemoryDraft(content="wifi password: hunter2"))
        assert exc.value.details["reason"] == "secret_like_content"

    def test_draft_scores_are_bounded(self) -> None:
        with pytest.raises(PydanticValidationError):
            MemoryDraft(content="a real fact about the user", confidence=1.5)
        with pytest.raises(PydanticValidationError):
            MemoryDraft(content="a real fact about the user", importance=-0.1)


class TestRemember:
    async def test_remember_and_recall(self, core: LifeOpsCore) -> None:
        saved = await core.remember(
            HERMES,
            MemoryDraft(
                content="The user is allergic to penicillin",
                type=MemoryType.SEMANTIC,
                source_type=PreferenceSource.USER_EXPLICIT,
                importance=0.9,
            ),
        )
        assert saved.is_current
        assert saved.subject_id == PRIMARY_PERSON_ID
        assert saved.created_by_client == "hermes-personal"
        assert saved.id.startswith("memory_")

        recalled = await core.recall(HERMES, query="penicillin")
        assert [m.id for m in recalled] == [saved.id]

    async def test_restating_an_identical_memory_is_a_no_op(
        self, core: LifeOpsCore, clock: FrozenClock
    ) -> None:
        first = await core.remember(HERMES, MemoryDraft(content="User drinks oat milk"))
        clock.advance(3600)
        second = await core.remember(HERMES, MemoryDraft(content="User drinks oat milk"))
        assert second.id == first.id, "duplicates must not pile up (section 47)"

    async def test_remember_defaults_to_the_primary_person(
        self, core: LifeOpsCore
    ) -> None:
        saved = await core.remember(HERMES, MemoryDraft(content="User drinks oat milk"))
        assert saved.subject_id == PRIMARY_PERSON_ID

    async def test_remember_unknown_subject_raises(self, core: LifeOpsCore) -> None:
        with pytest.raises(NotFoundError):
            await core.remember(
                HERMES,
                MemoryDraft(
                    content="A fact about someone", subject_id="person_absent"
                ),
            )

    async def test_recall_filters_by_type(self, core: LifeOpsCore) -> None:
        await core.remember(
            HERMES, MemoryDraft(content="Dentist visit on Friday", type=MemoryType.EPISODIC)
        )
        pref_candidate = await core.remember(
            HERMES,
            MemoryDraft(
                content="User seems to prefer evening appointments",
                type=MemoryType.PREFERENCE_CANDIDATE,
                source_type=PreferenceSource.USER_INFERRED,
            ),
        )
        found = await core.recall(
            HERMES, query="appointments", memory_types=[MemoryType.PREFERENCE_CANDIDATE]
        )
        assert [m.id for m in found] == [pref_candidate.id]

    async def test_blank_recall_lists_current_memories(self, core: LifeOpsCore) -> None:
        low = await core.remember(
            HERMES, MemoryDraft(content="likes green tea", importance=0.2)
        )
        high = await core.remember(
            HERMES, MemoryDraft(content="allergic to penicillin", importance=0.95)
        )
        listed = await core.recall(HERMES)
        assert [m.id for m in listed] == [high.id, low.id]

    async def test_unconfigured_memory_raises_a_stable_error(
        self, people, preferences, tasks, clock
    ) -> None:
        bare = LifeOpsCore(
            people=people, preferences=preferences, tasks=tasks, clock=clock
        )
        with pytest.raises(ConfigurationError):
            await bare.recall(HERMES, query="anything at all")


class TestTemporalCorrection:
    async def test_correct_memory_supersedes_without_overwriting(
        self, core: LifeOpsCore, clock: FrozenClock
    ) -> None:
        original = await core.remember(
            HERMES, MemoryDraft(content="User's dentist is Dr. Patel")
        )
        clock.advance(3600)
        corrected = await core.correct_memory(
            HERMES, memory_id=original.id, new_content="User's dentist is Dr. Nguyen"
        )

        assert corrected.id != original.id
        assert corrected.supersedes == original.id
        assert corrected.is_current

        old = await core.get_memory(HERMES, memory_id=original.id)
        assert not old.is_current
        assert old.content == "User's dentist is Dr. Patel", "history is preserved"

        current = await core.recall(HERMES, query="dentist")
        assert [m.id for m in current] == [corrected.id]

    async def test_history_returns_the_whole_chain(
        self, core: LifeOpsCore, clock: FrozenClock
    ) -> None:
        first = await core.remember(HERMES, MemoryDraft(content="lives on Oak Street"))
        clock.advance(60)
        second = await core.correct_memory(
            HERMES, memory_id=first.id, new_content="lives on Maple Street"
        )
        clock.advance(60)
        third = await core.correct_memory(
            HERMES, memory_id=second.id, new_content="lives on Birch Street"
        )

        history = await core.memory_history(HERMES, memory_id=first.id)
        assert [m.id for m in history] == [third.id, second.id, first.id]
        # Asking from any version returns the same chain.
        history_from_tip = await core.memory_history(HERMES, memory_id=third.id)
        assert [m.id for m in history_from_tip] == [third.id, second.id, first.id]

    async def test_weaker_source_cannot_correct_user_explicit_memory(
        self, core: LifeOpsCore
    ) -> None:
        stated = await core.remember(
            HERMES,
            MemoryDraft(
                content="User's birthday is March 3",
                source_type=PreferenceSource.USER_EXPLICIT,
            ),
        )
        with pytest.raises(ConflictError):
            # A model guess does not get to overwrite what the user said.
            await core.correct_memory(
                HERMES,
                memory_id=stated.id,
                new_content="User's birthday is March 5",
                source_type=PreferenceSource.AGENT,
            )

    async def test_correcting_an_invalidated_memory_is_refused(
        self, core: LifeOpsCore
    ) -> None:
        saved = await core.remember(HERMES, MemoryDraft(content="drives a blue car"))
        await core.invalidate_memory(HERMES, memory_id=saved.id, reason="sold it")
        with pytest.raises(ConflictError) as exc:
            await core.correct_memory(
                HERMES, memory_id=saved.id, new_content="drives a red car"
            )
        assert exc.value.details["reason"] == "memory_not_current"

    async def test_identical_correction_is_a_no_op(self, core: LifeOpsCore) -> None:
        saved = await core.remember(HERMES, MemoryDraft(content="drives a blue car"))
        again = await core.correct_memory(
            HERMES, memory_id=saved.id, new_content="drives a blue car"
        )
        assert again.id == saved.id


class TestInvalidate:
    async def test_invalidate_closes_the_window_and_hides_from_recall(
        self, core: LifeOpsCore
    ) -> None:
        saved = await core.remember(HERMES, MemoryDraft(content="has a dog named Rex"))
        closed = await core.invalidate_memory(
            HERMES, memory_id=saved.id, reason="user asked to forget"
        )
        assert not closed.is_current
        assert closed.invalidation_reason == "user asked to forget"

        assert await core.recall(HERMES, query="Rex") == []
        # The record itself is still retrievable for audit.
        assert (await core.get_memory(HERMES, memory_id=saved.id)).id == saved.id

    async def test_invalidate_unknown_memory_raises(self, core: LifeOpsCore) -> None:
        with pytest.raises(NotFoundError):
            await core.invalidate_memory(HERMES, memory_id="memory_absent")


class TestMemorySafety:
    """BUILD_SPEC section 44: memory observes; it never rewrites reality."""

    def test_draft_cannot_carry_transactional_references(self) -> None:
        # A draft smuggling a task/action/approval id is rejected at the
        # boundary rather than silently ignored.
        with pytest.raises(PydanticValidationError):
            MemoryDraft(content="x", task_id="task_01")  # type: ignore[call-arg]
        with pytest.raises(PydanticValidationError):
            MemoryDraft(content="x", action_id="act_01")  # type: ignore[call-arg]
        with pytest.raises(PydanticValidationError):
            MemoryDraft(content="x", state="completed")  # type: ignore[call-arg]

    async def test_memory_operations_never_touch_task_or_preference_repositories(
        self,
        core: LifeOpsCore,
        preferences: SpyPreferenceRepository,
        tasks: SpyTaskRepository,
    ) -> None:
        saved = await core.remember(HERMES, MemoryDraft(content="user likes espresso"))
        await core.recall(HERMES, query="espresso")
        await core.get_memory(HERMES, memory_id=saved.id)
        await core.memory_history(HERMES, memory_id=saved.id)
        await core.correct_memory(
            HERMES, memory_id=saved.id, new_content="user likes ristretto"
        )
        await core.invalidate_memory(HERMES, memory_id=saved.id, reason="test")

        assert preferences.calls == [], "memory must not read or write preferences"
        assert tasks.calls == [], "memory must not read or write tasks"

    async def test_preference_candidate_is_not_a_preference(
        self, core: LifeOpsCore
    ) -> None:
        candidate = await core.remember(
            HERMES,
            MemoryDraft(
                content="User might prefer window seats",
                type=MemoryType.PREFERENCE_CANDIDATE,
                source_type=PreferenceSource.USER_INFERRED,
            ),
        )
        # Section 44: an inferred candidate is an observation, not a stated
        # preference. It must not appear on the preference surface.
        prefs = await core.get_preferences(HERMES)
        assert candidate.content not in {p.value for p in prefs}
        assert prefs == []

    async def test_memory_capability_is_required(
        self, core: LifeOpsCore
    ) -> None:
        with pytest.raises(CapabilityDeniedError):
            await core.remember(CODING_CLIENT, MemoryDraft(content="sneaky write"))

    def test_memory_service_holds_only_the_memory_repository(self) -> None:
        # Structural proof of section 44: the service's dependencies are a
        # MemoryRepository, a clock, and an event callback. There is nothing
        # to approve, pay, complete, or authorise with.
        from lifeops.core import MemoryService

        service = MemoryService(
            memories=FakeMemoryRepository(), clock=FrozenClock()
        )
        dependency_names = set(vars(service))
        assert dependency_names == {"_memories", "_clock", "_publish_event"}
