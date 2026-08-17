"""Phase 4 acceptance test (BUILD_SPEC section 93).

Section 93's criterion is that durable work — a task, and a waiting item
recording that the task is blocked on someone else — survives:

  * conversation exit    (a new MCP session sees it)
  * Hermes restart        (the MCP subprocess is killed and relaunched)
  * LifeOps restart       (a fresh Container/HTTP app reads it, not a cached
                           Python object inside one LifeOps Core instance)
  * a NornicDB restart    (reusing tests/e2e/test_phase0_exit.py's mechanism)

Every MCP session below is a real subprocess speaking the real protocol over
stdio, exactly as the Phase 0 suite does: nothing is shared between sessions
except NornicDB, which is the point.

This suite also carries a handful of tool-contract checks for the two tools
Phase 4 adds — ``create_waiting_item`` and ``update_task`` — ahead of the
survival tests that depend on them behaving correctly.
"""

from __future__ import annotations

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

pytestmark = [pytest.mark.integration, pytest.mark.persistence]

REPO_ROOT = Path(__file__).resolve().parents[2]

HERMES = "hermes-personal"
#: The due-work worker reads and updates tasks; it never originates one
#: (BUILD_SPEC section 55), so it holds no CREATE_TASK grant either.
WORKER = "lifeops-worker"

TASK_TITLE = "Phase4 durable work: get the roof quoted"
WAITING_SUBJECT = "Phase4 durable work: waiting on ABC Roofing for a quote"


def _server_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("LIFEOPS_NORNIC_PASSWORD", os.environ.get("LIFEOPS_NORNIC_PASSWORD", ""))
    env["LIFEOPS_LOG_LEVEL"] = "WARNING"
    return env


