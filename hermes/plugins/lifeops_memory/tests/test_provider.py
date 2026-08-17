"""Provider↔API mapping and graceful-degradation tests.

Every test runs against the stub HTTP server from conftest.py — no real
Hermes, no real LifeOps.
"""

from __future__ import annotations

import json

import pytest
from hermes.plugins.lifeops_memory import LifeOpsMemoryProvider
from hermes.plugins.lifeops_memory.tests.conftest import join_background, posts


def _result(raw: str) -> dict:
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)
    return parsed


# -- identity / lifecycle -----------------------------------------------------


def test_provider_metadata(provider: LifeOpsMemoryProvider) -> None:
    assert provider.name == "lifeops"
    assert provider.is_available() is True
    assert "LifeOps" in provider.system_prompt_block()
    schemas = provider.get_tool_schemas()
    assert {s["name"] for s in schemas} == {
        "lifeops_remember",
        "lifeops_search",
        "lifeops_recent",
        "lifeops_forget",
    }
    cfg_keys = {f["key"] for f in provider.get_config_schema()}
    assert {"base_url", "client_id"} <= cfg_keys


def test_client_identity_header(provider, stub_server) -> None:
    provider.prefetch("anything")
    assert stub_server.requests
    assert stub_server.requests[0]["client_header"] == "hermes-personal"


# -- prefetch / recall --------------------------------------------------------


def test_prefetch_searches_and_formats(provider, stub_server) -> None:
    stub_server.search_results = [
        {
            "id": "mem-1",
            "type": "preference",
            "content": "Appointments after ten only",
            "source_type": "user_explicit",
        }
    ]
    context = provider.prefetch("when should I book the dentist?")
    assert "Appointments after ten only" in context
    assert "preference" in context and "user_explicit" in context
    req = stub_server.requests[0]
    assert req["method"] == "GET"
    assert req["path"].startswith("/api/v1/memory/search?")
    assert "q=when+should+I+book+the+dentist%3F" in req["path"] or "q=" in req["path"]


def test_prefetch_empty_on_no_results(provider, stub_server) -> None:
    assert provider.prefetch("nothing stored here") == ""


def test_prefetch_tolerates_bare_list_response(provider, stub_server) -> None:
    stub_server.search_raw_list = True
    stub_server.search_results = [{"type": "semantic", "content": "Lives in Oslo"}]
    assert "Lives in Oslo" in provider.prefetch("where do they live")


def test_queue_prefetch_feeds_next_prefetch(provider, stub_server) -> None:
    stub_server.search_results = [{"type": "semantic", "content": "Drives a Volvo"}]
    provider.queue_prefetch("what car?")
    join_background(provider)
    before = len(stub_server.requests)
    context = provider.prefetch("what car?")
    assert "Drives a Volvo" in context
    assert len(stub_server.requests) == before  # served from the background fetch


# -- sync_turn -----------------------------------------------------------------


def test_sync_turn_stores_episodic_conversation(provider, stub_server) -> None:
    provider.sync_turn(
        "Remind me the boiler service is due in October",
        "Noted — boiler service due in October.",
        session_id="sess-42",
    )
    join_background(provider)
    stored = posts(stub_server)
    assert len(stored) == 1
    body = stored[0]["body"]
    assert stored[0]["path"] == "/api/v1/memory"
    assert body["type"] == "episodic"
    assert body["source_type"] == "conversation"
    assert body["source_id"] == "sess-42"
    assert "boiler service" in body["content"]


def test_sync_turn_skips_trivial_turns(provider, stub_server) -> None:
    provider.sync_turn("ok", "👍")
    provider.sync_turn("", "")
    join_background(provider)
    assert posts(stub_server) == []


def test_sync_turn_skips_internal_gateway_turns(provider, stub_server) -> None:
    provider.sync_turn("[CONTEXT SUMMARY]: compacted 12 turns", "Understood.")
    join_background(provider)
    assert posts(stub_server) == []


def test_sync_turn_never_stores_secrets(provider, stub_server) -> None:
    provider.sync_turn("my password = hunter2", "I won't store that.")
    join_background(provider)
    assert posts(stub_server) == []


# -- session end / mirror ------------------------------------------------------


def test_session_end_stores_summary(provider, stub_server) -> None:
    provider.on_session_end(
        [
            {"role": "user", "content": "The car insurance renews in March."},
            {"role": "assistant", "content": "Renewal noted for March."},
        ]
    )
    stored = posts(stub_server)
    assert len(stored) == 1
    assert stored[0]["body"]["type"] == "summary"
    assert stored[0]["body"]["source_type"] == "conversation"
    assert "car insurance" in stored[0]["body"]["content"]


def test_session_end_skips_empty_session(provider, stub_server) -> None:
    provider.on_session_end([{"role": "user", "content": "hi"}])
    provider.on_session_end([])
    assert posts(stub_server) == []


def test_memory_write_mirrors_builtin_memory(provider, stub_server) -> None:
    provider.on_memory_write("update", "USER.md", "Prefers concise answers")
    join_background(provider)
    stored = posts(stub_server)
    assert len(stored) == 1
    body = stored[0]["body"]
    assert body["source_type"] == "agent"
    assert body["source_id"] == "USER.md"
    assert "Prefers concise answers" in body["content"]


