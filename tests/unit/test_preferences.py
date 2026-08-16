"""Temporal preference behaviour: supersession, history, and trust ordering."""

from __future__ import annotations

import pytest

from lifeops.clock import FrozenClock
from lifeops.core import LifeOpsCore
from lifeops.domain.preferences import PreferenceDraft, PreferenceSource, normalise_key
from lifeops.errors import ConflictError
from lifeops.policy import HERMES
from lifeops.policy.trust import may_supersede
from tests.conftest import PRIMARY_PERSON_ID


class TestNormaliseKey:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Scheduling.Earliest", "scheduling.earliest"),
            ("  scheduling earliest  ", "scheduling_earliest"),
            ("scheduling__earliest", "scheduling_earliest"),
            ("_scheduling.earliest_", "scheduling.earliest"),
        ],
    )
    def test_variants_collapse_to_one_key(self, raw: str, expected: str) -> None:
        # Two spellings of the same key must not become two "current" values.
        assert normalise_key(raw) == expected


class TestSavePreference:
    async def test_saves_and_reads_back(self, core: LifeOpsCore) -> None:
        saved = await core.save_preference(
            HERMES,
            PreferenceDraft(
                key="scheduling.earliest_appointment_time",
                value="No appointments before 10 AM",
            ),
        )
        assert saved.is_current
        assert saved.supersedes is None
        assert saved.created_by_client == "hermes-personal"

        current = await core.get_preferences(HERMES)
        assert [p.value for p in current] == ["No appointments before 10 AM"]

    async def test_second_save_supersedes_the_first(
        self, core: LifeOpsCore, clock: FrozenClock
    ) -> None:
        first = await core.save_preference(
            HERMES, PreferenceDraft(key="scheduling.earliest", value="after 10")
        )
        clock.advance(3600)
        second = await core.save_preference(
            HERMES, PreferenceDraft(key="scheduling.earliest", value="after 9")
        )

        assert second.supersedes == first.id

        current = await core.get_preferences(HERMES)
        assert len(current) == 1, "only one value may be current for a key"
        assert current[0].value == "after 9"

    async def test_superseded_record_is_kept_with_a_closed_window(
        self, core: LifeOpsCore, clock: FrozenClock
    ) -> None:
        await core.save_preference(
            HERMES, PreferenceDraft(key="scheduling.earliest", value="after 10")
        )
        clock.advance(3600)
        await core.save_preference(
            HERMES, PreferenceDraft(key="scheduling.earliest", value="after 9")
        )

        history = await core.get_preference_history(HERMES, key="scheduling.earliest")
        assert len(history) == 2
        old = next(p for p in history if p.value == "after 10")
        assert old.valid_to is not None, "history must be preserved, not overwritten"
        assert not old.is_current

    async def test_restating_the_same_value_does_not_grow_history(
        self, core: LifeOpsCore, clock: FrozenClock
    ) -> None:
        first = await core.save_preference(
            HERMES, PreferenceDraft(key="scheduling.earliest", value="after 10")
        )
        clock.advance(60)
        again = await core.save_preference(
            HERMES, PreferenceDraft(key="scheduling.earliest", value="  after 10  ")
        )
        assert again.id == first.id

        history = await core.get_preference_history(HERMES, key="scheduling.earliest")
        assert len(history) == 1

    async def test_key_prefix_filter(self, core: LifeOpsCore) -> None:
        await core.save_preference(
            HERMES, PreferenceDraft(key="scheduling.earliest", value="after 10")
        )
        await core.save_preference(
            HERMES, PreferenceDraft(key="shopping.store", value="the co-op")
        )

        scheduling = await core.get_preferences(HERMES, key_prefix="scheduling")
        assert [p.key for p in scheduling] == ["scheduling.earliest"]

    async def test_invalidate_closes_the_window(self, core: LifeOpsCore) -> None:
        saved = await core.save_preference(
            HERMES, PreferenceDraft(key="scheduling.earliest", value="after 10")
        )
        await core.invalidate_preference(HERMES, preference_id=saved.id)
        assert await core.get_preferences(HERMES) == []


class TestTrustHierarchy:
    """BUILD_SPEC section 46: external content is evidence, not authority."""

    def test_explicit_user_statement_outranks_everything(self) -> None:
        for source in PreferenceSource:
            if source is PreferenceSource.USER_EXPLICIT:
                continue
            assert may_supersede(PreferenceSource.USER_EXPLICIT, source)
            assert not may_supersede(source, PreferenceSource.USER_EXPLICIT)

    def test_equal_authority_may_update(self) -> None:
        # The user restating a preference is a legitimate update.
        assert may_supersede(
            PreferenceSource.USER_EXPLICIT, PreferenceSource.USER_EXPLICIT
        )

    def test_website_cannot_override_a_calendar_fact(self) -> None:
        assert not may_supersede(PreferenceSource.WEBSITE, PreferenceSource.CALENDAR)

    async def test_inference_cannot_overwrite_what_the_user_said(
        self, core: LifeOpsCore
    ) -> None:
        await core.save_preference(
            HERMES,
            PreferenceDraft(
                key="scheduling.earliest",
                value="after 10",
                source_type=PreferenceSource.USER_EXPLICIT,
            ),
        )

        with pytest.raises(ConflictError) as exc:
            await core.save_preference(
                HERMES,
                PreferenceDraft(
                    key="scheduling.earliest",
                    value="after 7 — they booked an early slot once",
                    source_type=PreferenceSource.USER_INFERRED,
                ),
            )
        assert exc.value.details["existing_source"] == "user_explicit"

        current = await core.get_preferences(HERMES)
        assert current[0].value == "after 10"

    async def test_user_can_correct_an_inference(self, core: LifeOpsCore) -> None:
        await core.save_preference(
            HERMES,
            PreferenceDraft(
                key="scheduling.earliest",
                value="probably after 8",
                source_type=PreferenceSource.USER_INFERRED,
            ),
        )
        corrected = await core.save_preference(
            HERMES,
            PreferenceDraft(
                key="scheduling.earliest",
                value="after 10",
                source_type=PreferenceSource.USER_EXPLICIT,
            ),
        )
        assert corrected.value == "after 10"


class TestSubjectResolution:
    async def test_defaults_to_the_primary_person(self, core: LifeOpsCore) -> None:
        saved = await core.save_preference(
            HERMES, PreferenceDraft(key="scheduling.earliest", value="after 10")
        )
        assert saved.subject_id == PRIMARY_PERSON_ID

    async def test_unknown_subject_is_rejected(self, core: LifeOpsCore) -> None:
        from lifeops.errors import NotFoundError

        with pytest.raises(NotFoundError):
            await core.save_preference(
                HERMES,
                PreferenceDraft(
                    key="k", value="v", subject_id="person_does_not_exist"
                ),
            )
