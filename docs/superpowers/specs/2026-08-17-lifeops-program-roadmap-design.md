# LifeOps Program Roadmap — Phases 4 through 11

**Date:** 2026-08-17
**Status:** Approved design, not yet executed
**Scope:** The remaining build, from Phase 4 to the two acceptance scenarios

[BUILD_SPEC.md](../../../BUILD_SPEC.md) is authoritative. Where this document
disagrees with it, the spec wins. [AGENTS.md](../../../AGENTS.md) holds the
working rules; this roadmap sequences them and makes two of them mechanical.

---

## 1. Purpose

This is the program-level plan. It is deliberately **not** an implementation
spec for eight phases — writing Phase 8's telephony flows today, before the
approval model they depend on exists, would produce fiction that needs
rewriting anyway.

What this document fixes:

- the order phases are built in, and the gates between them
- which BUILD_SPEC section 36 entity type is owned by which phase
- the pipeline every phase follows
- the enforcement harness that makes that pipeline self-checking
- cross-cutting decisions and the gaps being carried forward

Each phase then gets its own brainstorm → spec → plan cycle, written
immediately before it is built, informed by what the previous phase taught.

---

## 2. Where the build stands

Phases 0 through 3 are complete:

| Phase | Delivered |
|---|---|
| 0 | The spine: Hermes → LifeOps MCP → LifeOps Core → NornicDB. Person, Preference, Task. Five MCP tools. |
| 1 | Console foundation, optional bearer auth, event stream, universal search, activity feed. |
| 2 | Memory provider on NornicDB with BM25 recall, temporal supersession, three MCP tools. |
| 3 | World graph, entity inspector, Household/Provider/Asset, preference projection, four MCP read tools. |

Twelve MCP tools, 427 Python tests, 106 Console tests, `make check` green.

**Phase 3 is complete and verified but not yet committed** — it sits in the
working tree. Committing it is step 0 of this roadmap (see section 6).

---

## 3. Decisions taken

Three decisions shape everything below.

**Scope is all eleven phases**, ending with both acceptance scenarios — the
Electrician scenario (section 101) and the Shared-Agent scenario (section 102).

**Third-party providers are built disabled.** Per AGENTS.md and BUILD_SPEC
section 88, no phase asks for a runtime credential. Every provider phase ships
an adapter, a test double, a registry entry, a Console form rendered from its
schema, and a working Test button — left disabled. The user enables each in the
Console when ready, and live verification happens together at that point. Every
secret stays in the user's hands.

**Work is contract-first, then parallel.** Within a phase, the domain models,
repository Protocols, fakes, and `LifeOpsCore` signatures land and commit as one
unit *before* adapters, Console, and tests fan out. Section 5 explains why this
ordering is load-bearing rather than stylistic.

---

## 4. The enforcement harness

### Why it exists

Phase 3 was built by four parallel agents and produced four incompatible views
of one API: two different `world_graph()` signatures, an HTTP adapter written
against an invented `EntityDetail` shape, a Console that sent `type` where the
server expected `rel_type`, and forty passing tests that exercised a stub of the
very service that had never been written. The Console screen was never routed.

None of that happened for lack of rules. AGENTS.md's "Adding a domain entity"
recipe already required a fake (step 4), operations on `LifeOpsCore` (step 5),
and persistence tests (step 7). All three were skipped and nothing noticed.

A second failure followed: the section 39 relationship vocabulary was narrowed
from twenty types to four, and the narrowing was documented as if it were a
design principle rather than a deviation.

Both classes of failure are mechanically detectable. With seven phases left,
detecting them by review alone is not a plan.

### The four suites

All live in `tests/spec/`. They need no database, so the `test-fast` target in
the Makefile is extended to include the directory — currently it runs
`tests/unit tests/policy tests/integration`. That one-line change is part of
building the harness, so the guards run on every fast check rather than only in
full CI.

**`test_spec_fidelity.py`** — parses the fenced lists out of `BUILD_SPEC.md` by
section heading and compares them against the code.

- Section 39: exact set equality against `WorldRelationship`. All twenty types,
  no more, no fewer.
- Section 36: the world graph renders a deliberate subset, so equality is wrong
  here. Instead the code declares `PHASE_FOR_ENTITY_TYPE`, mapping every one of
  the eighteen canonical entity types to the phase that owns it, and the test
  asserts that map covers the spec's list exactly. Deferring a type becomes an
  explicit, reviewable entry rather than a silent omission.

Extended per phase as new enumerations land: section 54 (WaitingItem fields),
section 59 (Approval model), section 60 (Action record fields).

**`test_protocol_conformance.py`** — for every Protocol in
`repositories/interfaces.py`, assert that a fake exists in
`repositories/fakes/` and that its method signatures match the NornicDB
implementation's. Catches the missing `FakeWorldRepository` outright, and
catches fake/real drift — which bit twice in Phase 3, once when the fake
silently returned `None` where the real repository raised, and once over the
preference projection.

