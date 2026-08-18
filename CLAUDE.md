# Hermes LifeOps — session context

A personal operating system built around the Hermes assistant.

**Read [BUILD_SPEC.md](BUILD_SPEC.md) first.** It is authoritative. When
anything here disagrees with it, the spec wins.
[AGENTS.md](AGENTS.md) holds the working rules for changing this repository.

---

## Where things stand

**All eleven phases are complete.** The spine — Hermes → LifeOps MCP →
LifeOps Core → NornicDB — is proven end to end and every Phase 0 exit criterion
still passes. Phase 1 added the Console foundation, Phase 2 the memory
provider, Phase 3 the world graph, Phase 4 durable work with the action outbox
and approvals, Phases 5-6 voice, and Phase 7 calendar and email.

LifeOps can now act outward. `BOOK_APPOINTMENT`, `SEND_EXTERNAL_MESSAGE`, and
`SHOPPING_CHECKOUT` are held by Hermes and the Console; `APPROVE_ACTION` and
`FINANCIAL_PAYMENT` are Console-only, so no agent approves its own action and
no model holds a path to a payment.

Both acceptance scenarios pass (sections 101 and 102). `README.md` tracks status.

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
                  (MemoryService and WorldService are narrowed by construction)
  policy/         capabilities and trust — pure functions
  repositories/   interfaces + the only Cypher in the codebase
  api/            HTTP for the Console — shape translation only
  mcp/            MCP for agents — shape translation only
  config/         provider registry, validation, config service
  secrets/        AES-GCM secret store; secrets never enter NornicDB

console/src/      LifeOps Console (React), talks only to LifeOps Core
  pages/lifeops/  Today, Tasks, Memory, World, Configuration, System
  services/lifeops.ts

tests/            unit · policy · spec · integration · persistence · e2e
hermes/           MCP registration for Hermes and other clients
scripts/          build, run, health
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
make test-fast     # unit + policy + spec + integration, no database, <1 min
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

**World writes over MCP are narrow and named.** Relationships and generic
entities are created from the Console; the MCP surface spends `write_world`
only through `record_provider`, `record_asset`, and `create_service_request`
(BUILD_SPEC section 51 sanctions exactly these), so Hermes can record a
provider it just found but cannot shape the user's world generically.

**The relationship vocabulary is BUILD_SPEC section 39, all twenty types.**
The warning there — "do not attempt to predefine every relationship in a human
life" — bounds *inventing new* types; it is not licence to implement fewer.
Section 36 reads the same way for entity types. Implement the spec's list; do
not add to it.

**Not every edge endpoint is a world node.** `ASSIGNED_TO` and `ABOUT` point at
Tasks. Graph traversal asks `is_world_entity_id()` and skips them, and
`assemble_world_graph` drops the edge — so the World screen never draws an
arrow into a node it does not render. Section 16 gives tasks, waiting items,
documents, and memories their own inspector panels; that is where they belong,
not as unlabelled relationship rows.

**`toLower()` does not evaluate on a parameter.** `toLower(i.name) CONTAINS
toLower($needle)` silently matches nothing on NornicDB. Lower the parameter in
Python and call `toLower()` only on the property — `tasks.py` and `people.py`
already do. Found in Phase 9's item search.

**Resolved debt (kept for the reasoning): list-valued facts were JSON-blobbed.** Phases 7 and 9
project Appointment, Document, ServiceRequest, and ShoppingList as world nodes,
encoding list fields (a cart's items, an appointment's attendees) into a single
`facts` string and bypassing `validate_facts`' 500-character bound on purpose.
It works and it is consistent, but it defeats a bound that exists so an entity
cannot become an unbounded document store, and it makes those items
unqueryable — you cannot ask which lists contain milk. It was chosen partly to route around a harness rule.

Both are now paid off. `ShoppingList` items are `(:ShoppingItem)` nodes behind
a `CONTAINS` edge, so `find_lists_containing("milk")` answers. `ServiceRequest`
stores `availability` as a native string array — the original premise that
NornicDB "cannot store lists" was simply wrong; `Person.aliases` and
`Memory.entity_ids` have been arrays since Phase 0. Appointment, Event, and
Document had no list fields and needed no change. The world projections remain
for graph *display*, which is a `dict[str, str]` by design.

**Money moves only where a human is present.** `FINANCIAL_PAYMENT` is granted
to the Console and to nothing else. Hermes can read what is owed and say a bill
is due; it holds no path from a model's reasoning to a payment. This is
stricter than BUILD_SPEC requires — sections 56/57 would permit granting Hermes
the capability and letting the Console-only approval gate stop the money — and
the reasoning is recorded in `tests/spec/test_spec_fidelity.py`
(`CONSOLE_ONLY_BY_JUDGEMENT`) so it can be reversed deliberately.

