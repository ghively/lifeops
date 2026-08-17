"""Phase 0 exit test (BUILD_SPEC section 109).

Proves the spine:

    agent client -> LifeOps MCP -> LifeOps Core -> NornicDB

Every MCP session below is a real subprocess speaking the real protocol over
stdio, so "kill that session" means the process actually dies. Nothing is
shared between sessions except NornicDB, which is the point: if state survived
because it sat in a Python object, these tests would pass while the
architecture was wrong.

Note on the Hermes client: this repository does not contain the user's Hermes
runtime. These sessions connect with ``--client hermes-personal``, which is
exactly the identity and interface Hermes uses; what is exercised is the
LifeOps side of that contract. See HERMES_INTEGRATION.md.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession, StdioServerParameters, stdio_client

from lifeops.policy import resolve_client

pytestmark = [pytest.mark.integration, pytest.mark.persistence]

REPO_ROOT = Path(__file__).resolve().parents[2]

HERMES = "hermes-personal"
SECOND_CLIENT = "claude-code"

PREFERENCE_KEY = "scheduling.earliest_appointment_time"
PREFERENCE_VALUE = "I don't like appointments before ten."
TASK_TITLE = "Call dentist"


def _server_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("LIFEOPS_NORNIC_PASSWORD", os.environ.get("LIFEOPS_NORNIC_PASSWORD", ""))
    env["LIFEOPS_LOG_LEVEL"] = "WARNING"
    return env


@asynccontextmanager
async def mcp_session(client_id: str) -> AsyncIterator[ClientSession]:
    """Launch a fresh LifeOps MCP server subprocess and connect to it.

    Leaving this context terminates the subprocess — that is how the test
    "kills the session".
    """
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "lifeops.mcp.server", "--client", client_id],
        env=_server_env(),
        cwd=str(REPO_ROOT),
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        yield session


def _payload(result: Any) -> dict[str, Any]:
    """Extract the tool's JSON result."""
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        # MCPServer wraps a non-object return under "result".
        return structured.get("result", structured)
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            return json.loads(text)
    raise AssertionError(f"no payload in tool result: {result!r}")


async def _call(session: ClientSession, tool: str, **arguments: Any) -> dict[str, Any]:
    return _payload(await session.call_tool(tool, arguments or None))


@pytest.fixture(scope="module", autouse=True)
def require_nornic() -> None:
    import socket

    uri = os.environ.get("LIFEOPS_NORNIC_URI", "bolt://127.0.0.1:7687")
    host, _, port = uri.rsplit("/", 1)[-1].partition(":")
    try:
        with socket.create_connection((host, int(port or 7687)), timeout=3):
            pass
    except OSError:
        pytest.skip(f"NornicDB is not reachable at {uri}")


@pytest.fixture(autouse=True)
async def clean_state() -> AsyncIterator[None]:
    """Remove anything this test wrote, before and after."""
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


class TestToolSurface:
    """BUILD_SPEC sections 49–51: the tool surface grows only by phase.

    Phase 0 pinned exactly five tools; Phase 2 adds the three memory tools.
    The assertion stays exact so a tool can never slip in unreviewed.
    """

    async def test_exactly_the_sanctioned_tools(self) -> None:
        async with mcp_session(HERMES) as session:
            tools = {tool.name for tool in (await session.list_tools()).tools}
        assert tools == {
            # Phase 0 (section 49)
            "get_person",
            "get_preferences",
            "save_preference",
            "create_task",
            "list_tasks",
            # Phase 2 (section 91)
            "search_memory",
            "remember",
            "invalidate_memory",
        }

    async def test_no_raw_database_tool_is_exposed(self) -> None:
        # BUILD_SPEC section 7: agents work in domain concepts, not graph ones.
        async with mcp_session(HERMES) as session:
            tools = {tool.name for tool in (await session.list_tools()).tools}
        forbidden = {
            "run_cypher",
            "create_node",
            "delete_relationship",
            "raw_vector_search",
            "set_property",
            "do_action",
            "execute_anything",
        }
        assert not (tools & forbidden)


