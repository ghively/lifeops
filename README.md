# Hermes LifeOps

A personal operating system built around the Hermes assistant.

**Status: Phase 0 complete.** The spine is proven end to end; the phases that
follow build on it. See [Phase status](#phase-status).

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
| 2 | Hermes memory provider backed by NornicDB | Not started |
| 3 | World graph and entity inspector | Not started |
| 4 | Durable work: waiting items, due-work worker, verification | Not started |
| 5 | Configuration and the ElevenLabs voice path | Not started |
| 6 | Local RTX voice | Not started |
| 7 | Calendar and email | Not started |
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

### What Phase 0 deliberately does not deliver

Voice, telephony, email, calendar, browser, shopping, payments, memory, and the
World graph. Their provider entries exist and are configurable; their adapters
arrive in the phases above, and the Console says so rather than pretending
otherwise.

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
