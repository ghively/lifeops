"""ConsoleAuth — password-gated bearer tokens for the Console API."""

from __future__ import annotations

import pytest

from lifeops.auth import TOKEN_TTL_S, ConsoleAuth
from lifeops.clock import FrozenClock
from lifeops.errors import LifeOpsError, ValidationError
from lifeops.secrets.local_encrypted import InMemorySecretStore
from lifeops.settings import Settings


@pytest.fixture
def store() -> InMemorySecretStore:
    return InMemorySecretStore()


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock()


def make_auth(
    store: InMemorySecretStore, clock: FrozenClock, *, auth_enabled: bool = True
) -> ConsoleAuth:
    return ConsoleAuth(
        secret_store=store,
        settings=Settings(console_auth_enabled=auth_enabled),
        clock=clock,
    )


class TestEnabled:
    def test_disabled_until_a_password_is_set(
        self, store: InMemorySecretStore, clock: FrozenClock
    ) -> None:
        auth = make_auth(store, clock)
        assert auth.enabled is False
        auth.set_password("correct horse")
        assert auth.enabled is True

    def test_master_switch_overrides_a_configured_password(
        self, store: InMemorySecretStore, clock: FrozenClock
    ) -> None:
        auth = make_auth(store, clock, auth_enabled=False)
        auth.set_password("correct horse")
        assert auth.enabled is False

    def test_password_goes_to_the_secret_store_nowhere_else(
        self, store: InMemorySecretStore, clock: FrozenClock
    ) -> None:
        auth = make_auth(store, clock)
        auth.set_password("correct horse")
        assert store.list_names() == ["console.password"]


class TestLogin:
    def test_wrong_password_is_refused(
        self, store: InMemorySecretStore, clock: FrozenClock
    ) -> None:
        auth = make_auth(store, clock)
        auth.set_password("correct horse")
        with pytest.raises(LifeOpsError) as err:
            auth.login("wrong")
        assert err.value.code == "invalid_credentials"

    def test_correct_password_issues_a_valid_token(
        self, store: InMemorySecretStore, clock: FrozenClock
    ) -> None:
        auth = make_auth(store, clock)
        auth.set_password("correct horse")
        token, expires_at = auth.login("correct horse")
        assert auth.validate(token) is True
        assert expires_at.startswith("2026-01-01T12:00:00")  # FrozenClock + TTL

    def test_unknown_token_is_not_valid(
        self, store: InMemorySecretStore, clock: FrozenClock
    ) -> None:
        auth = make_auth(store, clock)
        assert auth.validate("never-issued") is False
        assert auth.validate(None) is False

    def test_token_expires(
        self, store: InMemorySecretStore, clock: FrozenClock
    ) -> None:
        auth = make_auth(store, clock)
        auth.set_password("correct horse")
        token, _ = auth.login("correct horse")
        clock.advance(TOKEN_TTL_S - 1)
        assert auth.validate(token) is True
        clock.advance(2)
        assert auth.validate(token) is False

    def test_empty_password_is_a_validation_error(
        self, store: InMemorySecretStore, clock: FrozenClock
    ) -> None:
        auth = make_auth(store, clock)
        with pytest.raises(ValidationError):
            auth.set_password("")
