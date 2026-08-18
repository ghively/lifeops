# Architecture

How the pieces fit, and the reasoning behind the boundaries.
[BUILD_SPEC.md](BUILD_SPEC.md) is authoritative; this document explains the
implementation.

---

## The shape

```
                              USER
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
    Telegram                 Voice             LifeOps Console
        │                      │                      │
        └──────────────────────┼──────────────────────┘
                               │
                          ┌────▼────┐
                          │ HERMES  │  conversation, planning, skills
                          └────┬────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
         DeepSeek       MemoryProvider     LifeOps MCP
                                                │
                                    ┌───────────▼───────────┐
                                    │     LifeOps Core      │
                                    │  domain · policy ·    │
                                    │  actions · config     │
                                    └───────────┬───────────┘
                                                ▼
                                            NornicDB
                                  graph · vector · temporal
```

Phase 0 implements the Hermes → LifeOps MCP → LifeOps Core → NornicDB spine and
the Console's connection to LifeOps Core. Voice, Telegram, and the memory
provider arrive in later phases.

---

## Four boundaries that matter

### 1. Nothing writes to NornicDB except LifeOps Core

Agents don't, the Console doesn't, integrations won't. Every state change goes
through a domain operation.

This is what makes authorization, state validity, approval, idempotency,
verification, and audit possible at all. A raw graph write can carry none of
them. That is also why the MCP surface offers `save_preference` rather than
`run_cypher`: the tool boundary is where meaning is enforced.

### 2. One application service, two adapters

```
        HTTP API (Console)     MCP server (agents)
                  \                 /
                   \               /
                    LifeOpsCore          ← every rule lives here
                         │
                  repositories
                         │
                     NornicDB
```

`core/lifeops/core.py` is the only place that orchestrates repository calls and
capability checks. `api/http.py` and `mcp/server.py` translate shapes and
nothing else.

If each surface did its own orchestration, the rules would drift — and they
would drift *silently on the MCP path*, which is the one a human never watches.

### 3. Domain code never sees Cypher

```python
class PreferenceRepository(Protocol):
    async def save_superseding(self, preference, *, supersedes): ...
```

The domain depends on Protocols in `repositories/interfaces.py`. NornicDB
implementations live in `repositories/nornic/` and are the only files in the
codebase containing Cypher.

This is the escape plan from BUILD_SPEC section 81, made real: replacing the
database means writing new implementations of these Protocols, with Hermes, the
Console, the MCP surface, and the domain layer untouched. The in-memory fakes in
`repositories/fakes/` are the proof — if a domain test ever needs Cypher to
pass, the abstraction has leaked.

### 4. Secrets never enter NornicDB

NornicDB holds the world model, which is read broadly by agents and rendered in
the Console. API keys and refresh tokens have no business in that blast radius.

They go to a `SecretStore` instead: AES-256-GCM, master key outside the
repository at mode 0600, ciphertext in its own file. Reads return
`{"configured": true, "fingerprint": "a1b2c3"}` and never the value.

---

## Request path

A preference save, end to end:

```
Hermes calls save_preference(key, value)
  │
  ├─ MCP server           client identity is already bound to the connection
  │                       (a tool argument would be model-controlled)
  ├─ LifeOpsCore          require(client, WRITE_PREFERENCE)
  │                       resolve subject → primary person
  │                       load the current value for this key
  │                       trust check: may this source supersede that one?
  │                       identical value? return the existing record
  │                       build the new Preference with valid_from = now
  │
  ├─ Repository           one transaction:
  │                         close the old validity window
  │                         create the new record
  │                         link Person -[:PREFERS]-> Preference
  │                         link new -[:SUPERSEDES]-> old
  │
  └─ NornicDB             durable
```

The close-and-open pair shares a transaction because committing only half would
leave the subject with either two current values for one key or none.

---

## Temporal state

Preferences are never edited in place:

```
Preference A   "appointments after 10"   valid_from: 2026-08-16  valid_to: null
                                              ↓ user changes their mind
Preference A   "appointments after 10"   valid_from: 2026-08-16  valid_to: 2027-03-02
Preference B   "appointments after 9"    valid_from: 2027-03-02  valid_to: null
Preference B  -[:SUPERSEDES]-> Preference A
```