class TestPhase0ExitCriteria:
    async def test_a_through_c_preference_survives_the_session_that_wrote_it(
        self,
    ) -> None:
        # A. Hermes stores the preference.
        async with mcp_session(HERMES) as session:
            saved = await _call(
                session,
                "save_preference",
                key=PREFERENCE_KEY,
                value=PREFERENCE_VALUE,
                source_type="user_explicit",
            )
            assert saved["ok"] is True, saved

        # B. That session is now dead — the subprocess exited above.
        # C. A brand-new session reads it back.
        async with mcp_session(HERMES) as session:
            result = await _call(session, "get_preferences")

        values = {p["key"]: p["value"] for p in result["preferences"]}
        assert values[PREFERENCE_KEY] == PREFERENCE_VALUE

    async def test_e_second_client_reads_the_same_preference(self) -> None:
        async with mcp_session(HERMES) as session:
            await _call(
                session,
                "save_preference",
                key=PREFERENCE_KEY,
                value=PREFERENCE_VALUE,
            )

        # E. A different client identity, a different process, the same state.
        async with mcp_session(SECOND_CLIENT) as session:
            result = await _call(session, "get_preferences")

        values = {p["key"]: p["value"] for p in result["preferences"]}
        assert values[PREFERENCE_KEY] == PREFERENCE_VALUE

    async def test_f_and_g_second_client_creates_a_task_hermes_lists_it(self) -> None:
        # F. The second client creates the task.
        async with mcp_session(SECOND_CLIENT) as session:
            created = await _call(session, "create_task", title=TASK_TITLE)
            assert created["ok"] is True, created
            task_id = created["task"]["id"]

        # G. Hermes lists the same task.
        async with mcp_session(HERMES) as session:
            listed = await _call(session, "list_tasks")

        by_id = {t["id"]: t for t in listed["tasks"]}
        assert task_id in by_id
        assert by_id[task_id]["title"] == TASK_TITLE

    async def test_shared_state_flows_in_both_directions(self) -> None:
        """BUILD_SPEC section 102 — state belongs to LifeOps, not to an agent."""
        async with mcp_session(HERMES) as session:
            await _call(
                session,
                "save_preference",
                key=PREFERENCE_KEY,
                value=PREFERENCE_VALUE,
            )

        async with mcp_session(SECOND_CLIENT) as session:
            prefs = await _call(session, "get_preferences")
            assert any(
                p["value"] == PREFERENCE_VALUE for p in prefs["preferences"]
            )
            await _call(session, "create_task", title=TASK_TITLE)

        async with mcp_session(HERMES) as session:
            tasks = await _call(session, "list_tasks")
            assert any(t["title"] == TASK_TITLE for t in tasks["tasks"])

    async def test_h_console_sees_the_same_task_state(self) -> None:
        """H. LifeOps Console displays the same Task state."""
        async with mcp_session(SECOND_CLIENT) as session:
            created = await _call(session, "create_task", title=TASK_TITLE)
            task_id = created["task"]["id"]

        # The Console reads through LifeOps Core's HTTP API, which is a
        # different process boundary from MCP but the same database.
        import httpx
        from asgi_lifespan import LifespanManager

        from lifeops.api.http import create_app

        app = create_app()
        async with LifespanManager(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://lifeops.test"
            ) as client:
                response = await client.get(f"/api/v1/tasks/{task_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["title"] == TASK_TITLE
        assert body["state"] == "CAPTURED"
        assert body["created_by_client"] == SECOND_CLIENT

    async def test_capability_manifest_holds_across_the_mcp_boundary(self) -> None:
        """The coding client must not be able to rewrite the user's preferences."""
        async with mcp_session(SECOND_CLIENT) as session:
            result = await _call(
                session,
                "save_preference",
                key=PREFERENCE_KEY,
                value="whatever it likes",
            )

        assert result["ok"] is False
        assert result["error"] == "capability_denied"

        # And nothing was written.
        async with mcp_session(HERMES) as session:
            prefs = await _call(session, "get_preferences")
        assert not any(
            p["key"] == PREFERENCE_KEY for p in prefs["preferences"]
        )

    async def test_unknown_client_identity_is_refused_at_launch(self) -> None:
        # A typo in a launch config should be loud, not a silent downgrade.
        result = subprocess.run(
            [sys.executable, "-m", "lifeops.mcp.server", "--client", "not-a-real-client"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env=_server_env(),
            timeout=60,
            input="",
        )
        assert result.returncode != 0
        assert "unknown client identity" in (result.stderr + result.stdout).lower()


class TestNoParallelSourceOfTruth:
    """BUILD_SPEC exit test I."""

    def test_no_prohibited_datastore_is_a_runtime_dependency(self) -> None:
        prohibited = {
            "sqlalchemy",
            "alembic",
            "qdrant-client",
            "qdrant_client",
            "redis",
            "neo4j-driver",
            "psycopg2",
            "psycopg",
            "asyncpg",
            "temporalio",
            "kafka-python",
            "pika",
        }
        text = (REPO_ROOT / "pyproject.toml").read_text()
        # The neo4j *driver* is how LifeOps speaks Bolt to NornicDB, which is
        # the sanctioned transport; a Neo4j *server* is what is prohibited.
        dependencies = text.split("[project.optional-dependencies]")[0]
        for name in prohibited:
            assert name not in dependencies, f"{name} must not be a LifeOps dependency"

    def test_lifeops_imports_no_prohibited_client_library(self) -> None:
        import lifeops  # noqa: F401

        forbidden = {"sqlite3", "sqlalchemy", "qdrant_client", "redis", "psycopg2"}
        loaded = forbidden & set(sys.modules)
        assert not loaded, f"LifeOps pulled in {loaded}"

    def test_no_sqlite_or_qdrant_file_lives_in_the_lifeops_state_directory(
        self,
    ) -> None:
        from lifeops.settings import Settings

        state_dir = Settings().state_dir
        if not state_dir.exists():
            return
        for path in state_dir.rglob("*"):
            assert path.suffix not in {".db", ".sqlite", ".sqlite3"}, path

    def test_core_package_contains_no_prohibited_import(self) -> None:
        offenders: list[str] = []
        for path in (REPO_ROOT / "core" / "lifeops").rglob("*.py"):
            text = path.read_text()
            for name in ("import sqlite3", "import qdrant_client", "import redis"):
                if name in text:
                    offenders.append(f"{path}: {name}")
        assert not offenders


class TestFreshDeploymentNeedsNoCredentials:
    """BUILD_SPEC exit test J and section 104."""

    async def test_console_api_serves_with_every_provider_unconfigured(
        self, tmp_path: Path
    ) -> None:
        import httpx
        from asgi_lifespan import LifespanManager

        from lifeops.api.http import create_app
        from lifeops.container import Container
        from lifeops.settings import Settings

        # A pristine state directory: no secrets, no configuration document.
        settings = Settings(
            state_dir=tmp_path / "fresh",
            nornic_password=os.environ.get("LIFEOPS_NORNIC_PASSWORD", ""),
        )
        app = create_app(container=Container(settings), settings=settings)

        async with LifespanManager(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://lifeops.test"
            ) as client:
                assert (await client.get("/health")).status_code == 200

                providers = (await client.get("/api/v1/config/providers")).json()
                for entry in providers["providers"]:
                    assert entry["status"]["state"] in {"not_configured", "disabled"}

                # The Console's main screens answer without any provider set up.
                assert (await client.get("/api/v1/tasks")).status_code == 200
                assert (await client.get("/api/v1/people/me")).status_code == 200
                assert (await client.get("/api/v1/system/status")).status_code == 200

    def test_no_credential_is_committed_to_the_repository(self) -> None:
        # The coding agent never holds a runtime credential (section 88).
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True
        ).stdout.split()
        assert "core/lifeops" in " ".join(tracked) or tracked, "git ls-files failed"
        for name in tracked:
            assert not name.endswith("master.key"), name
            assert "secrets.json" not in name, name


@pytest.mark.skipif(
    shutil.which("systemctl") is None and not os.environ.get("LIFEOPS_NORNIC_RESTART_CMD"),
    reason="no way to restart NornicDB in this environment",
)
class TestNornicRestart:
    """BUILD_SPEC exit test D — state survives a database restart.

    Driven by ``LIFEOPS_NORNIC_RESTART_CMD``. When no restart mechanism is
    available the test skips rather than silently asserting nothing.
    """

    async def test_a_long_lived_core_reconnects_after_a_restart(self) -> None:
        """BUILD_SPEC section 86: a Nornic restart must not require restarting
        LifeOps Core.

        A long-lived Core holds a connection pool. If it did not recover, every
        database restart would need a manual Core restart too, and the failure
        would look like data loss to the user.
        """
        restart = os.environ.get("LIFEOPS_NORNIC_RESTART_CMD")
        if not restart:
            pytest.skip("set LIFEOPS_NORNIC_RESTART_CMD to exercise this")

        from lifeops.container import Container
        from lifeops.settings import Settings

        container = Container(Settings())
        await container.startup()
        try:
            assert await container.nornic.ping()

            subprocess.run(restart, shell=True, check=True, timeout=180)

            # The driver reconnects on demand; allow a few attempts for the
            # server to finish accepting connections.
            for _ in range(10):
                if await container.nornic.ping():
                    break
                await asyncio.sleep(1)
            else:
                pytest.fail("LifeOps Core did not reconnect after a Nornic restart")

            # And it can still read, not merely open a socket.
            people = await container.core.list_people(
                resolve_client(HERMES), limit=1
            )
            assert isinstance(people, list)
        finally:
            await container.shutdown()

    async def test_preference_survives_a_nornic_restart(self) -> None:
        restart = os.environ.get("LIFEOPS_NORNIC_RESTART_CMD")
        if not restart:
            pytest.skip("set LIFEOPS_NORNIC_RESTART_CMD to exercise this")

        async with mcp_session(HERMES) as session:
            await _call(
                session,
                "save_preference",
                key=PREFERENCE_KEY,
                value=PREFERENCE_VALUE,
            )

        subprocess.run(restart, shell=True, check=True, timeout=180)

        async with mcp_session(HERMES) as session:
            result = await _call(session, "get_preferences")

        values = {p["key"]: p["value"] for p in result["preferences"]}
        assert values[PREFERENCE_KEY] == PREFERENCE_VALUE