def test_memory_write_ignores_reads(provider, stub_server) -> None:
    provider.on_memory_write("read", "MEMORY.md", "whatever")
    join_background(provider)
    assert posts(stub_server) == []


# -- tools ---------------------------------------------------------------------


def test_remember_tool_posts_memory(provider, stub_server) -> None:
    result = _result(
        provider.handle_tool_call(
            "lifeops_remember",
            {
                "content": "Prefers morning appointments",
                "type": "preference_candidate",
                "source_type": "user_explicit",
            },
        )
    )
    assert result["ok"] is True
    assert result["memory"]["id"].startswith("mem-")
    body = posts(stub_server)[0]["body"]
    assert body["content"] == "Prefers morning appointments"
    assert body["type"] == "preference_candidate"
    assert body["source_type"] == "user_explicit"


def test_remember_tool_refuses_secrets(provider, stub_server) -> None:
    result = _result(
        provider.handle_tool_call(
            "lifeops_remember", {"content": "api_key = sk-abcdefghijklmnopqrstuvwxyz"}
        )
    )
    assert result == {
        "ok": False,
        "error": "secret_refused",
        "detail": "Memory never stores credentials (BUILD_SPEC §47).",
    }
    assert posts(stub_server) == []  # refused before any network call


def test_search_tool(provider, stub_server) -> None:
    stub_server.search_results = [{"id": "mem-9", "content": "Dentist: Dr. Berg"}]
    result = _result(provider.handle_tool_call("lifeops_search", {"query": "dentist"}))
    assert result["ok"] is True
    assert result["memories"][0]["id"] == "mem-9"
    req = stub_server.requests[0]
    assert req["path"].startswith("/api/v1/memory/search?")


def test_recent_tool(provider, stub_server) -> None:
    provider.handle_tool_call("lifeops_remember", {"content": "fact one"})
    result = _result(provider.handle_tool_call("lifeops_recent", {"limit": 5}))
    assert result["ok"] is True
    assert result["total"] == 1
    paths = [r["path"] for r in stub_server.requests]
    assert "/api/v1/memory?limit=5" in paths


def test_forget_tool_invalidates(provider, stub_server) -> None:
    result = _result(
        provider.handle_tool_call(
            "lifeops_forget", {"memory_id": "mem-7", "reason": "user corrected it"}
        )
    )
    assert result["ok"] is True
    assert result["memory"]["id"] == "mem-7"
    req = stub_server.requests[0]
    assert req["path"] == "/api/v1/memory/mem-7/invalidate"
    assert req["body"] == {"reason": "user corrected it"}


def test_unknown_tool(provider) -> None:
    assert _result(provider.handle_tool_call("nope", {}))["error"] == "unknown_tool"


def test_tool_requires_arguments(provider) -> None:
    assert _result(provider.handle_tool_call("lifeops_remember", {}))["error"] == (
        "invalid_arguments"
    )
    assert _result(provider.handle_tool_call("lifeops_forget", {}))["error"] == (
        "invalid_arguments"
    )


# -- degradation ---------------------------------------------------------------


@pytest.fixture()
def dead_provider(stub_server, tmp_path, monkeypatch):
    """Provider pointed at a port nothing listens on."""
    monkeypatch.setenv("LIFEOPS_API_URL", "http://127.0.0.1:1")
    p = LifeOpsMemoryProvider()
    p.initialize(session_id="dead", hermes_home=str(tmp_path))
    yield p
    p.shutdown()


def test_degrades_when_lifeops_unreachable(dead_provider) -> None:
    assert dead_provider.prefetch("anything") == ""
    result = _result(dead_provider.handle_tool_call("lifeops_search", {"query": "x"}))
    assert result["ok"] is False
    assert result["error"] == "lifeops_unavailable"
    dead_provider.sync_turn("a real question with substance", "a substantive answer")
    dead_provider.on_session_end(
        [
            {"role": "user", "content": "something durable"},
            {"role": "assistant", "content": "recorded"},
        ]
    )
    join_background(dead_provider)  # must not raise


def test_retries_after_dropped_connection(provider, stub_server) -> None:
    stub_server.drop_next = True
    result = _result(provider.handle_tool_call("lifeops_remember", {"content": "fact"}))
    assert result["ok"] is True
    assert stub_server.attempts == 2  # dropped once, retried, succeeded


def test_http_error_surfaces_stable_code(provider, stub_server) -> None:
    stub_server.fail_status = 503
    result = _result(provider.handle_tool_call("lifeops_search", {"query": "x"}))
    assert result["ok"] is False
    assert result["error"] == "lifeops_error"
    assert result["status"] == 503
    assert result["detail"] == "repository_error"


def test_uninitialized_provider_degrades(tmp_path) -> None:
    p = LifeOpsMemoryProvider()  # initialize() never called
    assert p.prefetch("x") == ""
    p.sync_turn("user says something substantial", "assistant answers at length")
    p.on_session_end([])
    assert _result(p.handle_tool_call("lifeops_search", {"query": "x"}))["error"] == (
        "lifeops_unavailable"
    )
