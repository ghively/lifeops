"""Stub LifeOps HTTP server for plugin tests.

No real Hermes, no real LifeOps: a ThreadingHTTPServer records every request
and answers with canned shapes, so tests prove each provider method maps to
the right API call and degrades cleanly on connection errors.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

# Repo root on sys.path so the plugin imports as a package; hermes/, plugins/
# are namespace packages. The plugin never depends on the core project.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from hermes.plugins.lifeops_memory import LifeOpsMemoryProvider  # noqa: E402


class _StubState:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.attempts = 0  # counts connection-level attempts (incl. dropped)
        self.drop_next = False  # close the next connection without answering
        self.search_results: list[dict[str, Any]] = []
        self.search_raw_list = False  # answer search with a bare list
        self.memories: list[dict[str, Any]] = []
        self.fail_status: int | None = None  # answer everything with this


def _make_handler(state: _StubState):
    class StubHandler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:  # keep test output quiet
            pass

        def _handle(self) -> None:
            state.attempts += 1
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            if state.drop_next:
                state.drop_next = False
                self.connection.close()
                return
            body = None
            if raw:
                try:
                    body = json.loads(raw)
                except ValueError:
                    body = None
            state.requests.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "client_header": self.headers.get("X-LifeOps-Client"),
                    "body": body,
                }
            )
            if state.fail_status:
                self._reply(state.fail_status, {"error": "repository_error"})
                return
            status, payload = self._route(body)
            self._reply(status, payload)

        def _route(self, body: Any) -> tuple[int, Any]:
            path = self.path.split("?")[0]
            if self.command == "POST" and path == "/api/v1/memory":
                memory = {"id": f"mem-{len(state.memories) + 1}", **(body or {})}
                state.memories.append(memory)
                return 201, memory
            if self.command == "GET" and path == "/api/v1/memory/search":
                if state.search_raw_list:
                    return 200, state.search_results
                return 200, {
                    "memories": state.search_results,
                    "total": len(state.search_results),
                }
            if self.command == "GET" and path == "/api/v1/memory":
                return 200, {"memories": state.memories, "total": len(state.memories)}
            if self.command == "POST" and path.startswith("/api/v1/memory/"):
                memory_id = path.rsplit("/", 2)[-2]
                return 200, {"id": memory_id, "valid_to": "2026-08-16T00:00:00Z"}
            return 404, {"error": "not_found"}

        def _reply(self, status: int, payload: Any) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = _handle
        do_POST = _handle

    return StubHandler


@pytest.fixture()
def stub_server(monkeypatch: pytest.MonkeyPatch):
    state = _StubState()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("LIFEOPS_API_URL", f"http://127.0.0.1:{server.server_port}")
    yield state
    server.shutdown()
    server.server_close()


@pytest.fixture()
def provider(stub_server: _StubState, tmp_path):
    p = LifeOpsMemoryProvider()
    p.initialize(session_id="test-session", hermes_home=str(tmp_path))
    yield p
    p.shutdown()


def join_background(p: LifeOpsMemoryProvider, timeout: float = 5.0) -> None:
    """Wait for sync/prefetch threads the provider spawned."""
    for thread in (p._sync_thread, p._prefetch_thread, p._mirror_thread):
        if thread and thread.is_alive():
            thread.join(timeout=timeout)


def posts(state: _StubState, path_prefix: str = "/api/v1/memory") -> list[dict]:
    return [
        r
        for r in state.requests
        if r["method"] == "POST" and r["path"].startswith(path_prefix)
    ]