@asynccontextmanager
async def mcp_session(client_id: str) -> AsyncIterator[ClientSession]:
    """Launch a fresh LifeOps MCP server subprocess and connect to it.

    Leaving this context terminates the subprocess. Opening a new one after
    that is how a test simulates a conversation ending, or Hermes itself
    restarting: there is no Python object shared between the two sessions,
    only NornicDB.
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


async def _create_task_and_waiting_item(session: ClientSession) -> tuple[str, str]:
    """Capture a task, then record that it is blocked on someone else."""
    created = await _call(session, "create_task", title=TASK_TITLE)
    assert created["ok"] is True, created
    task_id = created["task"]["id"]

    waited = await _call(
        session,
        "create_waiting_item",
        task_id=task_id,
        subject=WAITING_SUBJECT,
        max_followups=2,
    )
    assert waited["ok"] is True, waited
    return task_id, waited["waiting_item"]["id"]


async def _get_waiting_item_via_http(waiting_id: str) -> dict[str, Any]:
    """Read the waiting item back through LifeOps Core's HTTP API.

    A different process boundary than MCP, over the same NornicDB — the same
    cross-check tests/e2e/test_phase0_exit.py runs for tasks (exit test H).
    There is no MCP read tool for a single waiting item (list_waiting stays a
    resource, section 48), so this is the honest way to confirm persistence
    independent of the writing session.
    """
    import httpx
    from asgi_lifespan import LifespanManager

    from lifeops.api.http import create_app

    app = create_app()
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://lifeops.test"
        ) as client:
            response = await client.get(f"/api/v1/waiting/{waiting_id}")
    assert response.status_code == 200, response.text
    return response.json()


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
    """Remove anything this suite wrote, before and after each test."""
    from lifeops.repositories.nornic.client import NornicClient
    from lifeops.settings import Settings

    async def purge() -> None:
        client = NornicClient(Settings())
        await client.connect()
        try:
            await client.write(
                "MATCH (w:WaitingItem) WHERE w.subject = $subject DETACH DELETE w",
                subject=WAITING_SUBJECT,
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


class TestToolContracts:
    """The two tools behave as their descriptions promise, ahead of the
    survival tests below that depend on them."""

    async def test_create_waiting_item_records_a_wait(self) -> None:
        async with mcp_session(HERMES) as session:
            task_id, waiting_id = await _create_task_and_waiting_item(session)
        assert task_id
        assert waiting_id

    async def test_create_waiting_item_for_a_nonexistent_task_is_not_found(self) -> None:
        async with mcp_session(HERMES) as session:
            result = await _call(
                session,
                "create_waiting_item",
                task_id="task_does_not_exist",
                subject=WAITING_SUBJECT,
            )
        assert result["ok"] is False
        assert result["error"] == "not_found"

    async def test_a_client_without_create_task_may_not_create_a_waiting_item(
        self,
    ) -> None:
        async with mcp_session(HERMES) as session:
            created = await _call(session, "create_task", title=TASK_TITLE)
            task_id = created["task"]["id"]

        async with mcp_session(WORKER) as session:
            result = await _call(
                session,
                "create_waiting_item",
                task_id=task_id,
                subject=WAITING_SUBJECT,
            )
        assert result["ok"] is False
        assert result["error"] == "capability_denied"

    async def test_update_task_moves_a_legal_transition(self) -> None:
        async with mcp_session(HERMES) as session:
            created = await _call(session, "create_task", title=TASK_TITLE)
            task_id = created["task"]["id"]
            updated = await _call(session, "update_task", task_id=task_id, state="READY")
        assert updated["ok"] is True, updated
        assert updated["task"]["state"] == "READY"

    async def test_update_task_rejects_an_illegal_transition(self) -> None:
        async with mcp_session(HERMES) as session:
            created = await _call(session, "create_task", title=TASK_TITLE)
            task_id = created["task"]["id"]
            result = await _call(session, "update_task", task_id=task_id, state="COMPLETED")
        assert result["ok"] is False
        assert result["error"] == "invalid_transition"


class TestPhase4Acceptance:
    """BUILD_SPEC section 93 — work survives conversation exit, Hermes
    restart, LifeOps restart, and a NornicDB restart."""

    async def test_conversation_exit_new_session_sees_the_waiting_item(self) -> None:
        # A. Hermes records the task and the wait.
        async with mcp_session(HERMES) as session:
            task_id, waiting_id = await _create_task_and_waiting_item(session)
        # B. That session is now dead — the subprocess exited above.

        # C. A brand-new session sees the task.
        async with mcp_session(HERMES) as session:
            tasks = await _call(session, "list_tasks")
        assert any(t["id"] == task_id for t in tasks["tasks"])

        # And the waiting item it created is still there.
        body = await _get_waiting_item_via_http(waiting_id)
        assert body["task_id"] == task_id
        assert body["subject"] == WAITING_SUBJECT

    async def test_hermes_restart_new_subprocess_still_sees_the_work(self) -> None:
        """Not merely a new session object — an entirely new subprocess,
        launched independently of the one that wrote the data, which by then
        is fully dead. This is what "Hermes restarts" means mechanically."""
        async with mcp_session(HERMES) as session:
            task_id, waiting_id = await _create_task_and_waiting_item(session)

        async with mcp_session(HERMES) as session:
            updated = await _call(
                session,
                "update_task",
                task_id=task_id,
                current_action="checked after restart",
            )
        assert updated["ok"] is True, updated
        assert updated["task"]["current_action"] == "checked after restart"

        body = await _get_waiting_item_via_http(waiting_id)
        assert body["id"] == waiting_id
        assert body["task_id"] == task_id

    async def test_lifeops_restart_fresh_container_reads_the_same_state(self) -> None:
        """A fresh Container, built by this test and never touched by the
        session that wrote the data, must read it back. Proves the state
        lives in NornicDB rather than in a cached Python object inside one
        LifeOps Core instance (BUILD_SPEC section 86)."""
        async with mcp_session(HERMES) as session:
            task_id, waiting_id = await _create_task_and_waiting_item(session)

        # One independent read through the HTTP boundary...
        body = await _get_waiting_item_via_http(waiting_id)
        assert body["task_id"] == task_id

        # ...and a second, through a brand-new Container talking to
        # LifeOpsCore directly, with its own connection pool.
        from lifeops.container import Container
        from lifeops.policy import resolve_client
        from lifeops.settings import Settings

        container = Container(Settings())
        await container.startup()
        try:
            item = await container.core.get_waiting_item(
                resolve_client(HERMES), waiting_id=waiting_id
            )
            assert item.task_id == task_id
            assert item.subject == WAITING_SUBJECT

            task = await container.core.get_task(resolve_client(HERMES), task_id=task_id)
            assert task.title == TASK_TITLE
        finally:
            await container.shutdown()


@pytest.mark.skipif(
    shutil.which("systemctl") is None and not os.environ.get("LIFEOPS_NORNIC_RESTART_CMD"),
    reason="no way to restart NornicDB in this environment",
)
class TestNornicRestart:
    """BUILD_SPEC section 93's fourth survival criterion.

    Driven by ``LIFEOPS_NORNIC_RESTART_CMD``, the same mechanism
    tests/e2e/test_phase0_exit.py uses for its Nornic-restart test — skips
    cleanly when no restart command is configured, rather than asserting
    nothing.
    """

    async def test_task_and_waiting_item_survive_a_nornic_restart(self) -> None:
        restart = os.environ.get("LIFEOPS_NORNIC_RESTART_CMD")
        if not restart:
            pytest.skip("set LIFEOPS_NORNIC_RESTART_CMD to exercise this")

        async with mcp_session(HERMES) as session:
            task_id, waiting_id = await _create_task_and_waiting_item(session)

        subprocess.run(restart, shell=True, check=True, timeout=180)

        # A brand-new MCP session and a brand-new HTTP app, both created after
        # the database restart, must see exactly what was written before it.
        async with mcp_session(HERMES) as session:
            tasks = await _call(session, "list_tasks")
        assert any(t["id"] == task_id for t in tasks["tasks"])

        body = await _get_waiting_item_via_http(waiting_id)
        assert body["task_id"] == task_id
        assert body["subject"] == WAITING_SUBJECT
