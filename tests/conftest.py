"""Shared test fixtures.

Unit and policy tests run against in-memory fakes and need no database.
Integration and persistence tests need a live NornicDB and skip themselves when
one is not reachable, so the fast suite stays runnable anywhere.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

from lifeops.clock import FrozenClock
from lifeops.config.service import ConfigurationService
from lifeops.core import LifeOpsCore
from lifeops.domain.people import Person
from lifeops.repositories.fakes import (
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
)
from lifeops.secrets.local_encrypted import InMemorySecretStore, LocalEncryptedSecretStore
from lifeops.settings import Settings

PRIMARY_PERSON_ID = "person_test_user"


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock()


@pytest.fixture
def repos() -> tuple[FakePersonRepository, FakePreferenceRepository, FakeTaskRepository]:
    return FakePersonRepository(), FakePreferenceRepository(), FakeTaskRepository()


@pytest.fixture
async def core(
    repos: tuple[FakePersonRepository, FakePreferenceRepository, FakeTaskRepository],
    clock: FrozenClock,
) -> LifeOpsCore:
    """A LifeOpsCore backed by fakes, with a primary person already present."""
    people, preferences, tasks = repos
    await people.upsert(
        Person(
            id=PRIMARY_PERSON_ID,
            display_name="Test User",
            is_primary=True,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
    )
    return LifeOpsCore(
        people=people, preferences=preferences, tasks=tasks, clock=clock
    )


@pytest.fixture
def secret_store() -> InMemorySecretStore:
    return InMemorySecretStore()


@pytest.fixture
def encrypted_store(tmp_path: Path) -> LocalEncryptedSecretStore:
    return LocalEncryptedSecretStore(tmp_path / "secrets")


@pytest.fixture
def config_service(
    tmp_path: Path, secret_store: InMemorySecretStore, clock: FrozenClock
) -> ConfigurationService:
    return ConfigurationService(
        config_dir=tmp_path / "config", secret_store=secret_store, clock=clock
    )


# --- live NornicDB ----------------------------------------------------------


def _nornic_settings(tmp_path: Path) -> Settings:
    return Settings(
        nornic_uri=os.environ.get("LIFEOPS_NORNIC_URI", "bolt://127.0.0.1:7687"),
        nornic_user=os.environ.get("LIFEOPS_NORNIC_USER", "admin"),
        nornic_password=os.environ.get("LIFEOPS_NORNIC_PASSWORD", ""),
        state_dir=tmp_path / "state",
    )


@pytest.fixture
def nornic_settings(tmp_path: Path) -> Settings:
    return _nornic_settings(tmp_path)


@pytest.fixture
async def nornic_client(nornic_settings: Settings) -> AsyncIterator[object]:
    """A connected NornicClient, or a skip when NornicDB is not running."""
    from lifeops.errors import RepositoryError
    from lifeops.repositories.nornic.client import NornicClient

    client = NornicClient(nornic_settings)
    try:
        await client.connect()
    except RepositoryError as exc:
        pytest.skip(f"NornicDB is not reachable: {exc}")
    await client.ensure_schema()
    try:
        yield client
    finally:
        await client.close()


@pytest.fixture
def test_label(request: pytest.FixtureRequest) -> Iterator[str]:
    """A unique marker so parallel test runs do not collide in a shared DB."""
    yield f"test_{abs(hash(request.node.nodeid)) % 10**10}"
