# Hermes LifeOps — session context

A personal operating system built around the Hermes assistant.

**Read [BUILD_SPEC.md](BUILD_SPEC.md) first.** It is authoritative. When
anything here disagrees with it, the spec wins.
[AGENTS.md](AGENTS.md) holds the working rules for changing this repository.

---

## Where things stand

**Phase 0 is complete.** The spine — Hermes → LifeOps MCP → LifeOps Core →
NornicDB — is proven end to end, and every Phase 0 exit criterion passes.

Phases 1 through 11 have not started. `README.md` tracks status.

Do not begin the next phase without the user asking for it.

---

## The rules that matter most

1. **NornicDB is the only application database.** No SQLite, PostgreSQL,
   Qdrant, Neo4j, or Redis.
2. **Nothing writes to NornicDB except LifeOps Core.** Not agents, not the
   Console, not integrations.
3. **Never ask the user for a runtime credential.** Build the adapter, the
   schema, the Console form, and the Test button; leave the provider disabled.
4. **Hermes is the assistant.** Do not build a second agent, a voice agent, or
   an agent runtime.
5. **No infrastructure for hypothetical problems.** See BUILD_SPEC section 105.

---

## Layout

```
core/lifeops/     LifeOps Core
  domain/         models and pure rules — no Cypher, no HTTP, no MCP
  core.py         the single application service; all orchestration lives here
  policy/         capabilities and trust — pure functions
  repositories/   interfaces + the only Cypher in the codebase
  api/            HTTP for the Console — shape translation only
  mcp/            MCP for agents — shape translation only
  config/         provider registry, validation, config service
  secrets/        AES-GCM secret store; secrets never enter NornicDB

console/src/      LifeOps Console (React), talks only to LifeOps Core
  pages/lifeops/  Today, Tasks, Configuration, System
  services/lifeops.ts

tests/            unit · policy · integration · persistence · e2e
hermes/           MCP registration for Hermes and other clients
scripts/          build, run, health
legacy/           pre-LifeOps Knowledge-OS code — not built, not run, not imported
```

---

## Running it

```bash
make dev      # NornicDB + LifeOps Core + Console
make health
make stop
```

Console at http://127.0.0.1:5173, Core at http://127.0.0.1:8080.

No third-party credentials required.

---

## Testing

```bash
make test-fast     # unit + policy + integration, no database, ~1s
make test          # everything Python, needs NornicDB
make console-test
make check         # what CI runs
```

`tests/e2e/test_phase0_exit.py` is the Phase 0 acceptance gate. Every MCP
session in it is a real subprocess speaking the real protocol.

Details in [TESTING.md](TESTING.md).

---

## Things worth knowing before you change something

**One service, two adapters.** `core/lifeops/core.py` holds every capability
check and orchestration step. `api/http.py` and `mcp/server.py` only translate
shapes. Putting a rule in one adapter means the other silently does not get it —
and MCP is the path no human watches.

**Cypher lives in exactly one place.** `repositories/nornic/`. If a domain test
needs Cypher to pass, the abstraction has leaked; fix the abstraction.

**Preferences are never overwritten.** A save closes the old validity window and
opens a new record with a `SUPERSEDES` edge, in one transaction.

**Task state goes through the machine.** Never assign `state` directly. An
illegal transition must raise and write nothing.

**Client identity is bound per connection**, never passed as a tool argument — a
tool argument is model-controlled, which would let any agent claim to be Hermes.

**NornicDB's admin password is fixed at data-directory initialisation.** A new
`nornicdb.env` pointed at existing data will fail to authenticate.

---

## Known gaps in Phase 0

Recorded in [SECURITY.md](SECURITY.md), not hidden:

- The Console has no authentication. Loopback only; Phase 1 closes it.
- No durable audit log yet. Phase 4.
- No provider adapters. `test` and `discover` report honestly that they are not
  implemented rather than faking success.
- Hermes itself has not been attached on this machine — it is not installed
  here. See [HERMES_INTEGRATION.md](HERMES_INTEGRATION.md).

---

## Documentation

[README](README.md) · [BUILD_SPEC](BUILD_SPEC.md) · [ARCHITECTURE](ARCHITECTURE.md) ·
[DATA_MODEL](DATA_MODEL.md) · [MCP_API](MCP_API.md) · [SECURITY](SECURITY.md) ·
[OPERATIONS](OPERATIONS.md) · [TESTING](TESTING.md) · [CONFIGURATION](CONFIGURATION.md) ·
[HERMES_INTEGRATION](HERMES_INTEGRATION.md) · [AGENTS](AGENTS.md)
