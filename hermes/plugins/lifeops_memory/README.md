# LifeOps Memory Provider for Hermes Agent

A thin [Hermes memory provider plugin](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers)
backed by LifeOps Core. Hermes recalls and stores memory through the LifeOps
HTTP memory API; NornicDB holds the data. This plugin keeps **no memory of its
own** — BUILD_SPEC §43 forbids a second memory database or a second domain
model in the provider.

```text
Hermes → LifeOpsMemoryProvider → LifeOps memory API → NornicDB
```

## What it does

| Hermes calls | Plugin does |
|---|---|
| `prefetch(query)` / `queue_prefetch(query)` | `GET /api/v1/memory/search?q=…`, formats results for context injection |
| `sync_turn(user, assistant)` | `POST /api/v1/memory` as `type=episodic, source_type=conversation` (background thread, non-blocking) |
| `on_memory_write(action, target, content)` | Mirrors built-in MEMORY.md/USER.md writes as `type=semantic, source_type=agent` |
| `on_session_end(messages)` | Stores one `type=summary` conversational digest |
| Tools: `lifeops_remember`, `lifeops_search`, `lifeops_recent`, `lifeops_forget` | `POST /memory`, `GET /memory/search`, `GET /memory`, `POST /memory/{id}/invalidate` |

Safety, enforced in the plugin and again on the server (BUILD_SPEC §44–§47):

- Memory only ever **observes** — no code path here approves actions, consumes
  approvals, touches payments/idempotency, or grants authority.
- Content matching credential patterns (private keys, `sk-…`, `password = …`,
  Bearer tokens, AWS keys) is refused **before** any network call (§47).
- Automatic turn sync never claims `user_explicit` provenance; only the
  `lifeops_remember` tool can, per the §46 trust hierarchy.
- If LifeOps is unreachable the provider degrades to empty context / no-op
  writes / `{"ok": false, "error": "lifeops_unavailable"}` — Hermes never
  stalls or crashes because LifeOps is down. Transport errors retry with
  exponential backoff (2 retries) before degrading.

## Interface provenance

The implemented interface is the `MemoryProvider` ABC from
`agent/memory_provider.py`, documented at
<https://hermes-agent.nousresearch.com/docs/developer-guide/memory-provider-plugin>
(fetched 2026-08-16): required `name`, `is_available()`, `initialize()`,
`get_tool_schemas()`, `handle_tool_call()`, `get_config_schema()`,
`save_config()`; optional `system_prompt_block()`, `prefetch()`,
`queue_prefetch()`, `sync_turn()`, `on_session_end()`, `on_memory_write()`,
`shutdown()`; registration via `register(ctx)` →
`ctx.register_memory_provider(...)`. The shape (non-blocking `sync_turn` via
daemon thread, background prefetch consumed by the next turn, JSON-string tool
returns) follows the bundled Honcho provider,
`plugins/memory/honcho/` in <https://github.com/NousResearch/hermes-agent>,
the closest documented analogue.

## Install

Hermes is **not installed on this machine** — this plugin has been validated
against the documented interface and a stub HTTP server only, never against a
live Hermes runtime. On the machine that runs Hermes:

```bash
mkdir -p ~/.hermes/plugins/lifeops
cp -r hermes/plugins/lifeops_memory/* ~/.hermes/plugins/lifeops/
```

Then select the provider in `~/.hermes/config.yaml`:

```yaml
memory:
  provider: lifeops
```

or run `hermes memory setup` and pick `lifeops`. The setup wizard prompts for
`base_url` and `client_id` (both have working defaults) and writes
`~/.hermes/lifeops-memory.json`.

## Configuration

Resolution order: environment → `$HERMES_HOME/lifeops-memory.json` → defaults.

| Key | Env var | Default | Meaning |
|---|---|---|---|
| `base_url` | `LIFEOPS_API_URL` | `http://127.0.0.1:8080` | LifeOps Core API |
| `client_id` | `LIFEOPS_CLIENT_ID` | `hermes-personal` | Capability identity (see SECURITY.md) |
| `timeout_seconds` | `LIFEOPS_MEMORY_TIMEOUT` | `2.0` | Per-request timeout |

The plugin declares its identity with the `X-LifeOps-Client` header — the same
mechanism LifeOps Core's HTTP API uses (`get_client` in
`core/lifeops/api/http.py`). There are no secrets to configure; LifeOps is a
loopback service and memory never contains credentials.

## Tests

```bash
.venv/bin/python -m pytest hermes/plugins/lifeops_memory/tests/ -q
```

25 tests against a stub HTTP server (no real Hermes, no real LifeOps): each
interface method's API mapping, the `hermes-personal` identity header, retry
after dropped connections, secret refusal, and clean degradation when LifeOps
is unreachable. Dependencies (`httpx`, `pytest`) are already in the repo's
`.venv`; see `requirements-test.txt`. Nothing here is added to the core
project's `pyproject.toml`.

## Not done / honest status

- **Never loaded by a real Hermes.** The `register(ctx)` path, tool
  registration, and hook wiring are implemented to the documented contract
  but unexercised against the runtime. First live check on a Hermes host:
  `hermes plugins doctor ~/.hermes/plugins/lifeops --ci`, then
  `hermes memory status`.
- Memory type vocabulary matches the landed LifeOps domain
  (`core/lifeops/domain/memory.py`): `semantic`, `preference_candidate`,
  `episodic`, `association`, `summary`. Invalidation requires a `reason`,
  which becomes part of the record's history — the `lifeops_forget` tool
  enforces this client-side.
- No `cli.py` (`hermes lifeops status`) yet — optional per the developer
  guide, deliberately omitted to keep the plugin thin.
