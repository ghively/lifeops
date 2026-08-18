# Full audit — unimplemented features and unfinished spec

**Date:** 2026-08-18 · **Branch:** `claude/unimplemented-features-spec-audit-vl18ze`

Method: six independent review passes, one per cluster of BUILD_SPEC sections
(Console screens 9–21/77; Voice 27–33; MCP/world/memory core 34–51;
outbox/integrations 52–72; Hermes self-configuration 73–76;
operations/security/CI/acceptance 78–86/101–104), each verified against the
code rather than against repo documentation. This is a companion to
[2026-08-18-bugcheck.md](2026-08-18-bugcheck.md), which covered correctness
bugs and spec-fidelity debt in already-built code; this audit instead asks
*what BUILD_SPEC describes that has no working implementation at all*, and
where repo documentation's account of that is incomplete or optimistic.

A capability behind a disabled provider with a real, working adapter (the
BUILD_SPEC section 88 policy: "ship built and disabled with a fake behind
it") is **not** counted as a gap below unless noted. What follows is code
that does not exist, or exists only as a stub/Protocol/enum with no
executable path.

---

**Superseded, same day, same branch:** most of what this table and the
detailed sections below call "not implemented" was subsequently built — see
"Follow-up (same day, same branch): what closed" at the end of this document
for what changed, and CLAUDE.md's "Known gaps" for the current living
summary. The table and sections below are left exactly as originally
written, as the point-in-time record.

## Summary

| Area | State |
|---|---|
| Core spine, task/preference/memory domain, capabilities, outbox/approval/audit | Solid — matches CLAUDE.md's claim |
| Calendar, Email, Bills, Financial policy | Real, working adapters (calendar/email disabled by policy; no payment adapter by design) |
| Console: Today, Waiting, Tasks, World, Entity Inspector, Memory, Activity, System | Implemented, several with named partial gaps below |
| Console: Calendar, Knowledge, Files, Hermes screens | Not implemented — literal placeholder pages |
| Voice: ElevenLabs adapter, provider abstraction, mode selection | Real and working |
| Voice: local ASR/TTS, resource priority, Voice Bridge, latency objectives | Not implemented — no runtime, no scheduler, no audio path, no instrumentation |
| Browser, Telephony adapters | Not implemented — Protocol/stub only, unlike calendar/email |
| Shopping checkout | Blocked on the Browser gap — no live execution path |
| MCP resources, several read tools, Knowledge/WorkflowTemplate entities | Partially implemented — 3 of 7 resources, several named tools missing |
| Memory promotion, trust hierarchy for memory | Not implemented as designed — filter exists, no pipeline; trust checked for preferences only |
| Hermes self-configuration | Mostly unimplemented — only code-change-requests and workflow-templates (Console-only) work |
| Hermes skills | Zero skills instantiated; template only |
| Hermes itself | Not attached to this machine — confirmed accurate |
| Chaos/failure-injection tests | 2 of 16 spec'd scenarios covered |
| Voice acceptance scenario (103) | Cannot be exercised — no Voice Bridge to walk the Console steps |
| Provider Configuration acceptance (104) | Has a real, passing test — CLAUDE.md undercounts this; only 101 and 102 are credited there |

---

## Console (BUILD_SPEC §9–21, §77)

- **§9 Knowledge-OS migration** — done; no SQLite/Qdrant dependency remains.
- **§10 Navigation** — 4 of 14 routes (`/calendar`, `/knowledge`, `/files`,
  `/hermes`) render `ComingInPhasePage.tsx` — an icon, a sentence, a link
  back. No data fetching, no components (`App.tsx:63-96`).
- **§11 Today** — sources tasks only. Approvals, Waiting items, and calendar
  events (all spec'd Today content) are absent; the page's own footer says so
  (`TodayPage.tsx:168-181`).
- **§12 Needs Attention** — the 8 spec'd categories collapse into 3 task
  states (`NEEDS_APPROVAL`, `BLOCKED`, `FAILED`); no distinct clarification/
  MFA/price-change/conflict typing.
- **§13 Waiting, §14 Tasks** — fully implemented.
- **§15 World Screen** — implemented except the temporal/current toggle
  (only a history query exists, no point-in-time switch) — matches CLAUDE.md.
- **§16 Entity Inspector** — fully implemented.
- **§17 Memory Screen** — implemented; type filters expose the underlying
  memory types (`semantic`, `episodic`, `preference_candidate`, …) rather
  than the spec's named views (Preferences / Personal facts / Relationships /
  Procedures).
- **§18 Knowledge and Files** — not implemented; no backend route, no
  Knowledge entity type to back it (see §36 finding below).
- **§19 Universal Search** — searches only people, preferences, tasks — 3 of
  12 spec'd categories. `core.py:3703-3730` docstring: "Phase 1 is a
  case-insensitive substring match; ranking and semantic retrieval arrive
  with the memory layer." No hybrid/semantic search, no graph expansion.
- **§20 Hermes Screen** — not implemented; placeholder only.
- **§21 Activity Screen** — implemented but shows raw technical fields
  (`intent`, `tool`, `client`, `trace_id`) rather than the spec's
  human-readable narrative with details behind an expand action.
- **§77 System Health** — health, provider state, safe-mode toggle, and
  capability grants are shown; no "view recent failures" panel and no
  "restart suggestions" — no backing route exists for either.

## Voice (BUILD_SPEC §27–33)

- **§27 ElevenLabs, §28 provider abstraction, §29 voice modes** — fully
  implemented: real REST calls (`voice/elevenlabs.py`), a clean
  `TTSProvider`/`ASRProvider` Protocol, and mode-pinning logic in
  `voice/service.py`. No API key configured — expected, not a gap.
- **§28/§30 local ASR/TTS** — a step short of section 88's own bar: unlike
  ElevenLabs's fake, the local adapter has no working path even in
  simulation — `transcribe`/`synthesize`/`stream` unconditionally raise
  (`voice/local.py:98-158`), and `health()` always reports `False`
  regardless of whether `faster_whisper` is installed. `TTS_RUNTIME_CANDIDATES`
  is an empty tuple — the comment says the candidate model names in the spec
  aren't confirmed importable packages, so nothing was written against them.
- **§31 RTX 3060 Resource Priority** — not implemented at all. No scheduler,
  queue, or arbitration code anywhere in the repo.
- **§32 Voice Bridge** — does not exist as a runtime path. No file
  implementing duplex audio streaming exists anywhere. The only websocket
  code is the Console's change-notification stream (`api/events.py`),
  unrelated to audio. `tests/integration/test_voice_shared_state.py` states
  outright that no working local voice runtime or Hermes exists in this
  repo, and proves only that state *would* route through the same MCP path
  if voice existed — by simulating a saved preference through Hermes's MCP
  identity, not through any audio path. This is a stronger gap than
  CLAUDE.md's "no websocket scaffolding, no codec" phrasing suggests: the
  bridge component itself was never started.
- **§33 Voice Latency Objectives** — no p50/p95/p99 measurement, no barge-in
  tracking, none of the eight spec'd instrumentation points. The only
  latency code found (`voice/service.py:283-293`) times provider health
  checks for the Console's connectivity indicator, not conversational turns.

## MCP / World / Memory core (BUILD_SPEC §34–51)

Confirmed solid, no gaps beyond what's already disclosed: client identity
(§34), capability manifest (§35), canonical IDs (§37), identity handling
(§38), all 20 relationship types (§39), repository abstraction (§41), memory
architecture/provider shape (§42–43), memory safety invariants (§44).

Gaps found:

- **§48 MCP Resources — 3 of 7 implemented.** Only `lifeops://me`,
  `lifeops://today`, `lifeops://waiting` exist
  (`mcp/resources/__init__.py:79,98,129`). `lifeops://household`,
  `lifeops://approvals`, `lifeops://entity/{id}`, `lifeops://task/{id}`,
  `lifeops://provider/{id}` do not exist. Code comments call these "the
  first three," but no other document flags the remaining four as
  outstanding.
- **§50 Expanded Read Tools — several named tools missing from MCP, though
  some exist server-side.** `get_task`, `list_appointments`,
  `get_appointment`, `get_bill`, `list_bills` exist as `LifeOpsCore` methods
  but are wired only to `api/http.py`, never exposed as MCP tools.
  `list_waiting_items`, `find_provider`, `get_asset`/`list_assets`, and
  `search_knowledge` are not implemented anywhere, core or MCP.
- **§36 World Model — `Knowledge` and `WorkflowTemplate` entity types are
  entirely unimplemented.** `WorldEntityType` has 10 of the spec'd members;
  no domain class, repository, or world label exists for either. This is
  why `search_knowledge` (§50) has nothing to search.
- **§51 Expanded Action Tools — payment tools incomplete.** `prepare_payment`
  and `commit_payment` as named by the spec don't exist; `core.py` has
  `prepare_bill_payment` (a different, bill-scoped tool) and no
  `commit_payment` equivalent.
- **§47 Memory Promotion — filter, not pipeline.** `PREFERENCE_CANDIDATE`
  memories are "parked for confirmation" per their own docstring, but no
  code anywhere converts one into a real `Preference`. `validate_durable_content`
  decides what gets saved at write time; there is no confirm/promote tool.
- **§46 Trust Hierarchy — enforced only for preferences.** `may_supersede`/
  `authority_of` are called at exactly two preference-supersession sites;
  `remember()` never checks a new memory's `source_type` against an
  existing one's. Tests confirm the same scope — only
  `tests/unit/test_preferences.py` exercises trust.
- **§40 Temporal State** — confirmed exactly as CLAUDE.md states: Preference
  and Memory have full supersession chains; generic world entities
  (Household, Provider, Asset, …) do a bare overwrite with no validity
  window (`repositories/nornic/world.py:190-206`).

## Outbox and integrations (BUILD_SPEC §52–72)

- **§52–64 (context, task semantics, waiting items, durable continuation,
  risk classes, two-phase commit, approvals, outbox, idempotency, audit,
  calendar, email)** — implemented and well-evidenced. Calendar
  (`calendar/caldav.py`) and Email (`email/imap_smtp.py`) both have real,
  working protocol adapters, disabled by default per policy — not a gap.
- **§65–66 Web and Browser — genuine gap.** `browser/real.py`
  (`RealBrowserWorker`) contains no automation code at all: every method
  immediately raises `ProviderError`, and `health()` always returns `False`
  even with Playwright/Selenium installed. Unlike calendar/email, there is
  no working code path here even if enabled.
- **§67 Provider Workflow** — implemented, rides the outbox machinery
  correctly.
- **§68–69 Telephony — genuine gap, more bare than Browser's.**
  `telephony/` has only a Protocol and a fake — no `real.py` exists at all.
  `telephony/__init__.py` states plainly: "this package ships with no
  working real transport." The structured-call-result data shape (§69) is
  correctly modeled and exercised by the fake — only the transport is
  missing.
- **§70 Shopping — blocked on the Browser gap.** Checkout routes through
  `BrowserProviderService` → `RealBrowserWorker`; since that has no working
  path, shopping can only ever succeed against the fake. The approval gate,
  idempotency, and total-display logic around checkout are real.
- **§71 Bills, §72 Financial Actions** — implemented correctly. Amount
  validation, payee re-approval revocation, and evidence-required settlement
  all check out. No `PaymentProvider` Protocol/adapter exists at all — this
  is deliberate (matches CLAUDE.md's "money moves only where a human is
  present"), not a stub: `execute_action`'s executor table excludes
  `PREPARE_PAYMENT`/`ADD_PAYEE` entirely, and payment is completed manually
  outside LifeOps.

## Hermes self-configuration (BUILD_SPEC §73–76)

- **§73 Self-Configuration — mostly unwired.** The protected/permitted
  classification rules are real and tested (`domain/self_config.py`), but of
  the seven permitted targets only `workflow_template` has a working
  save/list/delete path — and it's reachable only over HTTP (the Console),
  not MCP (Hermes). `skill`, `preference`, `cron_job`, `reminder`,
  `non_critical_prompt`, `routine_template` have no save/apply method
  anywhere; they exist only as enum values exercised in unit tests.
  `propose_self_change`, the one generic entry point, is not exposed via
  MCP or HTTP — dead code outside tests.
- **§74 Code Change Requests — the one piece that's real and MCP-exposed.**
  `request_code_change()` writes a JSON file to `changes/requests/`. That
  directory currently holds none — it is, today, the entire usable
  self-configuration surface available to Hermes over MCP.
- **§75 Hermes Skills — zero instantiated.** The eight named initial skills
  (personal-core, waiting-for-manager, daily-brief, weekly-review,
  provider-manager, appointment-manager, calendar-manager, email-triage)
  have no skill files anywhere. No skill-loading or skill-execution code
  exists. `hermes/skills/README.md` states outright: "Phase 0 ships no
  skills."
- **§76 Skill Template** — the template text is reproduced verbatim in the
  README and BUILD_SPEC; no file in the repo instantiates it.
- **"Hermes not attached"** — confirmed accurate. `hermes/` is scaffolding
  for a future client (a bootstrap script that prints launch JSON, config
  templates, an unregistered memory-provider plugin); no process, config, or
  credential anywhere runs a live Hermes instance.

## Operations, security, CI, acceptance scenarios (BUILD_SPEC §78–86, §101–104)

- **§79 Backups, §80 Restore Test** — real and automated, not just
  documented. `scripts/backup.sh` is a working script; `tests/persistence/
  test_backup_restore.py` drives it against a disposable NornicDB and
  asserts a full state round-trip, and runs in CI on every push. It is not,
  however, separately scheduled on a period cron the way §80 describes —
  it only runs at normal CI cadence.
- **§81 Nornic Escape Plan — partial.** The architectural precondition
  (Cypher confined to `repositories/nornic/`, domain layer unaware of the
  database) is real and enforced by design. No actual export or migration
  script/test exists — aspirational beyond the interface discipline.
- **§83 Safe Mode, §84 Emergency Stop** — implemented and tested
  end-to-end, including a dedicated policy test and Console component tests.
- **§85 CI** — mostly implemented; ruff, mypy, the full pytest suite
  (including `tests/spec` and `tests/persistence`), a tracked-secret check,
  a prohibited-dependency check, and Console typecheck/test/build all run in
  `.github/workflows/ci.yml` against a real matrix (Python 3.11/3.12,
  NornicDB service container). The spec's separately named test categories
  (domain-state, repository, MCP schema, HTTP API, approval, idempotency,
  security) are not separate CI steps — folded into `unit`/`integration`/
  `spec`, which is defensible but not a literal match.
- **§86 Failure/Chaos Tests — mostly unimplemented.** Of 16 spec'd
  scenarios, only Nornic restart and duplicate-request/idempotency have real
  coverage. No tests exist for DeepSeek timeout, Hermes restart, Nornic
  unavailability (distinct from restart), LifeOps crash, calendar/email
  timeout, browser crash, ElevenLabs timeout/partial stream, local ASR/TTS
  crash, or SIP disconnect.
- **§101 Electrician, §102 Shared-Agent** — real, passing e2e tests, as
  CLAUDE.md claims.
- **§103 Voice Acceptance — cannot be exercised.** A real integration test
  proves the state-sharing claim by simulation, but the spec's 15-step
  Console walkthrough (including a live voice session) has no automated
  coverage because the Voice Bridge doesn't exist (§32).
- **§104 Provider Configuration — real, passing test, and undercounted by
  CLAUDE.md.** `tests/e2e/test_phase0_exit.py::TestFreshDeploymentNeedsNoCredentials`
  is explicitly docstringed as covering this section and asserts every
  provider serves `not_configured`/`disabled` with zero credentials.
  CLAUDE.md's "Both acceptance scenarios pass (sections 101 and 102)" is
  accurate as far as it goes but leaves out that 104 also passes; only 103
  is genuinely incomplete.

---

## What this changes about the record

CLAUDE.md's "Known gaps" section (Console placeholder screens, the Phase-0
Today view, the Voice Bridge, Hermes skills, universal search breadth) is
accurate but incomplete. Not mentioned there, and confirmed missing by this
audit: the Browser and Telephony adapters (Calendar/Email have real adapters
behind their disabled flag; these two do not), 4 of 7 MCP resources and
several named read/action tools, the `Knowledge`/`WorkflowTemplate` world
entity types, memory promotion as a working pipeline, trust-hierarchy
enforcement for memory (only preferences are checked), the RTX resource
scheduler and voice latency instrumentation, most of Hermes
self-configuration beyond code-change-requests, and 14 of 16 chaos-test
scenarios. None of this is a correctness bug — each is BUILD_SPEC prose with
no corresponding code, generally in later-phase or aspirational sections of
the spec rather than in the Phase 0–4 spine the acceptance tests exercise.

---

## Follow-up (same day, same branch): what closed

Everything above is left as originally written — a point-in-time snapshot.
This section records what changed afterward, on the same branch, so the two
stay distinguishable rather than silently merged into one "current" document.
CLAUDE.md's "Known gaps" section carries the living, current summary; this
is the changelog behind it.

**Closed:**

- **Console.** All 4 placeholder screens (§10, §18, §20) replaced with real
  ones: Calendar, Hermes, Files, Knowledge. Today (§11) now shows approvals
  and waiting items alongside tasks and calendar appointments. Needs
  Attention (§12) categorizes into named buckets instead of 3 raw task
  states, labelled as a best-effort heuristic rather than the spec's real
  backend typing. World screen (§15) gained a temporal/current toggle,
  honestly scoped to preferences — the only entity type with real
  supersession data to toggle to. Memory screen (§17) exposes the spec's
  named views (Preferences / Personal facts / Relationships / Procedures) as
  filters over the underlying types. Activity screen (§21) now narrates
  human-readable sentences with technical detail behind an expand action.
  System screen (§77) gained a recent-failures panel (reading the durable
  audit log) and restart suggestions (text only, never a button that
  executes anything). Universal search (§19) widened from 3 to 10 of 12
  categories — only events and actions/historical facts remain, since
  neither has a domain model to search.
- **MCP surface (§48, §50, §51, §36).** All 8 spec'd resources now exist
  (5 added: household, approvals, entity/{id}, task/{id}, provider/{id}).
  Every previously-HTTP-only read tool (`get_task`, `list_appointments`,
  `get_appointment`, `get_bill`, `list_bills`) and every previously-missing
  one (`list_waiting_items`, `find_provider`, `get_asset`/`list_assets`,
  `search_knowledge`) is now MCP-exposed. The `Knowledge` world entity type
  (§36) exists, backing `search_knowledge`; a `WorkflowTemplate` mechanism
  also exists (`workflow-templates` HTTP routes, the Routines screen),
  though not as a §36 world entity type — a different shape than the
  original finding assumed, but the underlying gap (nowhere to save a
  routine) is closed either way. `commit_payment` remains deliberately
  MCP-unexposed (§51's note on payment tools stands).
- **Memory (§46, §47).** `promote_memory` (Console/HTTP-only) turns a
  confirmed `PREFERENCE_CANDIDATE` into a real `Preference` — the
  confirm/promote pipeline §47 describes. The §46 trust-hierarchy finding
  turned out to be a false negative on closer read, not a gap: `remember()`
  correctly has no supersession check (a fresh memory is independent
  evidence per §46's own text, not a competing claim), and `correct_memory`
  — the actual competing-claim site — was already trust-checked via
  `may_supersede`. `tests/unit/test_memory.py::TestMemoryTrustHierarchy` now
  names this explicitly.
- **Browser (§65–66) and Telephony (§68–69) adapters** are real, not stubs
  — but each surfaced a distinct, honest reason it can't do everything the
  spec envisions yet, discovered while building rather than assumed going
  in. Browser: `browser/real.py` genuinely launches Chromium and manages
  isolated per-context persistent profiles (proven against a real browser,
  `tests/unit/test_browser.py`), but no site-specific automation exists for
  any actual shopping site — nothing in this codebase has ever named a
  retailer, and inventing scraping logic for one nobody chose, untested
  against a live site, would be exactly the speculative build §105 warns
  against. `search`/`build_cart`/`submit_order` report that gap specifically
  through `_SITE_ADAPTERS`, an empty, documented extension point. Shopping
  checkout (§70) inherits this — it is no longer blocked on a missing
  adapter, but on the same missing site integration. Telephony:
  `telephony/twilio.py` genuinely places/tracks/hangs up/sends DTMF on real
  calls via Twilio's REST API (verified against Twilio's documented
  response shapes with a mocked transport — no live account exists to test
  against, unlike the browser adapter). `dial()` always refuses, though,
  because building it surfaced a deeper, pre-existing gap: `CallObjective`
  has never carried a destination phone number anywhere in this codebase —
  not in the objective, not in `_prepare_provider_contact`, not in the
  Protocol signature. That is a separate, cross-cutting domain-model change
  this work was not scoped to make. Layered on top, no call could meet its
  objective without the Voice Bridge (§32, still not implemented) to hold
  the actual conversation.
- **Chaos tests (§86).** All 16 scenarios now have real coverage —
  `tests/chaos/` (13, fakes-only) and
  `tests/e2e/test_chaos_duplicate_mcp_request.py` (scenario 6, needs a live
  NornicDB). 3 (DeepSeek timeout, local ASR crash, local TTS crash) are
  honest, documented skips: no client/runtime exists yet for the failure to
  happen to. One test run found a genuine new gap: a repository write
  failure between committing an action and recording its result escapes
  `execute_action` uncaught, stranding the action in `EXECUTING` — the
  outbox's actual invariant ("no duplicate external commitments") still
  holds, since the spent approval blocks any retry, but the stranded-action
  recovery itself is unfixed, a distributed-systems design question rather
  than a mechanical bug.

**Still open**, matching CLAUDE.md's "Known gaps" exactly and deliberately
left that way — both need the user's design input, not unilateral building:
the Voice Bridge (§32, and everything downstream of it: RTX scheduling §31,
latency instrumentation §33, the §103 acceptance walkthrough, and telephony
actually holding a conversation) and Hermes self-configuration content
(§73–76: the `skill`/`cron_job`/`reminder`/`non_critical_prompt`/
`routine_template` save/apply paths, `propose_self_change` exposure, and the
eight named Hermes skills — zero instantiated).