**`test_no_stub_cores.py`** — AST-scans `tests/` for class definitions whose
methods overlap `LifeOpsCore`'s public surface beyond a threshold. Faking a
repository is correct; faking the core service is a defect, because it tests the
adapter against the test author's belief about the core rather than the core.
This is precisely the line that held in Phase 2 and broke in Phase 3.

**`test_cypher_coverage.py`** — every module in `repositories/nornic/` except
`client.py` must have a matching `tests/persistence/test_nornic_<name>.py`. The
in-memory fakes stayed green through two genuine Cypher defects in Phase 3;
only the persistence suite can catch that class of bug.

### Cost

Roughly half a day, shipping no user-visible capability. It is paid once and
protects seven phases.

---

## 5. The per-phase pipeline

AGENTS.md's pipeline, with the contract step made explicit:

```
READ SPEC → CONTRACT (commit) → FAN OUT → TEST → ACCEPTANCE
→ ADVERSARIAL REVIEW → LIVE SMOKE → DOCUMENT → COMMIT
```

**READ SPEC** — quote the governing sections into the phase spec. Enumerations
in those sections get pinned in `tests/spec/` before implementation starts.

**CONTRACT** — one commit containing domain models and pure rules, repository
Protocols, in-memory fakes, and `LifeOpsCore` method signatures with capability
checks. Nothing else. This is AGENTS.md steps 1–5.

The ordering is the whole point. Phase 3's parallel agents each invented a
contract because there was nothing committed to agree on. A committed contract
is also the cheapest possible handoff between sessions: a fresh agent reads it
instead of reconstructing a transcript.

**FAN OUT** — HTTP routes, MCP tools, Console screens, and tests proceed in
parallel against the committed contract. These are genuinely independent once
the contract exists.

**TEST** — per AGENTS.md: domain rules in `tests/unit`, capability behaviour in
`tests/policy`, API contract in `tests/integration`, Cypher and graph shape in
`tests/persistence`, phase acceptance in `tests/e2e`.

**ACCEPTANCE** — the phase's own criteria, taken from its BUILD_SPEC section.

**ADVERSARIAL REVIEW** — a fresh reviewer hunting specifically for the Phase 3
failure modes: adapters calling core methods that do not exist, tests asserting
against stubs, Console payloads that disagree with server schemas, screens that
are built but never routed, and spec enumerations quietly narrowed.

**LIVE SMOKE** — exercise the phase against the running stack, then remove the
smoke data and confirm removal. Every Phase 3 world route would have failed on
its first call, because the core methods they invoked did not exist; forty
passing tests never revealed it, and only running the thing would have.

**DOCUMENT** — README phase table, DATA_MODEL.md, MCP_API.md, ARCHITECTURE.md,
CLAUDE.md, and this roadmap's status.

**COMMIT** — only after the above. Git mutations are confirmed with the user
each time.

A phase is done when: the harness is green, `make check` is green, the live
smoke passed and was cleaned up, and the docs are updated.

---

## 6. Sequence

Phases are executed strictly in order. AGENTS.md: *"Do not start the next phase
until the current one's acceptance criteria pass."* No resequencing, including
for phases that look independent.

**Step 0 — Commit Phase 3.** It is complete and verified but sitting in the
working tree.

**Step 1 — Build the enforcement harness** (section 4).

**Step 2 onward — the phases.**

### Phase 4 — Durable Work (section 93)

The backbone of the remaining build. It carries seven of the sixteen steps in
the Electrician scenario, and section 99 makes it a hard gate for Phase 10:
payments cannot be enabled until the outbox, approvals, idempotency,
verification, and audit are *proven*.

Introduces: **WaitingItem** (section 54), **Action** (section 60), **Approval**
(section 59).

Also: expanded task state machine, due-work worker, follow-up logic,
verification states, two-phase commit for sensitive actions (section 57),
idempotency keys generated and persisted by LifeOps, never invented by the model
(section 61), the durable audit log (section 62), and the Today/Waiting UI.

The one genuinely new architectural decision in the whole remaining build lands
here: the **due-work worker** is LifeOps's first background process. Everything
to date is request/response. In-process asyncio task versus a separately
supervised process determines how restart-resilience is tested, and it is
decided in the Phase 4 spec rather than defaulted into.

Acceptance (section 93): work survives conversation exit, Hermes restart,
LifeOps restart, and NornicDB restart.

### Phase 5 — Configuration + Voice Quick Path (section 94)

ElevenLabs provider and GUI setup, voice discovery, voice preview, streaming
TTS, selectable voice and model, provider health, voice mode controls. Then the
Voice Bridge integrates with Hermes. Adapter ships disabled.

### Phase 6 — Local Voice (section 95)

Local ASR/TTS adapters with Console model and device selection, load/unload,
health, latency indicators, active and fallback provider. Verify the same Hermes
and the same LifeOps state across voice and text.

### Phase 7 — Calendar + Email (section 96)

Read first, then reversible writes, then external communication — in that order.
Configuration entirely through the Console.

Introduces: **Appointment**, **Event**, **Document** (email attachments are the
first real documents in the system).

