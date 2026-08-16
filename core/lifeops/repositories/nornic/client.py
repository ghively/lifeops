"""NornicDB connection management.

NornicDB speaks the Neo4j Bolt protocol, so the official ``neo4j`` driver is
the transport. This module is the only place in LifeOps that knows that.

Schema note: LifeOps writes plain labelled nodes and relationships. It does not
use Nornic's memory-decay, managed-embedding, or auto-relationship features in
Phase 0 — those become relevant in Phase 2 (Memory), and reaching for them
before there is memory to decay would be building for a problem that does not
exist yet (BUILD_SPEC section 105).
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from lifeops.errors import RepositoryError
from lifeops.settings import Settings

logger = logging.getLogger(__name__)

# Uniqueness on canonical IDs is the one invariant worth pushing into the
# database: a duplicate person_gene would silently fork the user's world.
_SCHEMA_STATEMENTS: tuple[str, ...] = (
    "CREATE CONSTRAINT lifeops_person_id IF NOT EXISTS "
    "FOR (p:Person) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT lifeops_preference_id IF NOT EXISTS "
    "FOR (p:Preference) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT lifeops_task_id IF NOT EXISTS "
    "FOR (t:Task) REQUIRE t.id IS UNIQUE",
    "CREATE INDEX lifeops_preference_subject_key IF NOT EXISTS "
    "FOR (p:Preference) ON (p.subject_id, p.key)",
    "CREATE INDEX lifeops_task_state IF NOT EXISTS FOR (t:Task) ON (t.state)",
    "CREATE INDEX lifeops_task_created IF NOT EXISTS FOR (t:Task) ON (t.created_at)",
)


class NornicClient:
    """Owns the Bolt driver and runs parameterised Cypher.

    Every query goes through ``read``/``write`` here, so Cypher never appears
    outside ``repositories/nornic/``.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._driver: AsyncDriver | None = None

    # --- lifecycle ----------------------------------------------------------

    async def connect(self) -> None:
        if self._driver is not None:
            return
        auth = (self._settings.nornic_user, self._settings.nornic_password)
        self._driver = AsyncGraphDatabase.driver(
            self._settings.nornic_uri,
            auth=auth,
            connection_timeout=self._settings.nornic_connect_timeout_s,
        )
        try:
            await self._driver.verify_connectivity()
        except (ServiceUnavailable, Neo4jError) as exc:
            await self.close()
            raise RepositoryError(
                "cannot reach NornicDB", uri=self._settings.nornic_uri
            ) from exc
        logger.info("connected to NornicDB at %s", self._settings.nornic_uri)

    async def close(self) -> None:
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    async def ping(self) -> bool:
        try:
            await self.read("RETURN 1 AS ok")
            return True
        except RepositoryError:
            return False

    async def ensure_schema(self) -> None:
        """Create constraints and indexes. Safe to run on every boot."""
        for statement in _SCHEMA_STATEMENTS:
            try:
                await self.write(statement)
            except RepositoryError:
                # A backend that does not support a given DDL form should not
                # stop LifeOps from booting; the constraint is a safeguard,
                # not a correctness dependency of the domain layer.
                logger.warning("schema statement skipped: %s", statement, exc_info=True)

    # --- queries ------------------------------------------------------------

    @property
    def _session_kwargs(self) -> dict[str, Any]:
        if self._settings.nornic_database:
            return {"database": self._settings.nornic_database}
        return {}

    async def read(self, query: str, /, **params: Any) -> list[dict[str, Any]]:
        return await self._run(query, params)

    async def write(self, query: str, /, **params: Any) -> list[dict[str, Any]]:
        return await self._run(query, params)

    async def write_many(self, statements: list[tuple[str, dict[str, Any]]]) -> None:
        """Run several statements inside one transaction.

        Used where a partial write would corrupt an invariant — closing one
        preference's validity window and opening its replacement, for
        instance.
        """
        driver = self._require_driver()
        try:
            async with driver.session(**self._session_kwargs) as session:
                tx = await session.begin_transaction()
                try:
                    for query, params in statements:
                        await tx.run(query, **params)
                    await tx.commit()
                except BaseException:
                    await tx.rollback()
                    raise
        except (Neo4jError, ServiceUnavailable) as exc:
            raise RepositoryError(f"NornicDB transaction failed: {exc}") from exc

    async def _run(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        driver = self._require_driver()
        try:
            async with driver.session(**self._session_kwargs) as session:
                result = await session.run(query, **params)
                return [record.data() async for record in result]
        except (Neo4jError, ServiceUnavailable) as exc:
            # Deliberately does not echo the query: it can contain personal
            # values, and RepositoryError is surfaced to API clients.
            raise RepositoryError(f"NornicDB query failed: {exc}") from exc

    def _require_driver(self) -> AsyncDriver:
        if self._driver is None:
            raise RepositoryError("NornicDB client is not connected")
        return self._driver
