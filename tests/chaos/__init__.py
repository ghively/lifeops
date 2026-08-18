"""Failure/chaos tests (BUILD_SPEC section 86).

See ``tests/chaos/test_outbox_and_transport_failures.py``,
``tests/chaos/test_provider_adapter_failures.py``, and
``tests/chaos/test_documented_gaps.py`` for the 16 numbered scenarios;
scenario 6 (duplicate MCP request) needs a live NornicDB and a real MCP
subprocess, so it lives in ``tests/e2e/test_chaos_duplicate_mcp_request.py``
alongside the other real-subprocess chaos coverage (Nornic restart, Hermes
restart) instead.
"""
