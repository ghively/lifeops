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

**CONTAINS + ORDER BY + LIMIT in one clause returns duplicate rows on
NornicDB.** The text-scan path emits one row per index posting rather than
one per node — a task that had been written to a few times came back seven
times from universal search (found live, 2026-08-19, deployment audit).
Neither `DISTINCT` (unreliable on aliased columns here, see
`shopping.py`) nor ordering by aliases is the fix: sort and limit through a
`WITH` stage before the projection, and dedupe by id in Python as the
backstop. `tasks.py`, `preferences.py`, `people.py`, and `memory.py` all do
this now; `tests/persistence/test_nornic_search.py` pins it. Plain listings
(no CONTAINS) are unaffected.

**Undirected and variable-length Cypher patterns return phantom rows on
NornicDB.** Neighbourhood expansion is an explicit breadth-first walk of
directed single hops for that reason. Only `tests/persistence/` catches a
regression here — the fakes will stay green.

**NornicDB's admin password is fixed at data-directory initialisation.** A new
`nornicdb.env` pointed at existing data will fail to authenticate.

---

## Known gaps

Recorded in [SECURITY.md](SECURITY.md), not hidden. Three audits hold the
original findings: [docs/audits/2026-08-18-bugcheck.md](docs/audits/2026-08-18-bugcheck.md)
(correctness bugs and spec-fidelity debt in code that exists — all fixed on
that branch), [docs/audits/2026-08-18-unimplemented-features.md](docs/audits/2026-08-18-unimplemented-features.md)
(BUILD_SPEC prose with no corresponding code at all, verified section by
section against the code rather than against this file), and
[docs/audits/2026-08-18-full-codebase-audit.md](docs/audits/2026-08-18-full-codebase-audit.md)
(a full eight-pass sweep of code, tests, CI, Console, and docs — its eight
P0 findings, including two approval-flow races and a broken exit-test pin,
were fixed the same day; its P1/P2 backlog and documentation corrections
are deliberately open, summarised in
[docs/REMAINING_WORK.md](docs/REMAINING_WORK.md) section 5). A follow-up pass
closed most of that second audit's findings — the audit doc's own
changelog records what changed and when; what follows here is the current,
much shorter list of what is still genuinely missing.

**Every disabled provider now has a working adapter behind it.** Calendar
(`calendar/caldav.py`), email (`email/imap_smtp.py`), browser
(`browser/real.py`, Playwright/Chromium), and telephony
(`telephony/twilio.py`, Twilio's REST API) are all real, protocol-correct
adapters, disabled per BUILD_SPEC section 88 until credentials exist (browser
needs none — see its module docstring). Telephony's `dial()` now resolves a
real destination number from the target provider's own `phone` fact
(`_phone_number_for_provider` in `core.py`) before POSTing to Twilio's Calls
resource with inline TwiML — the call still cannot hold an actual
conversation without the Voice Bridge (below), but nothing stops it from
being placed. The browser adapter launches Chromium, manages isolated
per-context profiles, and now has two real site adapters:
`core/lifeops/browser/sites/` registers Amazon and Instacart into
`_SITE_ADAPTERS`. Both were driven against the live sites from the deployment
host on 2026-08-19 — Amazon's search, guest cart, and cart re-confirmation all
verified end to end; Instacart's search verified, its cart refused because
Instacart has no guest cart. The earlier claim that this sandbox's Chromium
"cannot reach any live site at all" was true of the machine it was written on
and is not true of this one.

**Checkout is deliberately not automated on either.** `submit_order` raises a
specific error naming what it would need. Selectors for a purchase flow that
has never been run, sitting next to an action that spends real money, is the
speculative build section 105 forbids; the failure mode is a wrong order, not
a red test. Closing it means signing a store profile in once and verifying
against a real basket.

No payment-provider adapter exists at all — deliberate, not a stub (see
"Money moves only where a human is present" above).

- **Console.** Every section 10 nav entry now has a real screen — Calendar,
  Hermes, Files, and Knowledge replaced their `ComingInPhasePage` stubs, and
  Today shows approvals, waiting items, and calendar appointments alongside
  tasks. Universal search now covers all 12 spec'd categories (people,
  preferences, tasks, providers, assets, appointments, memory, documents,
  knowledge, bills, events, and actions/historical facts — the last two
  added directly against `AuditRepository`, guarded the same way the bills
  and audit blocks already were: `search()` skips them cleanly when no
  audit repository is configured, rather than raising). The World screen's
  temporal/current toggle now applies to every entity type, not only
  preferences — see the next bullet.