"Current" means `valid_to IS NULL`. History stays queryable, so "what did the
assistant believe on the day it booked that appointment?" remains answerable
after the preference changes — which matters the first time a booking looks
wrong in hindsight.

---

## Task state machine

Eleven states with an explicit, exhaustive transition table. A lookup miss is a
denial, never a default-allow.

```
CAPTURED → PLANNED → READY → EXECUTING ─┬→ WAITING_EXTERNAL
                                        ├→ NEEDS_APPROVAL
                                        ├→ VERIFYING → COMPLETED
                                        ├→ BLOCKED
                                        └→ FAILED → READY (retry)

COMPLETED and CANCELLED are terminal.
```

Two rules are enforced here rather than trusted to a model:

1. An illegal transition raises `invalid_transition` and writes nothing. A model
   proposing CAPTURED → COMPLETED gets an error, not a rewritten task.
2. A task with `verification_required` reaches COMPLETED only through VERIFYING,
   and only with evidence attached. "The model said it booked the appointment"
   is not evidence.

---

## Client identity and capabilities

Authority never comes from a model or provider name. Every request resolves to a
declared client identity, and policy consults that.

| | Hermes | Interactive MCP | Coding agent | Console |
|---|:---:|:---:|:---:|:---:|
| Read world / preferences / tasks | ● | ● | ● | ● |
| Create task | ● | ● | ● | ● |
| Update task | ● | ● | — | ● |
| Write preference | ● | ● | — | ● |
| Read memory | ● | ● | ● | ● |
| Write memory | ● | — | — | ● |
| Write world | ● | — | — | ● |
| Manage configuration | — | — | — | ● |
| Approve action | — | — | — | ● |

The coding agent's job is the repository, not the user's life. Only the Console
— where a human is present — administers configuration or approves anything; an
agent approving its own action would defeat the gate entirely.

Hermes holds `write_world` because shaping the user's world is the primary
assistant's job. The MCP tools that spend it are narrow and named —
`record_provider`, `record_asset`, and `create_service_request`, exactly the
writes BUILD_SPEC section 51 sanctions — while relationships and generic
entities are created only from the Console. The capability is granted where
it belongs rather than the tool surface being the only thing standing
between a model and the graph.

There is no policy language. Capabilities are an explicit map and the decision
function is fifteen readable lines. A rules engine here would be infrastructure
for a problem that does not exist.

---

## What runs

| Process | Role | Binds |
|---|---|---|
| `nornicdb serve` | The database | 127.0.0.1:7687 (Bolt), :7474 (HTTP) |
| `lifeops` | HTTP API for the Console | 127.0.0.1:8080 |
| `lifeops-mcp` | One process per MCP client, over stdio | — |
| `vite` (dev) | The Console | 127.0.0.1:5173 |

MCP servers are separate short-lived processes because MCP clients launch and
own their transport. Each connects to the same NornicDB, so the state every
client sees is identical — that is the whole point.

---

## Choices worth recording

**React Flow for the World graph.** BUILD_SPEC section 15 asks for "an
interactive graph library appropriate for the existing React stack" and names
React Flow as acceptable, so the choice is the spec's rather than ours. Recording
it here because AGENTS.md requires every dependency to be justified in writing:
the concrete problem is section 15's zoom, pan, fit-view, and click-to-expand
requirements; no existing capability covers canvas interaction; the operational
cost is one Console-only package with no runtime or server footprint; and the
removal plan is that it is confined to `console/src/components/world/`, so
replacing it touches four files and no domain code.

**NornicDB built from source.** Upstream ships Docker images and macOS packages;
neither fits a Linux host without Docker. Building the Go binary was shorter
than adding a container runtime to satisfy one dependency.

**Embeddings off.** NornicDB can generate them, and Phase 2 gave memory
something worth embedding — but BM25 fulltext recall is answering the queries
that exist today. Loading an embedding model stays capacity held against a
problem that has not appeared yet.

**Console auth is opt-in.** Phase 1 added bearer-token authentication, enabled
only once a console password is set. Until then loopback binding is the whole
boundary, so a fresh deployment behaves exactly as Phase 0 did. Details in
[SECURITY.md](SECURITY.md).

**Legacy code deleted in Phase 1.** The Knowledge-OS backend and unmigrated
screens lived in `legacy/` through Phase 0 so their patterns stayed readable
while being ported. Phase 1 removed the tree; git history remains the archive.
