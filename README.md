# Hermes LifeOps

A personal operating system built around the Hermes assistant.

**Status: Phase 7 complete.** The spine is proven end to end; the Console,
memory, world, durable-work, voice, and calendar/email layers are built on it. See [Phase status](#phase-status).

```
Hermes            the assistant — conversation, planning, tools, skills
LifeOps Core      the portable personal domain layer and safety boundary
NornicDB          the single world-model and application-state database
LifeOps Console   the visual inspection, configuration, and approval interface
```

Your data, memory, tasks, relationships, and history belong to LifeOps — not to
any one agent. Hermes is the primary assistant, but Claude Code, a
ChatGPT-compatible MCP client, or a future agent can connect to the same LifeOps
MCP server and operate on the same state, each with its own permissions.

[BUILD_SPEC.md](BUILD_SPEC.md) is the authoritative architecture.

---

## Quick start

Nothing here requires a third-party API key. LifeOps boots with every provider
disabled and you configure real values later, in the Console.

```bash
make setup          # Python environment + Console dependencies
make nornic-build   # build NornicDB from source (~3 min, needs Go ≥ 1.26 or downloads it)
make dev            # start NornicDB, LifeOps Core, and the Console
```

Then open **http://127.0.0.1:5173**.

```bash
make health         # component health
make status         # what is running
make stop           # stop everything
```

### Connecting an agent

LifeOps MCP is a stdio server. Each client gets its own launch entry declaring
its identity:

```bash
./hermes/bootstrap/register-mcp-client.sh hermes-personal   # for Hermes
./hermes/bootstrap/register-mcp-client.sh claude-code       # for Claude Code
```

The identity is what determines permissions — see [SECURITY.md](SECURITY.md).
Full instructions in [HERMES_INTEGRATION.md](HERMES_INTEGRATION.md).

---

## Repository layout

```
core/lifeops/     LifeOps Core — domain, policy, repositories, MCP, HTTP API
console/          LifeOps Console — the React frontend, evolved from Knowledge-OS
hermes/           MCP registration templates and bootstrap for agent clients
tests/            unit, policy, integration, persistence, and the Phase 0 exit test
scripts/          build, run, and health scripts
deploy/           systemd units and container compose
changes/requests/ code change requests raised by Hermes (Phase 11)
```

---

## Phase status

| Phase | Scope | State |
|------:|-------|-------|
| 0 | Core spine: Hermes → LifeOps MCP → LifeOps Core → NornicDB | **Complete** |
| 1 | Console foundation: Today, Needs Attention, Waiting, Search, Activity | **Complete** |
| 2 | Hermes memory provider backed by NornicDB | **Complete** |
| 3 | World graph and entity inspector | **Complete** |
| 4 | Durable work: waiting items, due-work worker, verification | **Complete** |
| 5 | Configuration and the ElevenLabs voice path | **Complete** |
| 6 | Local RTX voice | **Complete** |
| 7 | Calendar and email | **Complete** |
| 8 | Provider workflows and telephony | Not started |
| 9 | Browser and shopping | Not started |
| 10 | Bills and financial actions | Not started |
| 11 | Hermes self-configuration | Not started |

### What Phase 0 delivers

- NornicDB running locally with persistent storage, reachable only on loopback.
- A repository abstraction with no Cypher outside `repositories/nornic/`.
- `Person`, `Preference`, and `Task` domains, with temporal preference history
  and a validated task state machine.
- Exactly five MCP tools: `get_person`, `get_preferences`, `save_preference`,
  `create_task`, `list_tasks`.
- Per-client capability enforcement — a coding agent can read your world and
  file a task, but cannot rewrite your stated preferences.
- An encrypted local secret store; secrets never enter NornicDB.
- A provider registry with schema-driven Console forms for DeepSeek,
  ElevenLabs, Telegram, Calendar, Email, Browser, and Telephony — all disabled
  and unconfigured on a fresh deployment.
- LifeOps Console booting on Today, Tasks, Configuration, and System.

### What Phase 1 adds

- The full Console navigation working: Today, Needs Attention, Waiting, Tasks,
  Search, Configuration, System, and Activity.
- Optional Console authentication: set a console password and every API route
  requires a bearer token; leave it unset and loopback stays open (see
  [SECURITY.md](SECURITY.md)).
- The task transition table served from the API — the Console no longer
  mirrors it.
- MCP resources `lifeops://me`, `lifeops://today`, and `lifeops://waiting`
  alongside the five tools (BUILD_SPEC section 48).
- A WebSocket event stream (`/api/v1/events`) so the Console updates live
  instead of only polling.
- Universal search across people, preferences, and tasks, an ephemeral
  activity feed (`/api/v1/system/activity`; the durable audit log is Phase 4),
  and a frontend log sink (`/api/v1/system/logs`).
- The pre-LifeOps `legacy/` tree is deleted; its patterns are ported or in git
  history.

### What Phase 3 adds

- A world model of `Household`, `Provider`, and `Asset` entities alongside the
  existing `Person`, each with a bag of current facts and canonical slug IDs.
- Preferences drawn in the graph as BUILD_SPEC section 15 shows them —
  `Gene ─PREFERS→ "After 10 AM"` — projected from the preference layer rather
  than duplicated, and only while current.
- The full BUILD_SPEC section 39 relationship vocabulary — all twenty types,
  in the spec's order. Several are written by other aggregates already
  (`ASSIGNED_TO` and `ABOUT` by tasks, `PREFERS` by preferences, `SUPERSEDES`
  by both temporal chains); the world graph reads one vocabulary rather than
  each layer keeping its own.
- The World screen: an interactive graph with zoom, pan, fit-view, entity-type
  and relationship filters, search-to-node, click-to-expand a neighborhood,
  and click-again to collapse the branch.
- The entity inspector (section 16): current facts, named relationships,
  related tasks and memories, history, and provenance — with unlink as the
  only write, because the graph is not a database editor.
- Four read-only MCP tools — `find_person`, `get_provider`,
  `get_related_entities`, `get_entity_history` — bringing the sanctioned tool
  surface to twelve. World *writes* stay on the Console: shaping the graph is
  the user's act, not the model's.
- Entity history that states its own scope. World facts are current-only in
  this phase, so history reports the memory record referencing an entity —
  closed versions included — and says so in a `covers` field rather than
  implying it is the durable audit log (Phase 4).

### What Phases 4 through 7 add

- **Durable work (Phase 4).** Waiting items with widening follow-up backoff that
  escalates rather than silently giving up, a due-work worker holding a lease so
  two workers never chase one provider, and continuation state in NornicDB per
  BUILD_SPEC section 55 — deliberately not a workflow engine. Work survives a
  full LifeOps and NornicDB restart, verified against the running stack.
- **The action outbox, approvals, and audit.** Section 93 does not require these;
  section 99 does, before payments are ever enabled. Every external write is
  recorded before it happens, idempotency keys are generated by LifeOps and never
  by a model, and an approval binds to the payload hash — so editing a booking
  after approval stops it authorising, as arithmetic rather than judgement.
- **Voice (Phases 5 and 6).** ElevenLabs and local ASR/TTS behind one provider
  abstraction, with the three section 29 modes selectable from the Console. No ML
  runtime is installed: the local adapters report honestly when theirs is absent,
  and CI exercises fakes. A test proves state saved through voice is the same
  state read through text — it belongs to LifeOps, not the modality.
- **Calendar and email (Phase 7).** Read first, then reversible writes, then
  external communication, in that order. A calendar hold is never mistaken for a
  booking (section 63).

**This is where LifeOps first becomes able to act outward.** `BOOK_APPOINTMENT`
and `SEND_EXTERNAL_MESSAGE` are granted to Hermes and the Console — and to
nothing else. `APPROVE_ACTION` stays Console-only, so a booking Hermes prepares
still needs a human decision it cannot make for itself. Shopping and payment
capabilities remain granted to no client at all until Phases 9 and 10.

### What Phase 0 deliberately does not deliver

Telephony, browser, shopping, and payments. Their provider entries exist and
are configurable; their adapters arrive in the phases above, and the Console
says so rather than pretending otherwise.

---

## Documentation

| Document | Purpose |
|---|---|
| [BUILD_SPEC.md](BUILD_SPEC.md) | The authoritative architecture and phase plan |
| [ARCHITECTURE.md](ARCHITECTURE.md) | How the pieces fit and why |
| [DATA_MODEL.md](DATA_MODEL.md) | Entities, relationships, and temporal state |
| [MCP_API.md](MCP_API.md) | The agent-facing tool surface |
| [SECURITY.md](SECURITY.md) | Client identity, capabilities, secrets, known gaps |
| [OPERATIONS.md](OPERATIONS.md) | Running, backing up, and recovering LifeOps |
| [TESTING.md](TESTING.md) | The test suites and what each proves |
| [CONFIGURATION.md](CONFIGURATION.md) | Deployment settings vs. runtime configuration |
| [HERMES_INTEGRATION.md](HERMES_INTEGRATION.md) | Attaching Hermes and other MCP clients |
| [AGENTS.md](AGENTS.md) | Guidance for agents working in this repository |

---

## Licence

MIT. See [LICENSE](LICENSE).
