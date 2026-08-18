"""Failure/chaos tests, part 1 (BUILD_SPEC section 86): the outbox and the
HTTP boundary. Everything here runs against fakes/in-memory repositories —
no live NornicDB, no subprocess — so it belongs in ``make test-fast``.

Covers scenarios 4 (Nornic unavailable), 5 (LifeOps crash), 7 (duplicate
HTTP request), 8 (calendar timeout), 9 (email timeout), 10 (browser crash),
and 16 (provider returns success but verification temporarily unavailable).
Section 86's acceptance line is the thread through all of them: "No failure
may cause duplicate external commitments" — the assertions below check the
outbox's state after each injected failure, not just that an exception was
raised.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager  # type: ignore[import-not-found]

from lifeops.api.http import create_app
from lifeops.browser.fake import FakeBrowser
from lifeops.browser.service import BrowserProviderService
from lifeops.calendar.fake import FakeCalendarProvider
from lifeops.calendar.service import CalendarProviderService
from lifeops.clock import FrozenClock
from lifeops.config.service import ConfigurationService
from lifeops.core import LifeOpsCore
from lifeops.domain.actions import Action, ActionDraft, ActionStatus, ActionType
from lifeops.domain.actions import prepare as prepare_action_domain
from lifeops.domain.approvals import request as request_approval
from lifeops.domain.calendar import AppointmentHoldDraft, AppointmentStatus
from lifeops.domain.email import EmailSendDraft
from lifeops.domain.people import Person
from lifeops.domain.shopping import ShoppingItem, ShoppingListDraft, ShoppingListStatus
from lifeops.email.fake import FakeEmailProvider
from lifeops.email.service import EmailProviderService
from lifeops.errors import ConflictError, ProviderError, RepositoryError
from lifeops.events import EventBus
from lifeops.policy.capabilities import CONSOLE, HERMES
from lifeops.repositories.fakes import (
    FakeActionRepository,
    FakeApprovalRepository,
    FakeAuditRepository,
    FakeMemoryRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeShoppingRepository,
    FakeTaskRepository,
    FakeWaitingRepository,
    FakeWorldRepository,
)
from lifeops.secrets.local_encrypted import InMemorySecretStore
from lifeops.settings import Settings

PRIMARY = "person_chaos_user"
NOW = "2026-09-01T00:00:00Z"
API = "/api/v1"


# --- scenario 4: Nornic unavailable -------------------------------------------


class TestNornicUnavailable:
    """The database never comes back — distinct from scenario 3's restart,
    where it does. No live NornicDB is needed for either half: the first
    proves the driver reports the failure honestly, the second proves the
    HTTP boundary maps it to a 503, not a bare 500."""

    async def test_connecting_to_an_unreachable_nornic_raises_a_repository_error(
        self,
    ) -> None:
        from lifeops.repositories.nornic.client import NornicClient

        # Port 1 is a privileged port nothing listens on in a test sandbox —
        # the OS refuses the connection immediately rather than timing out.
        client = NornicClient(
            Settings(nornic_uri="bolt://127.0.0.1:1", nornic_connect_timeout_s=2.0)
        )
        with pytest.raises(RepositoryError):
            await client.connect()

    async def test_a_repository_failure_maps_to_503_not_a_bare_500(
        self, tmp_path: Path
    ) -> None:
        class FlakyTaskRepository(FakeTaskRepository):
            async def list(self, **kwargs: Any) -> list[Any]:
                raise RepositoryError("cannot reach NornicDB")

        container = _StubContainer(tmp_path, tasks=FlakyTaskRepository())
        app = create_app(container=container, settings=container.settings)  # type: ignore[arg-type]
        async with LifespanManager(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://lifeops.test"
            ) as client:
                response = await client.get(f"{API}/tasks")
        assert response.status_code == 503
        assert response.json()["code"] == "repository_error"


# --- scenario 5: LifeOps crash mid-execute_action -----------------------------


class FlakyActionRepository(FakeActionRepository):
    """Wraps ``FakeActionRepository`` so a specific write can be made to
    fail on demand — the injection point for section 86 scenario 5 (a crash
    between committing an action and recording what happened to it).

    ``recovers_after_failures`` distinguishes a transient blip from a
    genuine outage: ``None`` (the default) fails every call past the
    threshold forever, the same permanent failure the original scenario
    tests; a number caps how many of those calls actually fail before the
    repository starts succeeding again, standing in for the kind of
    momentary failure ``record_action_result``'s retry is meant to survive.
    """

    def __init__(
        self,
        *,
        fail_update_after: int | None = None,
        recovers_after_failures: int | None = None,
    ) -> None:
        super().__init__()
        self._fail_update_after = fail_update_after
        self._recovers_after_failures = recovers_after_failures
        self.update_calls = 0
        self._induced_failures = 0

    async def update(self, action: Action) -> Action:
        self.update_calls += 1
        if self._fail_update_after is not None and self.update_calls > self._fail_update_after:
            still_failing = (
                self._recovers_after_failures is None
                or self._induced_failures < self._recovers_after_failures
            )
            if still_failing:
                self._induced_failures += 1
                raise RepositoryError("simulated repository failure writing the action record")
        return await super().update(action)


class TestCrashBetweenCommitAndRecordResult:
    """``execute_action`` (core.py) catches every ``LifeOpsError`` the
    *provider* call raises, so a calendar/email/browser/telephony failure
    always lands as a FAILED action (scenarios 8-10 below). The write that
    *records* the result is retried a few times (``record_action_result``),
    since it is naturally idempotent and so often follows a real external
    effect that already happened — but a genuinely persistent failure still
    escapes once the retry budget is spent, which is what this test proves:
    the external effect can genuinely happen (the fake calendar really
    creates the event) while LifeOps's own record of it fails to save every
    time, stranding the action in EXECUTING with its approval already
    spent. ``TestRecordActionResultRetry`` below proves the transient case
    — the one the retry actually exists for — recovers instead.

    The invariant section 86 actually asks for still holds even here: a
    stranded action's approval is consumed, so nothing can retry it into a
    second external effect (BUILD_SPEC section 57's single-use approval).
    """

    async def test_a_write_failure_after_a_successful_provider_call_strands_the_action(
        self, tmp_path: Path
    ) -> None:
        fake_calendar = FakeCalendarProvider()
        config = ConfigurationService(
            config_dir=tmp_path / "config",
            secret_store=InMemorySecretStore(),
            clock=FrozenClock(),
        )
        config.update_provider("calendar", {"enabled": True, "backend": "caldav"})
        calendar_service = CalendarProviderService(
            config=config,
            secret_store=InMemorySecretStore(),
            factories={"caldav": lambda settings, secrets: fake_calendar},
        )

        # update() call #1 is decide_approval's action-status sync, #2 is
        # begin_commit's, and #3 is record_action_result's — the one made to
        # fail here.
        actions = FlakyActionRepository(fail_update_after=2)
        people = FakePersonRepository()
        await people.upsert(
            Person(
                id=PRIMARY,
                display_name="Chaos User",
                is_primary=True,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        preferences = FakePreferenceRepository()
        world = FakeWorldRepository(preferences=preferences)
        core = LifeOpsCore(
            people=people,
            preferences=preferences,
            tasks=FakeTaskRepository(),
            world=world,
            waiting=FakeWaitingRepository(),
            actions=actions,
            approvals=FakeApprovalRepository(),
            audit=FakeAuditRepository(),
            calendar=calendar_service,
            clock=FrozenClock(),
        )

        appointment = await core.create_appointment_hold(
            HERMES,
            AppointmentHoldDraft(
                subject="Furnace tune-up",
                start_at="2026-09-01T14:00:00Z",
                end_at="2026-09-01T15:00:00Z",
            ),
        )
        action = await core.book_appointment(HERMES, appointment_id=appointment.id)
        pending = await core.list_pending_approvals(CONSOLE)
        await core.decide_approval(CONSOLE, approval_id=pending[0].id, approved=True)

        # The calendar call happens between #2 and #3 and succeeds for real
        # (fake_calendar actually creates the event) before the write that
        # would record that fact fails.
        with pytest.raises(RepositoryError):
            await core.execute_action(HERMES, action_id=action.id)

        stranded = await core.get_action(HERMES, action_id=action.id)
        assert stranded.status is ActionStatus.EXECUTING

        # The external effect really happened, even though LifeOps never
        # managed to record it — this is the honest, discovered gap, not a
        # fabricated one.
        assert len(fake_calendar._events) == 1

        # But no duplicate commitment is possible: the approval this action
        # needed was already spent at the first (successful) commit.
        with pytest.raises(ConflictError):
            await core.commit_action(HERMES, action_id=action.id)


class TestRecordActionResultRetry:
    """The fix for the gap ``TestCrashBetweenCommitAndRecordResult`` proves
    is real: a transient failure recording the result of a real external
    effect must not strand the action just because the write blipped once
    or twice. ``record_action_result`` retries up to
    ``LifeOpsCore._RECORD_RESULT_ATTEMPTS`` (3) times.
    """

    async def test_a_transient_failure_within_the_retry_budget_recovers(
        self, tmp_path: Path
    ) -> None:
        fake_calendar = FakeCalendarProvider()
        config = ConfigurationService(
            config_dir=tmp_path / "config",
            secret_store=InMemorySecretStore(),
            clock=FrozenClock(),
        )
        config.update_provider("calendar", {"enabled": True, "backend": "caldav"})
        calendar_service = CalendarProviderService(
            config=config,
            secret_store=InMemorySecretStore(),
            factories={"caldav": lambda settings, secrets: fake_calendar},
        )

        # Calls #1/#2 are decide_approval's/begin_commit's own status syncs;
        # #3 and #4 (record_action_result's first two tries) fail, #5 (its
        # third try) succeeds — exactly the retry budget, not more.
        actions = FlakyActionRepository(fail_update_after=2, recovers_after_failures=2)
        people = FakePersonRepository()
        await people.upsert(
            Person(
                id=PRIMARY,
                display_name="Chaos User",
                is_primary=True,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        preferences = FakePreferenceRepository()
        world = FakeWorldRepository(preferences=preferences)
        core = LifeOpsCore(
            people=people,
            preferences=preferences,
            tasks=FakeTaskRepository(),
            world=world,
            waiting=FakeWaitingRepository(),
            actions=actions,
            approvals=FakeApprovalRepository(),
            audit=FakeAuditRepository(),
            calendar=calendar_service,
            clock=FrozenClock(),
        )

        appointment = await core.create_appointment_hold(
            HERMES,
            AppointmentHoldDraft(
                subject="Furnace tune-up",
                start_at="2026-09-01T14:00:00Z",
                end_at="2026-09-01T15:00:00Z",
            ),
        )
        action = await core.book_appointment(HERMES, appointment_id=appointment.id)
        pending = await core.list_pending_approvals(CONSOLE)
        await core.decide_approval(CONSOLE, approval_id=pending[0].id, approved=True)

        # No exception this time: the retry absorbs the two induced failures.
        result = await core.execute_action(HERMES, action_id=action.id)
        assert result.status is ActionStatus.EXECUTED
        assert len(fake_calendar._events) == 1

        # And the outbox agrees with what execute_action returned — the
        # record genuinely landed, not just the in-memory return value.
        fetched = await core.get_action(HERMES, action_id=action.id)
        assert fetched.status is ActionStatus.EXECUTED
        assert actions.update_calls == 5

    async def test_the_retry_is_bounded_not_unlimited(self, tmp_path: Path) -> None:
        """A failure count exactly at the budget's edge still strands —
        proving the retry has a real limit, not an accidental infinite loop
        that happened to terminate above."""
        fake_calendar = FakeCalendarProvider()
        config = ConfigurationService(
            config_dir=tmp_path / "config",
            secret_store=InMemorySecretStore(),
            clock=FrozenClock(),
        )
        config.update_provider("calendar", {"enabled": True, "backend": "caldav"})
        calendar_service = CalendarProviderService(
            config=config,
            secret_store=InMemorySecretStore(),
            factories={"caldav": lambda settings, secrets: fake_calendar},
        )

        # Calls #3, #4, and #5 all fail — every try in the retry budget —
        # so the fourth attempt (#6) that would finally succeed never comes.
        actions = FlakyActionRepository(fail_update_after=2, recovers_after_failures=3)
        people = FakePersonRepository()
        await people.upsert(
            Person(
                id=PRIMARY,
                display_name="Chaos User",
                is_primary=True,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        preferences = FakePreferenceRepository()
        world = FakeWorldRepository(preferences=preferences)
        core = LifeOpsCore(
            people=people,
            preferences=preferences,
            tasks=FakeTaskRepository(),
            world=world,
            waiting=FakeWaitingRepository(),
            actions=actions,
            approvals=FakeApprovalRepository(),
            audit=FakeAuditRepository(),
            calendar=calendar_service,
            clock=FrozenClock(),
        )

        appointment = await core.create_appointment_hold(
            HERMES,
            AppointmentHoldDraft(
                subject="Furnace tune-up",
                start_at="2026-09-01T14:00:00Z",
                end_at="2026-09-01T15:00:00Z",
            ),
        )
        action = await core.book_appointment(HERMES, appointment_id=appointment.id)
        pending = await core.list_pending_approvals(CONSOLE)
        await core.decide_approval(CONSOLE, approval_id=pending[0].id, approved=True)

        with pytest.raises(RepositoryError):
            await core.execute_action(HERMES, action_id=action.id)

        stranded = await core.get_action(HERMES, action_id=action.id)
        assert stranded.status is ActionStatus.EXECUTING
        assert actions.update_calls == 5


# --- scenario 7: duplicate HTTP request ---------------------------------------


class _StubContainer:
    """A Container with fakes in place of NornicDB — mirrors the pattern
    every ``tests/integration/`` HTTP test uses (e.g.
    ``test_durable_work_api.py``), so a repository can be swapped for a
    flaky one without touching real infrastructure."""

    def __init__(
        self,
        tmp_path: Path,
        *,
        tasks: FakeTaskRepository | None = None,
        actions: FakeActionRepository | None = None,
    ) -> None:
        self.settings = Settings(state_dir=tmp_path / "state")
        self.settings.ensure_dirs()
        self.clock = FrozenClock()
        self.secret_store = InMemorySecretStore()
        self.config = ConfigurationService(
            config_dir=self.settings.config_dir,
            secret_store=self.secret_store,
            clock=self.clock,
        )
        self.events = EventBus()
        self.people = FakePersonRepository()
        self.preferences = FakePreferenceRepository()
        self.tasks = tasks if tasks is not None else FakeTaskRepository()
        self.memories = FakeMemoryRepository()
        self.world = FakeWorldRepository(preferences=self.preferences)
        self.waiting = FakeWaitingRepository()
        self.actions = actions if actions is not None else FakeActionRepository()
        self.approvals = FakeApprovalRepository()
        self.audit = FakeAuditRepository()
        self.core = LifeOpsCore(
            people=self.people,
            preferences=self.preferences,
            tasks=self.tasks,
            memory=self.memories,
            world=self.world,
            waiting=self.waiting,
            actions=self.actions,
            approvals=self.approvals,
            audit=self.audit,
            clock=self.clock,
            events=self.events,
        )

    async def startup(self) -> None:
        person = Person(
            id=PRIMARY,
            display_name="Chaos User",
            is_primary=True,
            created_at=NOW,
            updated_at=NOW,
        )
        await self.people.upsert(person)

    async def shutdown(self) -> None:
        return None

    async def health(self) -> dict[str, Any]:
        return {
            "lifeops_core": {"healthy": True, "detail": "running"},
            "nornicdb": {"healthy": True, "detail": "fake"},
            "secret_store": {"healthy": True, "detail": "in-memory"},
            "safe_mode": self.core.safe_mode,
        }


async def _seed_action_needing_approval(container: _StubContainer) -> tuple[str, str]:
    """A BOOK_APPOINTMENT action with a pending approval, seeded directly
    through the repositories the way ``test_durable_work_api.py`` does —
    none of the built-in client identities carry a capability for a
    consequential action type outside a wired provider, so only the HTTP
    routes under test go through the real core."""
    action = prepare_action_domain(
        ActionDraft(
            type=ActionType.BOOK_APPOINTMENT,
            payload={"appointment_id": "appointment_chaos_01"},
            target_entity_id="provider_chaos",
        ),
        now=NOW,
        client_id="hermes-personal",
    )
    created = await container.actions.create(action)
    approval = request_approval(created, now=NOW, requested_by="hermes-personal")
    saved_approval = await container.approvals.create(approval)
    return created.id, saved_approval.id


class TestDuplicateHttpRequest:
    """A duplicate ``POST /actions/{id}/execute`` must not commit twice —
    the guarantee BUILD_SPEC section 86 asks for, exercised at the actual
    transport boundary rather than only at the ``core.py`` layer (which
    ``test_calendar_email_core.py`` and friends already cover thoroughly).
    No calendar is wired, so the first execute fails at the provider call —
    that is fine: what matters is that the *second* request cannot commit
    at all, because the approval the first request spent is gone.
    """

    async def test_the_second_of_two_identical_execute_requests_is_refused(
        self, tmp_path: Path
    ) -> None:
        container = _StubContainer(tmp_path)
        action_id, approval_id = await _seed_action_needing_approval(container)
        app = create_app(container=container, settings=container.settings)  # type: ignore[arg-type]
        async with LifespanManager(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://lifeops.test"
            ) as client:
                await client.post(
                    f"{API}/approvals/{approval_id}/decide", json={"approved": True}
                )
                first = await client.post(f"{API}/actions/{action_id}/execute")
                second = await client.post(f"{API}/actions/{action_id}/execute")

        assert first.status_code == 200
        assert first.json()["status"] == "failed"  # no calendar wired
        assert second.status_code == 409
        assert second.json()["code"] == "conflict"


# --- scenario 8: calendar timeout ---------------------------------------------


class TestCalendarProviderFailure:
    async def test_a_provider_failure_during_booking_lands_the_action_failed(
        self, tmp_path: Path
    ) -> None:
        class TimingOutCalendar(FakeCalendarProvider):
            async def create_event(self, **kwargs: Any) -> str:
                raise ProviderError("timed out waiting for the calendar server", provider="caldav")

        fake_calendar = TimingOutCalendar()
        config = ConfigurationService(
            config_dir=tmp_path / "config",
            secret_store=InMemorySecretStore(),
            clock=FrozenClock(),
        )
        config.update_provider("calendar", {"enabled": True, "backend": "caldav"})
        calendar_service = CalendarProviderService(
            config=config,
            secret_store=InMemorySecretStore(),
            factories={"caldav": lambda settings, secrets: fake_calendar},
        )
        core = await _core_with(calendar=calendar_service)

        appointment = await core.create_appointment_hold(
            HERMES,
            AppointmentHoldDraft(
                subject="Furnace tune-up",
                start_at="2026-09-01T14:00:00Z",
                end_at="2026-09-01T15:00:00Z",
            ),
        )
        action = await core.book_appointment(HERMES, appointment_id=appointment.id)
        pending = await core.list_pending_approvals(CONSOLE)
        await core.decide_approval(CONSOLE, approval_id=pending[0].id, approved=True)

        result = await core.execute_action(HERMES, action_id=action.id)
        assert result.status is ActionStatus.FAILED
        assert "timed out" in (result.failure_reason or "")

        # The hold is untouched — a retry (once the calendar recovers) can
        # still book the same appointment, no duplicate hold needed.
        still_held = await core.get_appointment(HERMES, appointment_id=appointment.id)
        assert still_held.status is AppointmentStatus.HELD


# --- scenario 9: email timeout -------------------------------------------------


class TestEmailProviderFailure:
    async def test_a_provider_failure_sending_lands_the_action_failed(
        self, tmp_path: Path
    ) -> None:
        class TimingOutEmail(FakeEmailProvider):
            async def send(self, draft: EmailSendDraft) -> str:
                raise ProviderError("timed out waiting for the SMTP server", provider="smtp")

        fake_email = TimingOutEmail()
        config = ConfigurationService(
            config_dir=tmp_path / "config",
            secret_store=InMemorySecretStore(),
            clock=FrozenClock(),
        )
        config.update_provider(
            "email", {"enabled": True, "imap_host": "x", "smtp_host": "x", "username": "u"}
        )
        email_service = EmailProviderService(
            config=config,
            secret_store=InMemorySecretStore(),
            factories={"email": lambda settings, secrets: fake_email},
        )
        core = await _core_with(email=email_service)

        action = await core.prepare_send_email(
            HERMES,
            EmailSendDraft(
                to_addresses=["provider@example.invalid"],
                subject="Re: outlet repair",
                body="Following up on the quote.",
            ),
        )
        result = await core.execute_action(HERMES, action_id=action.id)
        assert result.status is ActionStatus.FAILED
        assert "timed out" in (result.failure_reason or "")


# --- scenario 10: browser crash ------------------------------------------------


class TestBrowserProviderFailure:
    """The checkout-failure half of this (``revert_submitting``, called
    when ``submit_grocery_order`` fails) is already covered by
    ``tests/unit/test_shopping.py::TestSubmittingIsRecoverable::
    test_a_failed_checkout_execution_returns_the_list_to_cart_built``. This
    covers the other half — a crash *building* the cart in the first
    place, which lands on ``mark_cart_failed`` and had no test anywhere.
    """

    async def test_a_crash_building_the_cart_lands_on_cart_failed_not_wedged(
        self, tmp_path: Path
    ) -> None:
        class CrashingBrowser(FakeBrowser):
            async def build_cart(self, **kwargs: Any) -> Any:
                raise ProviderError("the browser worker crashed", provider="browser")

        fake_browser = CrashingBrowser()
        config = ConfigurationService(
            config_dir=tmp_path / "config",
            secret_store=InMemorySecretStore(),
            clock=FrozenClock(),
        )
        config.update_provider("browser", {"enabled": True})
        browser_service = BrowserProviderService(
            config=config,
            secret_store=InMemorySecretStore(),
            factories={"browser": lambda settings, secrets: fake_browser},
        )
        core = await _core_with(browser=browser_service)

        shopping_list = await core.create_shopping_list(
            HERMES,
            ShoppingListDraft(
                title="Weekly groceries",
                store="fakemart",
                items=[ShoppingItem(name="Milk", quantity="1 gal")],
            ),
        )
        action = await core.build_grocery_cart(HERMES, list_id=shopping_list.id)
        assert action.status is ActionStatus.FAILED

        recovered = await core.get_shopping_list(HERMES, list_id=shopping_list.id)
        assert recovered.status is ShoppingListStatus.CART_FAILED

        # Not wedged: building again is explicitly permitted from CART_FAILED
        # (core.py's build_grocery_cart), so once the browser recovers the
        # same list can proceed.
        fake_browser_ok = FakeBrowser()
        browser_service._factories["browser"] = lambda settings, secrets: fake_browser_ok
        retry = await core.build_grocery_cart(HERMES, list_id=shopping_list.id)
        assert retry.status is ActionStatus.EXECUTED


# --- scenario 16: verification temporarily unavailable ------------------------


class TestVerificationTemporarilyUnavailable:
    """A provider can accept a request and still not be checkable a moment
    later — section 6's "an accepted request is a claim, not evidence" cuts
    both ways: verification failing is not proof the booking failed either.
    Neither the Action nor the local Appointment record may move until a
    verification actually succeeds.
    """

    async def test_a_flaky_verification_read_leaves_the_action_executed_not_verified(
        self, tmp_path: Path
    ) -> None:
        class FlakyGetEvent(FakeCalendarProvider):
            def __init__(self) -> None:
                super().__init__()
                self.get_event_calls = 0

            async def get_event(self, external_event_id: str) -> Any:
                self.get_event_calls += 1
                if self.get_event_calls == 1:
                    raise ProviderError(
                        "timed out reading the calendar", provider="caldav"
                    )
                return await super().get_event(external_event_id)

        fake_calendar = FlakyGetEvent()
        config = ConfigurationService(
            config_dir=tmp_path / "config",
            secret_store=InMemorySecretStore(),
            clock=FrozenClock(),
        )
        config.update_provider("calendar", {"enabled": True, "backend": "caldav"})
        calendar_service = CalendarProviderService(
            config=config,
            secret_store=InMemorySecretStore(),
            factories={"caldav": lambda settings, secrets: fake_calendar},
        )
        core = await _core_with(calendar=calendar_service)

        appointment = await core.create_appointment_hold(
            HERMES,
            AppointmentHoldDraft(
                subject="Furnace tune-up",
                start_at="2026-09-01T14:00:00Z",
                end_at="2026-09-01T15:00:00Z",
            ),
        )
        action = await core.book_appointment(HERMES, appointment_id=appointment.id)
        pending = await core.list_pending_approvals(CONSOLE)
        await core.decide_approval(CONSOLE, approval_id=pending[0].id, approved=True)
        executed = await core.execute_action(HERMES, action_id=action.id)
        assert executed.status is ActionStatus.EXECUTED

        # The calendar is temporarily unreachable for the verification read.
        with pytest.raises(ProviderError):
            await core.verify_action_externally(HERMES, action_id=action.id)

        still_executed = await core.get_action(HERMES, action_id=action.id)
        assert still_executed.status is ActionStatus.EXECUTED

        still_held = await core.get_appointment(HERMES, appointment_id=appointment.id)
        assert still_held.status is AppointmentStatus.HELD

        # The calendar recovers; a retry succeeds and only now does local
        # state move.
        verified = await core.verify_action_externally(HERMES, action_id=action.id)
        assert verified.status is ActionStatus.VERIFIED
        booked = await core.get_appointment(HERMES, appointment_id=appointment.id)
        assert booked.status is AppointmentStatus.BOOKED


# --- shared fixtures ------------------------------------------------------------


async def _core_with(
    *,
    calendar: CalendarProviderService | None = None,
    email: EmailProviderService | None = None,
    browser: BrowserProviderService | None = None,
) -> LifeOpsCore:
    people = FakePersonRepository()
    await people.upsert(
        Person(
            id=PRIMARY,
            display_name="Chaos User",
            is_primary=True,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    preferences = FakePreferenceRepository()
    world = FakeWorldRepository(preferences=preferences)
    return LifeOpsCore(
        people=people,
        preferences=preferences,
        tasks=FakeTaskRepository(),
        world=world,
        waiting=FakeWaitingRepository(),
        actions=FakeActionRepository(),
        approvals=FakeApprovalRepository(),
        audit=FakeAuditRepository(),
        shopping=FakeShoppingRepository(),
        calendar=calendar,
        email=email,
        browser=browser,
        clock=FrozenClock(),
    )
