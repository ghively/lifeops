# Handoff — Hermes LifeOps, Phase 1 onward

**For:** Kimi
**From:** the agent that built Phase 0
**Date:** 2026-08-16
**Branch:** `lifeops/phase-0` · last commit `bd395d9`
**Authority:** [BUILD_SPEC.md](BUILD_SPEC.md) is the spec. When this document
and the spec disagree, the spec wins. This is context, not a second source of
truth.

You are picking up a build that has a proven spine and eleven phases left.
Phase 0 is complete and committed. Nothing else has been started.

---

## 1. Read this first

Read in this order before writing code:

1. `BUILD_SPEC.md` — the whole thing. It is the contract.
2. `AGENTS.md` — the working rules (where code goes, what you may not change).
3. `ARCHITECTURE.md` — why the boundaries are where they are.
4. This document — what I learned that isn't written anywhere else.

Then run the system and poke it before changing it:

```bash
make dev      # NornicDB + LifeOps Core + Console
make health
open http://127.0.0.1:5173
make test     # 164 Python tests
```

---

## 2. What exists right now

### The spine, proven

```
MCP client (Hermes / Claude Code) → LifeOps MCP → LifeOps Core → NornicDB
                                          Console ↗
```

All seventeen Phase 0 exit tests pass, including a real NornicDB restart.

| Piece | State |
|---|---|
| NornicDB v1.2.2 | Built from source, running headless on loopback, persistent |
| LifeOps Core | 39 Python modules, ~5,000 lines |
| MCP server | Exactly 5 tools, per-connection client identity |
| LifeOps Console | Today, Tasks, Configuration, System |
| Tests | 164 Python + 15 Console, lint and typecheck clean |
| Docs | 10 documents at repo root |

### Domains implemented

`Person`, `Preference` (temporal, with supersession), `Task` (11-state machine
with a verification gate). That's it. Everything else in BUILD_SPEC §36 is
unbuilt — deliberately.

### What is scaffolding, not function

Nine providers are registered with full field schemas and render real forms in
the Console — DeepSeek, ElevenLabs, Local TTS, Local ASR, Telegram, Calendar,
Email, Browser, Telephony. **None has an adapter.** `POST
/config/providers/{id}/test` deliberately returns `healthy: false` with "no
adapter yet (arrives in phase N)". Don't mistake the scaffolding for a working
integration, and don't make the Test button lie when you wire one up.

---

## 3. Environment landmines

This box is unusual. Each of these cost me time; none is documented elsewhere.

| Reality | Consequence |
|---|---|
| **No Docker, no podman** | NornicDB is built from Go source via `scripts/build-nornicdb.sh`. `deploy/compose.yaml` exists for Docker hosts but is untested here. |
| **No Go on the box** | The build script downloads a Go 1.26 toolchain into a temp dir. NornicDB needs Go ≥ 1.26. |
| **System Python is 3.14.4 with no `pip` and no `ensurepip`** | `python3 -m venv` fails normally. `make setup-core` works around it with `venv --without-pip` + `get-pip.py`. Don't "fix" it back. |
| **No `uv`, `pipx`, `poetry`** | Plain venv + pip only. |
| **Playwright refuses to install** — "does not support chromium on ubuntu26.04-x64" | No browser e2e is possible here. Console coverage is vitest + live `curl` through the Vite proxy. Phase 9's browser work will need a different host or a non-Playwright driver. |
| **No `nvidia-smi`** | The RTX 3060 is not visible from this environment. Phase 6 (local voice) cannot be validated here. Confirm with the user where the GPU actually lives. |
| **No `sudo`** | Everything installs under `~/.local`. |

### NornicDB gotchas

- **The admin password is written into the data directory at first
  initialisation.** `--admin-password` has no effect on an existing data dir. A
  fresh `nornicdb.env` pointed at existing data fails with `AuthError: Invalid
  credentials`. To change it: NornicDB's admin API, or delete the data dir
  (destructive). This cost me a confusing twenty minutes.
