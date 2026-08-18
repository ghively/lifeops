"""NornicDB connection management.

NornicDB speaks the Neo4j Bolt protocol, so the official ``neo4j`` driver is
the transport. This module is the only place in LifeOps that knows that.

Schema note: LifeOps writes plain labelled nodes and relationships. The one
Nornic-specific capability it relies on is the Lucene-backed fulltext index
used for BM25 memory recall (Phase 2, BUILD_SPEC section 47). Managed
embeddings and decay machinery stay off until a phase has a concrete need for
them (section 105).
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
    "CREATE CONSTRAINT lifeops_memory_id IF NOT EXISTS "
    "FOR (m:Memory) REQUIRE m.id IS UNIQUE",
    # The Phase 3 world entities get the same protection: two nodes sharing
    # provider_abc_electric would split the graph around one real provider.
    "CREATE CONSTRAINT lifeops_household_id IF NOT EXISTS "
    "FOR (h:Household) REQUIRE h.id IS UNIQUE",
    "CREATE CONSTRAINT lifeops_provider_id IF NOT EXISTS "
    "FOR (p:Provider) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT lifeops_asset_id IF NOT EXISTS "
    "FOR (a:Asset) REQUIRE a.id IS UNIQUE",
    # Phase 4 durable-work labels get the same id protection, plus the
    # idempotency-key constraint section 61 depends on: two Action nodes
    # sharing a key would defeat the mechanism that prevents a blind retry
    # from double-booking or double-charging.
    "CREATE CONSTRAINT lifeops_waiting_id IF NOT EXISTS "
    "FOR (w:WaitingItem) REQUIRE w.id IS UNIQUE",
    "CREATE CONSTRAINT lifeops_action_id IF NOT EXISTS "
    "FOR (a:Action) REQUIRE a.id IS UNIQUE",
    "CREATE CONSTRAINT lifeops_action_idempotency_key IF NOT EXISTS "
    "FOR (a:Action) REQUIRE a.idempotency_key IS UNIQUE",
    "CREATE CONSTRAINT lifeops_approval_id IF NOT EXISTS "
    "FOR (ap:Approval) REQUIRE ap.id IS UNIQUE",
    "CREATE CONSTRAINT lifeops_audit_id IF NOT EXISTS "
    "FOR (r:AuditRecord) REQUIRE r.id IS UNIQUE",
    # Phase 7 (BUILD_SPEC sections 63, 64, 96): a duplicate appointment_ id
    # is exactly the "booked it twice" failure section 60 exists to prevent.
    "CREATE CONSTRAINT lifeops_appointment_id IF NOT EXISTS "
    "FOR (a:Appointment) REQUIRE a.id IS UNIQUE",
    "CREATE CONSTRAINT lifeops_event_id IF NOT EXISTS "
    "FOR (e:Event) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT lifeops_document_id IF NOT EXISTS "
    "FOR (d:Document) REQUIRE d.id IS UNIQUE",
    # Phase 8 (BUILD_SPEC section 97): a duplicate servicerequest_ id would
    # let one provider workflow silently fork into two.
    "CREATE CONSTRAINT lifeops_servicerequest_id IF NOT EXISTS "
    "FOR (s:ServiceRequest) REQUIRE s.id IS UNIQUE",
    # Phase 9 (BUILD_SPEC section 98): a duplicate shoppinglist_ id is the
    # "checked out twice" failure section 60 exists to prevent.
    "CREATE CONSTRAINT lifeops_shopping_list_id IF NOT EXISTS "
    "FOR (s:ShoppingList) REQUIRE s.id IS UNIQUE",
    # Phase 10 (sections 72, 99). The payee constraint matters most: two
    # Payee nodes sharing an id is how a payment reaches the wrong one.
    "CREATE CONSTRAINT lifeops_bill_id IF NOT EXISTS "
    "FOR (b:Bill) REQUIRE b.id IS UNIQUE",
    "CREATE CONSTRAINT lifeops_payee_id IF NOT EXISTS "
    "FOR (p:Payee) REQUIRE p.id IS UNIQUE",
    "CREATE INDEX lifeops_bill_status IF NOT EXISTS FOR (b:Bill) ON (b.status)",
    "CREATE INDEX lifeops_bill_due IF NOT EXISTS FOR (b:Bill) ON (b.due_at)",
    # Phase 11 (sections 73, 100).
    "CREATE CONSTRAINT lifeops_workflow_template_id IF NOT EXISTS "
    "FOR (t:WorkflowTemplate) REQUIRE t.id IS UNIQUE",
    "CREATE INDEX lifeops_workflow_template_next_run IF NOT EXISTS "
    "FOR (t:WorkflowTemplate) ON (t.next_run_at)",
    "CREATE INDEX lifeops_preference_subject_key IF NOT EXISTS "
    "FOR (p:Preference) ON (p.subject_id, p.key)",
    "CREATE INDEX lifeops_task_state IF NOT EXISTS FOR (t:Task) ON (t.state)",
    "CREATE INDEX lifeops_task_created IF NOT EXISTS FOR (t:Task) ON (t.created_at)",
    "CREATE INDEX lifeops_memory_subject IF NOT EXISTS "
    "FOR (m:Memory) ON (m.subject_id)",
    "CREATE INDEX lifeops_waiting_task IF NOT EXISTS "
    "FOR (w:WaitingItem) ON (w.task_id)",
    "CREATE INDEX lifeops_waiting_status IF NOT EXISTS "
    "FOR (w:WaitingItem) ON (w.status)",
    "CREATE INDEX lifeops_action_task IF NOT EXISTS "
    "FOR (a:Action) ON (a.task_id)",
    "CREATE INDEX lifeops_action_status IF NOT EXISTS "
    "FOR (a:Action) ON (a.status)",
    "CREATE INDEX lifeops_approval_action IF NOT EXISTS "
    "FOR (ap:Approval) ON (ap.action_id)",
    "CREATE INDEX lifeops_approval_status IF NOT EXISTS "
    "FOR (ap:Approval) ON (ap.status)",
    "CREATE INDEX lifeops_audit_target IF NOT EXISTS "
    "FOR (r:AuditRecord) ON (r.target)",
    # BM25 recall for the memory layer (BUILD_SPEC section 47). Embeddings stay
    # off; on a backend without fulltext support this is skipped with a warning
    # and the repository falls back to substring matching.
    "CREATE FULLTEXT INDEX lifeops_memory_content IF NOT EXISTS "
    "FOR (m:Memory) ON EACH [m.content]",
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
                    # A failed commit (a constraint violation, say) already
                    # closes the transaction. Rolling back a closed
                    # transaction raises its own DriverError, which would
                    # mask the real failure below instead of surfacing it as
                    # a RepositoryError.
                    if not tx.closed():
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