### Phase 8 — Provider Workflows + Telephony (section 97)

Provider research, information gathering, phone calls, waiting, quote
collection. Then approval-gated booking. No phone-based payment authorization.

Introduces: **ServiceRequest**.

**The Electrician acceptance scenario (section 101) becomes runnable here.** Its
sixteen steps span Phases 3, 4, 7, and 8; this is the phase that closes it.

### Phase 9 — Browser + Shopping (section 98)

Authenticated browser worker with separate browser contexts, search and
research, cart building, substitutions, approval-gated checkout, verification.

Introduces: **ShoppingList**.

### Phase 10 — Bills + Financial Actions (section 99)

Bills first, payments last. Section 99 states the gate explicitly: before
enabling payment, the action outbox, approvals, idempotency, verification,
audit, emergency stop, and backup/restore must all be proven.

Introduces: **Bill**.

### Phase 11 — Hermes Self-Configuration (section 100)

Safe self-management of skills, preferences, routines, cron, and workflow
templates. Protected changes create Code Change Requests in `changes/requests/`
rather than being applied.

Introduces: **WorkflowTemplate**.

### Closing

Run both acceptance scenarios end to end: the Electrician scenario (section 101)
and the Shared-Agent scenario (section 102), which proves state belongs to
LifeOps by having Hermes and Claude Code read and write the same preferences and
tasks.

---

## 7. Entity type ownership

All eighteen canonical entity types from BUILD_SPEC section 36, each assigned to
the phase that owns it. `PHASE_FOR_ENTITY_TYPE` in code mirrors this table and
`tests/spec/test_spec_fidelity.py` asserts the two agree.

| Entity type | Phase | Status |
|---|---|---|
| Person | 0 | Built |
| Preference | 0 | Built |
| Task | 0 | Built |
| Memory | 2 | Built |
| Household | 3 | Built |
| Provider | 3 | Built |
| Asset | 3 | Built |
| WaitingItem | 4 | Planned |
| Action | 4 | Planned |
| Approval | 4 | Planned |
| Appointment | 7 | Planned |
| Event | 7 | Planned |
| Document | 7 | Planned |
| ServiceRequest | 8 | Planned |
| ShoppingList | 9 | Planned |
| Bill | 10 | Planned |
| WorkflowTemplate | 11 | Planned |
| Knowledge | — | **Unscheduled** |

**Knowledge** is the single type no phase names. Section 36 says "only add types
required by real workflows," and none currently does. It is recorded here as
deliberately unscheduled rather than forgotten; it gets a phase when a workflow
needs it.

Relationship vocabulary: all twenty types from section 39 are implemented as of
Phase 3 and pinned by the fidelity suite. Section 39's warning — *"do not
attempt to predefine every relationship in a human life"* — bounds inventing new
types; it is not licence to implement fewer.

---

## 8. Gaps carried forward

Recorded, not hidden. None blocks Phase 4.

- **The World screen shows only the current view.** Section 15 also lists a
  temporal/current toggle. Not built. Phase 4 is the natural home, since it is
  already temporal work.
- **World entity facts have no supersession chain.** Unlike preferences and
  memories, an entity's facts are current-only, so `get_entity_history` reports
  the memories referencing an entity and states that scope in a `covers` field
  rather than implying more.
- **No durable audit log.** Phase 4, section 62.
- **Hermes is not installed on this machine**, so the MCP plugin is tested
  against a stub rather than a live Hermes. See HERMES_INTEGRATION.md.
- **No provider adapters exist yet.** `test` and `discover` report honestly that
  they are not implemented rather than faking success.

---

## 9. Risks

**Token budget.** Eight phases is a long run and sessions have hit limits twice.
The contract-first commit is the main mitigation: a fresh session reads a
committed contract rather than reconstructing intent from a transcript. Phase
specs written just-in-time also avoid spending budget on documents that would be
rewritten.

**Deferred integration truth.** Six phases end at "built but disabled," so
reality only arrives at the user's enable-and-verify step. Fakes, Test buttons,
and schema-driven Console forms narrow the gap; they do not close it. Expect
real defects at each enablement and budget for them.

**Section 101 depends on a real phone call to a real provider.** It is the
riskiest acceptance in the spec, it cannot be rehearsed against a fake with full
fidelity, and it arrives late. Phase 8's spec should plan a rehearsal path
before the live attempt.

**Parallel fan-out remains the known failure mode.** Contract-first plus the
harness addresses the mechanism that failed in Phase 3, but fan-out is still
where drift originates. The adversarial review step is not optional.

---

## 10. Definition of done for the program

- Phases 4 through 11 each pass their own BUILD_SPEC acceptance criteria.
- The Electrician scenario (section 101) runs end to end, with the Console
  visualizing task progress, waiting state, provider relationship, approval,
  activity, and final verified completion.
- The Shared-Agent scenario (section 102) passes across Hermes and Claude Code.
- All eighteen section 36 entity types are either built or explicitly recorded
  as unscheduled.
- The enforcement harness is green, and has been extended with each phase's new
  enumerations.