- Build tags are `noui,nolocalllm` (matching upstream's CPU Dockerfile).
  `noui` because LifeOps Console is the only interface we offer; a second admin
  UI on the same data is a second thing to secure.
- Embeddings are **off**. Phase 2 is the first phase with anything to embed.
  When you turn them on, `--embedding-provider` accepts `local|ollama|openai`;
  the `nolocalllm` build has no bundled model, so point it at a provider.
- Bolt is Neo4j-compatible and the `neo4j` Python driver 6.2.0 works against it.
  I verified these Cypher constructs work: `MERGE`, `ON CREATE SET`, `SET +=`,
  `WHERE ... IS NULL`, `OPTIONAL MATCH`, `coalesce`, `IN $list`, `ORDER BY`,
  `SKIP`/`LIMIT`, `WITH`, `DETACH DELETE`, `CREATE CONSTRAINT ... IF NOT
  EXISTS`, `CREATE INDEX`, aggregation, relationship traversal. Don't re-probe.
- A long-lived LifeOps Core **does** reconnect after a NornicDB restart (the
  driver pool handles it). There's a test for this; don't regress it.

### MCP SDK gotcha

The installed `mcp` is **2.0.0**, which is not the API most examples show.

```python
# WRONG — does not exist in mcp 2.0
from mcp.server.fastmcp import FastMCP

# RIGHT
from mcp.server.mcpserver import MCPServer
```

`MCPServer` is the FastMCP successor: `@server.tool()`, `@server.resource(uri)`,
`server.run(transport="stdio"|"sse"|"streamable-http")`.

Tool results come back with the payload under `structuredContent`, and a
non-object return is wrapped under a `result` key. `tests/e2e/test_phase0_exit.py::_payload`
handles both shapes — reuse it.

---

## 4. Invariants you must not break

From BUILD_SPEC §108. If one genuinely has to change: document the concrete
failure, write a proposal in `changes/requests/`, and **stop**. Don't redesign
quietly.

1. **NornicDB is the only application database.** No SQLite, Postgres, Qdrant,
   Neo4j, Redis, Temporal, Kafka. There's a CI check asserting no prohibited
   package is a runtime dependency.
2. **Only LifeOps Core writes to NornicDB.** Not agents, not the Console, not
   integrations.
3. **Cypher lives only in `core/lifeops/repositories/nornic/`.** If a domain
   test needs Cypher to pass, the abstraction has leaked — fix the abstraction,
   not the test.
4. **One application service, two adapters.** All orchestration and capability
   checks live in `core/lifeops/core.py`. `api/http.py` and `mcp/server.py`
   translate shapes and nothing else. A rule added to one adapter silently
   doesn't apply to the other — and MCP is the path no human watches.
5. **Never ask the user for a runtime credential.** Build the adapter, the
   mock, the schema, the Console form, the Test button. Leave it disabled. Keep
   going.
6. **External completion requires evidence.** Never mark a task COMPLETED
   because a model said the thing happened.
7. **Secrets never enter NornicDB**, never appear in an API response, never
   appear in a log.
8. **Hermes is the assistant.** Don't build a second agent, a voice agent, or
   an agent runtime.

### Before adding any dependency

BUILD_SPEC §105 requires you to answer, in writing:

```
Problem:             what concrete failure exists right now?
Existing capability: can Hermes / NornicDB / MCP / a small LifeOps module do it?
Why required:
Operational cost:
Removal plan:
```

No concrete problem → no dependency. This one matters more than it looks; the
spec is reacting to a real failure mode.

---

## 5. Codebase map

```
core/lifeops/
  settings.py       deployment settings only (ports, dirs, DB URI) — NOT provider config
  clock.py          injected time; use FrozenClock in tests, never wall clock
  ids.py            canonical IDs — slug (person_gene) and ULID (task_01j...)
  errors.py         LifeOpsError hierarchy; every error carries a stable `code`
  core.py           ← THE application service. Read this first.
  container.py      composition root
  domain/           models + pure rules. No Cypher, no HTTP, no MCP.
  policy/           capabilities.py (client → capability map), trust.py (source ranking)
  repositories/
    interfaces.py   Protocols the domain depends on
    nornic/         the only Cypher in the codebase
    fakes/          in-memory doubles — the proof the abstraction holds
  api/http.py       Console-facing REST
  mcp/server.py     agent-facing tools
  config/           provider_registry.py, validation.py, service.py
  secrets/          AES-256-GCM local store
  observability/    JSON logs, trace context, field redaction

console/src/
  services/lifeops.ts     the API client — all types live here
  pages/lifeops/          Today, Tasks, Configuration, System, ComingInPhase
  components/layout/      LifeOpsLayout, LifeOpsSidebar

legacy/                   pre-LifeOps Knowledge-OS. Not built, not run, not imported.
                          Mine it for patterns; delete it when Phase 1 is done.
```

### Patterns to follow

**Adding an entity** — model in `domain/`, Protocol in
`repositories/interfaces.py`, Nornic implementation, in-memory fake, operations
on `LifeOpsCore` with a capability check, then HTTP/MCP, then tests, then update
`DATA_MODEL.md`.

**Temporal records** — copy the preference pattern: never edit in place, close
the old `valid_to`, open a new record, link with `SUPERSEDES`, both writes in
one `write_many` transaction. See `repositories/nornic/preferences.py`.

**MCP tool descriptions are prompts.** The model reads them to decide *whether*
to call. Say when to use it, when not to, and what the consequence is
("this records intent; it executes nothing").

**Errors return as data over MCP**: `{"ok": false, "error": "<stable_code>",
...}` so the model can distinguish "not permitted" from "not found".

---

## 6. Standing up Hermes

This is the biggest open item and the one I could not finish. **Hermes is not
installed on this machine** — I checked (`~/.hermes`, `~/.config/hermes`, `PATH`).
Everything I built is the LifeOps half of the contract, exercised in tests using
the exact identity and interface Hermes uses.

### What Hermes actually is

I identified it. Confirm with the user before acting.

- **Hermes Agent by Nous Research** — https://github.com/NousResearch/hermes-agent
- Docs: https://hermes-agent.nousresearch.com/docs/
- PyPI `hermes-agent`, currently **0.19.0**
- Install: `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash`
- Home directory: `~/.hermes/` · config `~/.hermes/config.yaml`
- CLI: `hermes`, `hermes setup`, `hermes model`, `hermes tools`,
  `hermes config get|set`, `hermes gateway`, `hermes memory`, `hermes plugins`,
  `hermes skills`

**Version constraint that will bite you:** `hermes-agent` requires
`>=3.11,<3.14`. This box's Python is **3.14.4**. The installer bundles `uv`,
which can provision its own managed CPython, so `install.sh` will probably
handle it — but if it fails, that's why, and the fix is a uv-managed 3.13.

This does **not** conflict with LifeOps. LifeOps runs on 3.14 in its own venv;
Hermes runs as a separate process. They meet only over MCP stdio.

### Wiring LifeOps into Hermes

Hermes reads MCP servers from `mcp_servers` in `~/.hermes/config.yaml` — the
same shape as Claude Code's `mcpServers` block. There is even a migration path:
`hermes import-agent claude-code`.

I already registered LifeOps with Claude Code, so that import may Just Work.
Otherwise:

```bash
./hermes/bootstrap/register-mcp-client.sh hermes-personal
# prints a launch entry; paste into ~/.hermes/config.yaml under mcp_servers
```

Then verify BUILD_SPEC §102 conversationally:

- Hermes: "Remember I prefer appointments after ten." → check Console → Tasks/state
- Claude Code: "What are the current scheduling preferences?" → same answer
- Claude Code: "Create a task to call the dentist." → Hermes: "What tasks are open?"

### Hermes capabilities that change your plan

This is the most useful thing I found. **Hermes already has pluggable
interfaces for several things the spec describes**, and BUILD_SPEC §4 says reuse
before building. Check each before writing an adapter:

| You need | Hermes already has | Doc |
|---|---|---|
| Memory provider (Phase 2) | **Memory Provider Plugins** — 8 shipped (honcho, mem0, supermemory, …). Honcho is the closest analogue to what LifeOps needs. | `/docs/user-guide/features/memory-providers` |
| TTS backend (Phases 5–6) | **TTS custom command providers** — config-driven, *no Python needed* | Developer guide → plugins |
| STT backend (Phase 6) | `HERMES_LOCAL_STT_COMMAND`, an argv-tokenized template | Voice Message Transcription |
| Browser backend (Phase 9) | **Browser Provider Plugins** (Browserbase-style CDP) | Developer guide → plugins |
| Web search (Phase 9) | **Web Search Provider Plugins** | Developer guide → plugins |
| Secret manager (Phase 5+) | **Secret Source Plugins** (vault / password manager / OS keystore) — relevant to the Bitwarden backend | Developer guide → plugins |
| Telegram/Discord/Slack (Phase 1) | Built-in gateway, all channels, one process | Messaging Platforms |
| Cron / scheduling | Built-in | Cron Scheduling |
| Event hooks | Drop `HOOK.yaml` + `handler.py` into `~/.hermes/hooks/<name>/` | Event Hooks |

Read `/docs/developer-guide/plugins` — it has a map of every pluggable surface.
It may collapse a lot of Phases 5, 6, and 9 into configuration.

### Hermes memory model (matters for Phase 2)

Built-in memory is two files in `~/.hermes/memories/`:

| File | Purpose | Limit |
|---|---|---|
| `MEMORY.md` | Agent's notes — environment, conventions, learnings | 2,200 chars |
| `USER.md` | User profile — preferences, style, expectations | 1,375 chars |

Injected as a frozen snapshot at session start. Exactly as BUILD_SPEC §42
describes: keep identity and critical standing preferences here; everything
episodic and semantic goes to the Nornic-backed provider.

When an external provider is active, Hermes automatically:

1. injects provider context into the system prompt,
2. prefetches relevant memories before each turn (background, non-blocking),
3. syncs conversation turns after each response,
4. extracts memories on session end,
5. mirrors built-in memory writes to the provider,
6. registers provider-specific tools.

That maps one-to-one onto BUILD_SPEC §43's operations. **Only one external
provider can be active at a time**, and it's selected with
`memory: provider: <name>` in `config.yaml` or via `hermes memory setup`.

⚠️ "One agent per Hermes home" — don't point two Hermes processes at the same
`~/.hermes`.

---

## 7. Phase plan

Do them in order. Don't start the next until the current one's acceptance
criteria pass. Update the phase table in `README.md` as you go.

### Phase 1 — Console foundation (§90)

Screens: Today, Needs Attention, Waiting, Tasks, Search, Configuration, System,
Activity.

Also do these, which are recorded debts rather than new scope:

- **Console authentication.** Currently there is none. This is the largest known
  gap (see `SECURITY.md`). The old Knowledge-OS auth is in
  `legacy/knowledge-os-console/` — mine the UI, but the user table went with the
  SQLite backend, so identity has to come from LifeOps.
- **Serve the task transition table from the API** instead of duplicating it in
  `console/src/services/lifeops.ts` (`TASK_TRANSITIONS`). It can drift today.
  The server re-validates, so drift is not a safety hole — but fix it.
- **Delete `legacy/`** once you've mined what you need.
- Add MCP **resources** (`lifeops://me`, `lifeops://today`, `lifeops://waiting`).
  §48 wants reads as resources, not tools. Phase 0 shipped none by design.
- WebSocket/event stream for live Console updates (§4). Not built.
- Frontend log sink: `console/src/lib/logger.ts` currently drops remote logs
  because LifeOps Core has no `/system/logs` endpoint. Add one or leave it off.

### Phase 2 — Memory provider (§91)

Write a Hermes Memory Provider plugin (see §6 above — study Honcho's
implementation first; it's the closest shape).

- Keep the plugin **thin**. No second memory database, no second domain model.
  It calls the LifeOps memory API and nothing else.
- Build `core/lifeops/memory/` (api, policy, schemas) and a `MemoryRepository`.
- Enforce §44 hard: memory may observe, never rewrite transactional reality. It
  must not approve actions, consume approvals, mark payments complete, alter
  idempotency, or grant authority. Write the tests that prove each of those
  is refused.
- This is where embeddings first matter. Turn on NornicDB's vector/BM25
  capability (`--embedding-enabled`, provider `ollama` or `openai`); do **not**
  build a vector service. `docs/skills/managed-embeddings.skill.md` and
  `vector-search.skill.md` in the NornicDB source are worth reading.
- Memory screen in the Console with correct/invalidate/supersede.

### Phase 3 — World (§92)

React Flow is explicitly acceptable. Entity inspector, filters, search-to-node,
provenance, history. Promote `Task.related_entity_ids` from a property to real
graph edges — that's a repository migration, not a domain change. The browser
never gets Nornic credentials; everything goes through LifeOps APIs.

### Phase 4 — Durable work (§93)

WaitingItems, the due-work worker with leases, follow-up logic, verification
states. **No Temporal** — durable continuation state lives in Nornic (§55).
Add `update_task` and waiting tools to the MCP surface. This is also where the
**durable audit log** belongs (§62) and the Activity screen gets real data.

### Phase 5 — Configuration + ElevenLabs (§94)

The provider schema and Console form already exist. You need the adapter:
streaming TTS, `list_voices`, `list_models`, `health_check`, voice preview in
the browser. Discover models via the API — don't hardcode one.

Make the Test and Discover endpoints do real work; they currently return honest
"not implemented" responses that you must replace, not leave.

Check whether Hermes' config-driven TTS provider gets you there without Python.

### Phase 6 — Local voice (§95)

Needs the RTX 3060, which isn't visible from this box. Establish where the GPU
is before starting. Candidates are in §30; the spec explicitly says don't block
on picking a winner — ship adapters and let the Console choose.

### Phase 7 — Calendar + email (§96)

Read → reversible writes → external communication, in that order. Email is
untrusted input: prompt injection in a message must not change LifeOps authority.
The trust hierarchy in `policy/trust.py` is your structural defence — extend it,
don't bypass it.

### Phase 8 — Provider workflows + telephony (§97)

Research and information-gathering first, then approval-gated booking. A phone
call cannot enlarge its own authority (§68). Store structured call results, not
just transcripts (§69).

### Phase 9 — Browser + shopping (§98)

Separate browser contexts (general / shopping / medical / billing). Never bypass
MFA — surface it as NEEDS_ATTENTION. Never store session cookies in Nornic.
**Playwright doesn't work on this host** — check Hermes' Browser Provider
Plugins first.

### Phase 10 — Bills + payments (§99)

Payments last. The gate is explicit: action outbox, approvals, idempotency,
verification, audit, emergency stop, and backup/restore must all be *proven*
first. `SecretStore`, `policy`, and the verification gate exist; the outbox,
approvals, and idempotency modules do not — `core/lifeops/actions/` is empty.

### Phase 11 — Hermes self-configuration (§100)

`request_code_change()` writing to `changes/requests/`. Hermes manages skills,
routines, cron, preferences; it may not touch authorization, approval,
payments, secrets, migrations, MCP auth, or CI.

---

## 8. Debts I'm handing you

Everything here is written up in `SECURITY.md` too. None is hidden; all are real.

| # | Debt | Phase |
|---|---|---|
| 1 | **Console has no authentication.** Loopback-only, no external-write capability, so it's bounded — but do not expose 5173 or 8080 beyond localhost until this is fixed. | 1 |
| 2 | No durable audit log. Semantic operations are logged with trace IDs, but nothing is queryable and there's no Activity screen. | 4 |
| 3 | `TASK_TRANSITIONS` is duplicated in the Console. Server re-validates, so drift is not a safety hole, but serve it from the API. | 1 |
| 4 | No MCP resources. §48 wants reads as resources; Phase 0 shipped 5 tools and nothing else by design. | 1 |
| 5 | No WebSocket/event stream. §4 lists it; the Console polls. | 1 |
| 6 | No browser e2e — Playwright won't install here. | 1 or 9 |
| 7 | `legacy/` (2 MB) still in the tree. Excluded from all builds and tests. Delete after mining. | 1 |
| 8 | No backup/restore automation. `OPERATIONS.md` documents the manual loop; §80 wants it automated. | 10 |
| 9 | `core/lifeops/actions/`, `memory/`, `integrations/`, `worker/` don't exist yet. Create them when their phase arrives, not before. | — |
| 10 | The MCP server trusts its launch config — inherent to stdio MCP, not fixable there. Revisit only if you move to a networked transport. | — |

---

## 9. Verification, every phase

```bash
make check          # lint + all Python tests + Console tests + Console build
make test-e2e       # Phase 0 exit criteria — these must never regress
./scripts/healthcheck.sh
```

Test placement:

| Kind | Location | Needs DB |
|---|---|---|
| Domain rules | `tests/unit` (against fakes) | no |
| Capability behaviour | `tests/policy` | no |
| API contract | `tests/integration` | no |
| Cypher + graph shape | `tests/persistence` | yes |
| Phase acceptance | `tests/e2e` | yes |

Suites needing NornicDB must **skip** when it's unreachable, never fail.

Non-negotiables when you add tests:

- Use `FrozenClock`, never the wall clock.
- Clean up by owner/subject, not by an optional field. My first persistence
  fixture cleaned tasks by `source`, which most tests don't set — it silently
  leaked rows into a shared database for hours before I caught it.
- Assert on behaviour, not on private methods.

---

## 10. Judgement calls I made

You may reverse any of these, but know they were deliberate.

1. **Restructured the Knowledge-OS repo in place** rather than starting a new
   one, to keep git history. `frontend/` → `console/`; backend and unmigrated
   screens → `legacy/`.
2. **Moved legacy code instead of deleting it.** §9.2 says the old backend may
   be mined for patterns; exit criterion I says no parallel source of truth.
   Moving it out of every build satisfies both. Delete it in Phase 1.
3. **Built NornicDB from source.** No Linux release exists and there's no Docker
   here. Adding a container runtime to satisfy one dependency failed the §105
   gate.
4. **Embeddings off.** Nothing to embed until Phase 2.
5. **No Console auth in Phase 0.** Not in Phase 0's scope, and the old auth died
   with the SQLite user table. Recorded as debt #1 rather than half-built.
6. **Console shows later-phase nav entries dimmed with their phase number**
   instead of hiding them, so the Console's shape stays stable as phases land.
7. **Repo-local git identity** set to match existing commits (none was
   configured). Global config untouched.

---

## 11. Ask the user before assuming

1. **Is Hermes Agent by Nous Research the right Hermes?** I inferred it from the
   spec's description and a search. High confidence, but it's the foundation of
   everything — confirm.
2. **Where does Hermes actually run?** This box, a VPS, the desktop app? It
   affects the MCP transport (stdio vs. HTTP) and whether LifeOps needs to
   listen on more than loopback — which would make debt #1 urgent rather than
   bounded.
3. **Where is the RTX 3060?** Not visible here. Phase 6 can't be validated
   without it.
4. **Is there an existing Hermes profile/config to preserve?** If they've been
   using Hermes already, `hermes import-agent` and existing `MEMORY.md` /
   `USER.md` / `SOUL.md` matter for Phase 2.
5. **Does this branch get merged to `main`, or does work continue on
   `lifeops/phase-0`?** I left it on the branch.

---

## 12. If you read nothing else

- The spec is the contract. One phase at a time. Acceptance before moving on.
- Never ask for a credential. Build the adapter, the mock, the form, the Test
  button; leave it disabled; keep going.
- Rules go in `core.py` or `domain/`, never in an adapter.
- Cypher goes in `repositories/nornic/`, nowhere else.
- Check what Hermes and NornicDB already do before building anything. The spec
  is emphatic about this and I found several places where it pays off.
- Completion needs evidence. A model saying it happened is not evidence.