- **Voice.** The Voice Bridge does not exist as a runtime path — no duplex
  audio streaming code anywhere, not even scaffolding, which is a stronger
  gap than "no websocket scaffolding, no codec" suggests. Per BUILD_SPEC
  section 32's own diagram, the Voice Bridge sits between audio and "the
  same Hermes runtime," not LifeOps Core — combined with this file's rule
  against building a second agent or agent runtime, that orchestration
  likely belongs in Hermes itself, not this repository; a design check-in
  with the user surfaced this rather than building it unilaterally in the
  wrong place. The RTX resource-priority scheduler (section 31) and the
  latency instrumentation (section 33) are pure spec text with no
  corresponding code, and stay that way until the Voice Bridge that would
  use them exists somewhere.

  What *is* LifeOps Core's job — the swappable ASR/TTS provider layer
  (section 28) — is no longer a stub. `LocalASRProvider` (faster-whisper)
  and `LocalTTSProvider` (Kokoro, section 30's fallback/reference candidate)
  in `core/lifeops/voice/local.py` do real work once their runtime is
  installed: real transcription, real synthesis (including genuinely
  incremental streaming for TTS, bridging Kokoro's blocking per-segment
  generator onto the event loop from a worker thread), a real Load/Unload
  lifecycle, and an in-process model/pipeline cache so `VoiceService`
  rebuilding a provider fresh on every call doesn't reload multi-gigabyte
  weights each time. Neither package is installed by default — both live in
  `pyproject.toml`'s `voice-local` extra, with AGENTS.md's dependency
  justification written there, since this remains a GPU-class footprint most
  deployments never touch. This sandbox has no GPU and neither package
  installed, so `health()` correctly reports "not installed" here exactly as
  before; `tests/unit/test_voice.py` covers that real, honest path directly
  and covers the "installed" code paths against `sys.modules`-injected
  fakes standing in for the real libraries, the same way `ElevenLabsTTSProvider`
  is tested against `httpx.MockTransport` instead of the live API — neither
  adapter has been run against real hardware. Qwen3-TTS and Chatterbox Turbo
  (section 30's other TTS candidates) still have no adapter; the user asked
  to try all the candidates eventually, and Kokoro was the first, not the
  only intended one.
- **MCP surface.** Closed except for one deliberate absence: all 8 spec'd
  resources exist (`lifeops://me`, `today`, `waiting`, `household`,
  `approvals`, `entity/{id}`, `task/{id}`, `provider/{id}`), and every
  previously-HTTP-only read (`list_waiting_items`, `find_provider`,
  `get_task`, `list_appointments`, `get_bill`, `search_knowledge`) now has
  an MCP tool. `commit_payment` still has no MCP tool — that one is
  intentional, not a gap (see "Money moves only where a human is present").
  The `Knowledge` world entity type (section 36) now exists, backing
  `search_knowledge` and the Knowledge screen; `WorkflowTemplate` also
  exists (`workflow-templates` HTTP routes, the Routines screen) — neither
  is a world entity type in the section 36 sense, so this bullet previously
  conflated two different gaps that are both closed now regardless.
- **Memory.** Promotion (section 47) is implemented: `promote_memory` turns
  a confirmed `PREFERENCE_CANDIDATE` into a real preference
  (Console/HTTP-only, the same boundary `create_document` draws). The
  original "trust-hierarchy enforcement checks preference supersession
  only" claim was a false negative, not a real gap — `remember()`
  deliberately has no supersession check (a fresh memory is independent
  evidence, not a competing claim, per section 46's own "external content
  creates evidence, it does not create user authority"); `correct_memory`
  is where a competing claim is actually asserted, and it was already
  trust-checked via `may_supersede` — `tests/unit/test_memory.py`'s
  `TestMemoryTrustHierarchy` now names this explicitly so a future grep
  finds it rather than concluding otherwise again.
- **Hermes self-configuration** (sections 73-76) is wired now, without
  inventing a second scheduler (section 55): `routine_template`, `cron_job`,
  and `reminder` all route through the existing `WorkflowTemplate` mechanism
  (`save_workflow_template`/`list_workflow_templates`/`due_routines`/
  `delete_workflow_template`, exposed over both MCP and HTTP), `skill` and
  `non_critical_prompt` go through `propose_self_change` as a pure gate — it
  validates and files a request, it does not write skill content itself —
  and `preference` uses the save path that already existed. All of this is
  now reachable over MCP, closing the one gap the earlier audit found (the
  generic entry point existed but wasn't exposed). Nine Hermes skills are now
  instantiated in `hermes/skills/lifeops/` (personal-core, daily-brief,
  weekly-review, waiting-for-manager, provider-manager, appointment-manager,
  calendar-manager, email-triage, shopping-manager) — the template is no
  longer unused. The six "Later"-tier skills BUILD_SPEC itself defers are
  still not written, deliberately, matching the spec's own tier.
- **Chaos tests** (section 86) now cover all 16 spec'd failure scenarios —
  see `tests/chaos/` (13 scenarios, fakes-only, in `make test-fast`) and
  `tests/e2e/test_chaos_duplicate_mcp_request.py` (scenario 6, needs a live
  NornicDB and a real MCP subprocess). Three of the sixteen (DeepSeek
  timeout, local ASR crash, local TTS crash) have no adapter or runtime to
  fail yet, so those are documented, honest skips rather than fabricated
  tests — `tests/chaos/test_documented_gaps.py` explains each. One test run
  found a genuine, previously-unknown gap rather than just filling in
  coverage: a repository write failure between committing an action and
  recording its result was not caught anywhere in `execute_action`, so the
  action stranded in `EXECUTING` (the approval was still safely consumed,
  so nothing could retry it into a duplicate external commitment — see
  `TestCrashBetweenCommitAndRecordResult` in
  `tests/chaos/test_outbox_and_transport_failures.py`). This is now
  bounded-retried rather than stranding on the first failure:
  `record_action_result` retries a `RepositoryError` up to three times with
  a short delay before giving up (`_record_result_with_retry` in
  `core.py`), so a transient write failure recovers on its own —
  `TestRecordActionResultRetry` covers both the recovery and the bound
  (a failure past the retry budget still strands, deliberately: an
  unlimited retry would just move the same distributed-systems question
  to "how long is too long," not answer it).
- World entity facts now carry the same per-fact supersession chain
  preferences and memories do — `EntityFact`, `update_facts`, and
  `fact_history` (BUILD_SPEC section 16), following the identical
  close-old/open-new/`SUPERSEDES`-edge pattern `Preference` established.
  `get_entity_history`'s `covers` field lists both what it now reports:
  every version of every fact the entity has carried, and the memories
  referencing it. (The durable audit log itself exists — Phase 4, section
  62 — and separately answers "which client changed this?".)
- The voice acceptance scenario (section 103) has no automated coverage of
  its Console walkthrough, since the Voice Bridge doesn't exist. The
  provider-configuration scenario (section 104) does have a real, passing
  test (`test_phase0_exit.py`) — "Both acceptance scenarios pass (sections
  101 and 102)" above undercounts this; 104 passes too, and only 103 is
  genuinely incomplete.
- Hermes is attached (2026-08-19, host `gh-ai`): stdio MCP as
  `hermes-personal`, all 52 tools discovered. The memory-provider plugin is a
  separate switch and is not flipped.

A consolidated, standalone accounting of every item above — grouped by
whether it's blocked by this environment, deferred by BUILD_SPEC itself, out
of this repository's scope by design, or waiting on the user — lives in
[docs/REMAINING_WORK.md](docs/REMAINING_WORK.md).

---

## Documentation

[README](README.md) · [BUILD_SPEC](BUILD_SPEC.md) · [ARCHITECTURE](ARCHITECTURE.md) ·
[DATA_MODEL](DATA_MODEL.md) · [MCP_API](MCP_API.md) · [SECURITY](SECURITY.md) ·
[OPERATIONS](OPERATIONS.md) · [TESTING](TESTING.md) · [CONFIGURATION](CONFIGURATION.md) ·
[HERMES_INTEGRATION](HERMES_INTEGRATION.md) · [AGENTS](AGENTS.md) ·
[REMAINING_WORK](docs/REMAINING_WORK.md)