**Money is a validated string, never a float.** `89.10` round-tripped through
binary floating point is `89.09999999999999`, and that value is hashed into an
approval a human agreed to. `validate_amount` refuses `89.1` for the same
reason: two spellings of one amount must not produce two hashes.

**The world graph projects; it does not own.** Persons and preferences are
written by their own repositories and read by the world repository through a
per-label projection. `create_entity` accepts only Household, Provider, and
Asset (`CREATABLE_ENTITY_TYPES`), and the NornicDB repository refuses the rest
so a future caller cannot write a `:Preference` with the wrong property shape.

**`coalesce()` in a SET clause stores its own expression text.** Writing
`SET p.x = coalesce(p.x, $param)` on a node being created with `$param` null
persists the literal string `"coalesce(p.x, null)"`. It reads as non-null, so
an "only set this if absent" idiom silently produces a truthy value. Found in
Phase 10, where it would have made every new payee look already-approved and
defeated section 72's gate. `coalesce` in a WHERE clause is fine — every other
use in `repositories/nornic/` is a read and evaluates correctly. Do the merge
in Python instead.

**Write visibility is not immediate under load.** The quirk below is not only
a transaction-boundary problem: in a full suite run, a read issued straight
after two appends returned one of them. A test that asserts *ordering* should
poll until the records it expects are present, so it is not incidentally
asserting write latency — see `_ordered_audit_ids` in
`tests/persistence/test_nornic_durable_work.py`. Anything that must observe
its own write immediately needs the same treatment.

**A node written by auto-commit `write()` may not be visible to a `MATCH`
inside an immediately following `write_many()` transaction.** Transaction-to-
transaction is fine; auto-commit-to-transaction races. Found in Phase 4. Where
an edge depends on a node another call just created, either write both in the
same `write_many`, or make the edge redundant — `Task.related_entity_ids` is
the source of truth precisely so a dropped `ABOUT` edge degrades instead of
losing the relationship.

**Undirected and variable-length Cypher patterns return phantom rows on
NornicDB.** Neighbourhood expansion is an explicit breadth-first walk of
directed single hops for that reason. Only `tests/persistence/` catches a
regression here — the fakes will stay green.

**NornicDB's admin password is fixed at data-directory initialisation.** A new
`nornicdb.env` pointed at existing data will fail to authenticate.

---

## Known gaps

Recorded in [SECURITY.md](SECURITY.md), not hidden. The 2026-08-18 full
audit ([docs/audits/2026-08-18-bugcheck.md](docs/audits/2026-08-18-bugcheck.md))
holds the complete findings list. The design-decision bugs it originally
recorded (payee approval split-brain, expired-approval deadlock, shopping
SUBMITTING wedge, verify-after-hold-expiry, unenforced config capability,
the Console's missing execute/verify surface, `request_code_change`
unexposed) were all fixed in the follow-up pass on the same branch; what
remains open are the spec gaps — Console placeholder screens (Calendar,
Knowledge, Files, Hermes), the Phase-0 Today view, the Voice Bridge,
Hermes skills, and universal search breadth. Highlights:

- World entity facts are current-only: there is no per-fact supersession
  chain, unlike preferences and memories. `get_entity_history` therefore
  reports the memories referencing an entity and says so in its `covers`
  field rather than implying more. (The durable audit log itself exists —
  Phase 4, section 62 — and answers "which client changed this?".)
- The World screen shows the *current* view. Section 15 also lists a
  temporal/current toggle; that is not built.
- **No provider has been verified against a real account.** Every third-party
  adapter — ElevenLabs, local ASR/TTS, calendar, email, telephony, browser,
  payment — ships built and disabled with a fake behind it, per BUILD_SPEC
  section 88. Enabling each in the Console is where real integration bugs will
  surface, and none of that has happened yet.
- Hermes itself has not been attached on this machine — it is not installed
  here. See [HERMES_INTEGRATION.md](HERMES_INTEGRATION.md).

---

## Documentation

[README](README.md) · [BUILD_SPEC](BUILD_SPEC.md) · [ARCHITECTURE](ARCHITECTURE.md) ·
[DATA_MODEL](DATA_MODEL.md) · [MCP_API](MCP_API.md) · [SECURITY](SECURITY.md) ·
[OPERATIONS](OPERATIONS.md) · [TESTING](TESTING.md) · [CONFIGURATION](CONFIGURATION.md) ·
[HERMES_INTEGRATION](HERMES_INTEGRATION.md) · [AGENTS](AGENTS.md)
