# Working in this repository

Guidance for agents (and people) making changes to Hermes LifeOps.

[BUILD_SPEC.md](BUILD_SPEC.md) is authoritative. When this file and the spec
disagree, the spec wins.

---

## Execute one phase at a time

```
READ SPEC → INSPECT CODE → PLAN → IMPLEMENT → TEST → ACCEPTANCE
→ ADVERSARIAL REVIEW → FIX → DOCUMENT → COMMIT → NEXT PHASE
```

Do not start the next phase until the current one's acceptance criteria pass.
`README.md` tracks phase status.

---

## Never ask the user for runtime credentials

Not API keys, tokens, voice IDs, model IDs, account IDs, phone numbers, or
provider logins. Ever.

When a feature needs a provider:

1. Implement the adapter.
2. Implement a mock or test double.
3. Add the provider definition to `config/provider_registry.py`.
4. Ensure the Console renders its form from that schema.
5. Ensure the Test button works.
6. Leave the provider disabled.

Then keep going. The user configures real values in the Console after
deployment. Development and CI use fakes.

---

## Boundaries you must not cross without an explicit decision

These come from BUILD_SPEC section 108. If one genuinely needs to change,
document the concrete failure, write a proposal in `changes/requests/`, and
stop — do not redesign silently.

- The primary architecture
- NornicDB as the single application database
- Hermes as the primary agent
- The LifeOps MCP boundary
- The approval and risk model
- Secret-storage policy
- GUI-driven configuration
- External-action verification
- Knowledge-OS as the Console

---

## Prohibited without new evidence

PostgreSQL · SQLite as canonical state · Qdrant · Neo4j · Redis · Kafka ·
RabbitMQ · Temporal · n8n · OPA · Kubernetes · a dedicated vector service · a
dedicated graph service · a separate memory service · a separate entity-resolver
service · a general event bus · a multi-agent framework · a custom agent runtime
replacing Hermes

Before adding *any* dependency, answer in writing:

```
Problem:              what concrete failure exists right now?
Existing capability:  can Hermes, NornicDB, MCP, or a small LifeOps module do it?
Why it is required:
Operational cost:
Removal plan:
```

No concrete problem, no dependency.

---

## Where things go

| Concern | Location | Rule |
|---|---|---|
| Domain models and pure rules | `core/lifeops/domain/` | No Cypher, no HTTP, no MCP |
| Orchestration and capability checks | `core/lifeops/core.py` | The only place that composes repositories |
| Cypher | `core/lifeops/repositories/nornic/` | The only place, without exception |
| Policy | `core/lifeops/policy/` | Pure functions, explicit client argument |
| HTTP | `core/lifeops/api/` | Shape translation only |
| MCP | `core/lifeops/mcp/` | Shape translation only |
| Console | `console/src/` | Talks to LifeOps Core, never to NornicDB |

Adding a business rule to `api/http.py` or `mcp/server.py` means the other
surface does not get it — and the MCP path is the one no human is watching.
Rules go in the domain or in `core.py`.

---

## Adding a domain entity

1. Model and pure rules in `domain/`.
2. A repository Protocol in `repositories/interfaces.py`.
3. A NornicDB implementation in `repositories/nornic/`.
4. An in-memory fake in `repositories/fakes/`.
5. Operations on `LifeOpsCore` with a capability check.
6. HTTP routes and, if agents need it, an MCP tool.
7. Tests: unit against the fake, persistence against NornicDB.
8. Update `DATA_MODEL.md`.

If a domain test needs Cypher to pass, the abstraction has leaked. Fix the
abstraction, not the test.

---

## Adding an MCP tool

Tools are narrow and semantic. `book_appointment`, not `do_action`.

The description is a prompt — the model reads it to decide *whether* to call.
Say when to use it and when not to. State the consequence: "this records intent;
it executes nothing".

Errors return as `{"ok": false, "error": "<stable_code>", ...}` so a model can
distinguish "not permitted" from "not found" and react, rather than retrying
blindly.

Never expose `run_cypher`, `create_node`, `set_property`, or anything that lets
a caller construct arbitrary database or external operations.

---

## Testing expectations

Every change ships with tests. `make check` before committing.

- Domain rules → `tests/unit`, against fakes
- Capability behaviour → `tests/policy`
- API contract → `tests/integration`
- Cypher and graph shape → `tests/persistence`
- Phase acceptance → `tests/e2e`
- Spec fidelity and structure → `tests/spec`, no database

Suites needing NornicDB must skip when it is unreachable, never fail.

`tests/spec` enforces rules this file already states, because stating them was
not enough — Phase 3 skipped three steps of "Adding a domain entity" and no test
noticed. It asserts that BUILD_SPEC enumerations are implemented in full, that
every repository Protocol has a fake whose signatures match the NornicDB
implementation, that no test fakes `LifeOpsCore`, and that every NornicDB
repository has a persistence test.

When a phase adds an enumeration to BUILD_SPEC — section 54's WaitingItem
fields, section 59's Approval model, section 60's Action record — pin it in
`tests/spec/test_spec_fidelity.py` before implementing it.

Assert on behaviour, not on implementation. A test that breaks when you rename a
private method is a maintenance cost, not a safety net.

---

## Style

**Python** — PEP 8, `ruff` clean, type hints on public functions, async for I/O.

**TypeScript** — strict mode, no `any`, function components.

**Comments** explain *why*, not *what*. The reader can see what the code does;
they cannot see what you ruled out. Reference `BUILD_SPEC` sections where a
decision traces back to one.

**Errors** carry a stable `code`. Two very different consumers read them: a
human in the Console, and a model deciding what to do next. Prose alone serves
neither.

---

## Safety invariants

Do not weaken these to make a test pass:

1. Capability checks run before every state change.
2. Task transitions go through the state machine. Never assign `state` directly.
3. External completion requires evidence.
4. Secrets never enter NornicDB and never appear in a response or a log.
5. Safe mode is checked before the capability grant.
6. A weaker trust source cannot supersede a stronger one.
