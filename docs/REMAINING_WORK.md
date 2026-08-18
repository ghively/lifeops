# Remaining work

A single, current accounting of everything not yet done in this repository,
as of 2026-08-18. Written after a full pass ("finish all the repo work")
closed every BUILD_SPEC gap that was actually buildable here — what's left
falls into four different kinds, and the kind matters for what "done" would
even mean:

1. **Blocked by this environment**, not by missing code.
2. **Deferred by BUILD_SPEC itself**, explicitly, not an oversight.
3. **Out of this repository's scope by design** — belongs in Hermes, not
   LifeOps Core.
4. **Waiting on the user** — a real credential, a real machine, or a real
   decision only they can make.

Nothing below is hidden or downplayed elsewhere: this list is a distillation
of [CLAUDE.md](../CLAUDE.md)'s "Known gaps" section and
[docs/audits/2026-08-18-unimplemented-features.md](audits/2026-08-18-unimplemented-features.md)'s
changelog, both of which carry the fuller reasoning and code pointers behind
each item. When those documents and this one drift, they win — this is a
snapshot, not a new source of truth.

---

## 1. Blocked by this environment

### Instacart site adapter (BUILD_SPEC section 98)

**Status:** scoped and approved, not built.

The user chose the architecture (one reviewed, deterministic Playwright
adapter registered in `browser/real.py`'s `_SITE_ADAPTERS`, driven generically
by `hermes/skills/lifeops/shopping-manager/SKILL.md`) specifically to avoid
letting an LLM browse and check out live against raw, untrusted page content —
that shape carries a real prompt-injection risk next to a payment-capable
action loop. Instacart was named as the retailer.

Building it hit a hard wall before any Instacart-specific code was written:
**this sandbox's Chromium cannot reach any live website through the network
proxy at all.** Confirmed directly — `net::ERR_CONNECTION_RESET` against
`instacart.com`, `google.com`, and plain `example.com` alike, across several
proxy configurations, while `curl` to the same hosts works fine. There is no
way to render Instacart's real DOM, inspect its login/search/cart flow, or
verify any automation logic in this environment.

Writing selectors without ever seeing the real page would be exactly the
"scraping logic never tested against a live site" anti-pattern
`browser/real.py`'s own module docstring warns against, and BUILD_SPEC
section 105 forbids speculative builds like it. Per the user's direction,
this is recorded as an environment-blocked gap rather than shipped as
fabricated code.

**What unblocks it:** running this work somewhere with live outbound browser
network access (a real Chromium that can reach `instacart.com`). No code or
design work is needed first — `BrowserWorker`, `_SITE_ADAPTERS`, and the
shopping domain/MCP layer are all already built and waiting for exactly this
one adapter to register itself.

### Local voice providers on real hardware

**Status:** code is real and tested against fakes; never run against real
models or a GPU.

`LocalASRProvider` (faster-whisper) and `LocalTTSProvider` (Kokoro) in
`core/lifeops/voice/local.py` do real transcription/synthesis work, with a
real Load/Unload lifecycle and an in-process weight cache — but neither
package is installed by default (both live behind `pyproject.toml`'s
`voice-local` extra, a deliberate choice per AGENTS.md's dependency
justification, since it's a GPU-class footprint most deployments never
touch). This sandbox has no GPU and neither package installed, so
`health()` correctly reports "not installed" here. `tests/unit/test_voice.py`
covers the installed code paths only against `sys.modules`-injected fakes.

**What unblocks it:** installing the `voice-local` extra on a machine with a
GPU (or CPU inference, slower but functional) and exercising `health()` /a
real transcribe-then-synthesize round trip.

---

## 2. Deferred by BUILD_SPEC itself

These aren't gaps the audit found — the spec's own text puts them in a
later tier. Building them now would be jumping ahead of the phase BUILD_SPEC
defines, not closing a hole in it.

### Six "Later"-tier Hermes skills (BUILD_SPEC section 75)

The spec splits skills into "Initial" (built — see below) and "Later":

- `grocery-manager`
- `bill-manager`
- `household-maintenance`
- `vehicle-maintenance`
- `phone-call-manager`
- `school-admin`

All nine Initial-tier skills exist under `hermes/skills/lifeops/`:
`personal-core`, `waiting-for-manager`, `daily-brief`, `weekly-review`,
`provider-manager`, `appointment-manager`, `calendar-manager`,
`email-triage`, and `shopping-manager` (built ahead of its formal "Later"
listing above, at the user's explicit request, alongside the browser
architecture decision — it isn't literally named in section 75's Initial
list but fills the same role `grocery-manager` would).

**What unblocks it:** the user asking for any specific one. Each would
follow the identical pattern (Hermes Agent frontmatter + BUILD_SPEC section
76's ten mandatory headings) already established by the nine that exist.

### Extra local TTS candidates (BUILD_SPEC section 30)

Section 30 names four TTS candidates and says "do not make implementation
completion depend on selecting the final winner." Kokoro (the
fallback/reference candidate) has a real adapter now; Qwen3-TTS 1.7B/0.6B
and Chatterbox Turbo do not. The user has said they want to try all the
candidates eventually — Kokoro was first, not exclusive.

**What unblocks it:** the user asking to add a specific one. The
`VoiceProvider` Protocol (`voice/provider.py`) is the extension point — each
new adapter is additive, the same shape `LocalTTSProvider` already proves.

---

## 3. Out of this repository's scope by design

### The Voice Bridge (BUILD_SPEC sections 31, 32, 33, 103)

BUILD_SPEC section 32's own diagram places the Voice Bridge between raw
audio and "the same Hermes runtime" — not LifeOps Core. Combined with this
repo's standing rule against building a second agent or agent runtime
(CLAUDE.md rule 4), duplex-audio orchestration (streaming ASR, partial
transcripts, endpointing, barge-in, phrase-chunked TTS) belongs in Hermes
itself. This was raised with the user as a design check-in rather than built
unilaterally in the wrong place, and confirmed.

What *is* LifeOps Core's job — the swappable ASR/TTS provider layer the
Bridge would call into — is built (see section 1 above: real, just not run
on real hardware yet).

Three more items are downstream of the Bridge and have no code because the
thing that would drive them doesn't exist yet:

- **RTX 3060 resource-priority scheduling** (section 31) — a scheduling
  policy for a runtime (the Bridge) that isn't there to schedule.
- **Voice latency instrumentation** (section 33) — p50/p95/p99 measurements
  of a request path (mic → Bridge → Hermes → TTS → audio) most of which
  isn't wired.
- **The voice acceptance scenario's Console walkthrough** (section 103) —
  its steps (start a voice session, ask a question, add a task by voice)
  need a live Voice Bridge session to walk through; section 104's provider-
  configuration scenario, which doesn't, already passes
  (`test_phase0_exit.py`).

**What unblocks it:** this is a Hermes-side build, not a LifeOps Core one.
Nothing here changes until that work happens in Hermes's own codebase.

### Payment provider adapter

**Status:** deliberately absent — not a stub, not forgotten.

No payment-provider adapter exists anywhere in this codebase. CLAUDE.md's
rule is explicit: "Money moves only where a human is present." `commit_payment`
has no MCP tool by design, and `FINANCIAL_PAYMENT` is granted to the Console
only — Hermes can read what's owed and say a bill is due, but holds no path
from a model's reasoning to an actual payment. This is stricter than
BUILD_SPEC strictly requires (sections 56/57 would permit granting Hermes the
capability and relying on the Console-only approval gate to stop the money);
the reasoning for going stricter is recorded in
`tests/spec/test_spec_fidelity.py`'s `CONSOLE_ONLY_BY_JUDGEMENT`, specifically
so it can be reversed deliberately if the user ever wants to.

**What unblocks it:** an explicit user decision to add one, plus a real
payment provider's credentials (which, per CLAUDE.md rule 3, this repository
will never prompt for — it would build the adapter, the Console form, and
the Test button, and leave the provider disabled until supplied).

---

## 4. Waiting on the user

### Hermes itself is not attached to this machine

LifeOps Core, the MCP server, and every tool/resource/capability Hermes would
use are built and pass the Phase 0 exit test over a real MCP subprocess with
the exact client identity Hermes uses (`hermes-personal`). What hasn't
happened is Hermes — the user's own assistant, a separate install — actually
connecting here. See [HERMES_INTEGRATION.md](../HERMES_INTEGRATION.md) for
the (already-written) steps to do that; nothing in this repository blocks it.

### Every disabled provider needing real credentials

Calendar (CalDAV), email (IMAP/SMTP), and telephony (Twilio) each have a
real, protocol-correct adapter, disabled per BUILD_SPEC section 88 until
credentials exist. This is the intended steady state for a fresh checkout
(BUILD_SPEC section 104's acceptance scenario asserts exactly this — "Not
configured" / "Disabled" across the board), not something to "finish": the
Console's Configuration screen, the Test button, and the secret store are
all already built for each. Supplying real credentials is a user action,
never something this repository should prompt for on its own (CLAUDE.md
rule 3).

---

## 5. The 2026-08-18 full-audit backlog (P1/P2)

A complete code review and audit
([docs/audits/2026-08-18-full-codebase-audit.md](audits/2026-08-18-full-codebase-audit.md))
swept the whole repository. Its eight P0 findings — the approval-race and
resurrection bugs, the broken exit-test pin, the CI gaps, the identity
defaulting, the unverified email TLS — were **fixed the same day** (see the
disposition note at the top of that document). What remains open, by
explicit decision, is its P1 and P2 backlog and the documentation
corrections, all recorded there in full. The headline items a future
session should start from:

- **Before enabling providers:** the CalDAV adapter's TZID/all-day/recurrence
  handling and DESCRIPTION erasure; the email adapter's `confirm_sent`,
  SEARCH escaping/body matching, error wrapping, and port-465 gap; the
  Twilio connection-pool leak; the faster-whisper `cuda:0` device shape;
  the model-influenced telephony destination (needs an allowlist or an
  approval gate before real credentials).
- **Core hardening:** status guards on `record_result` and `settle_bill`;
  prepare-before-validate in `_prepare_provider_contact`; the config
  service's unlocked cross-process read-modify-write; the waiting-lease
  claim's atomicity (needs a live concurrent test against NornicDB).
- **Surface parity:** `entity_ids`/`related_entity_ids` missing from the MCP
  `remember`/task tools; shopping read-back over MCP; assorted filter and
  error-code parity holes.
- **Console:** the CalendarPage `datetime-local` handling; the Approvals
  screen's silent 50-item cap; the stale phase-gated sidebar; the
  MemoryPage search filter drop; the wrong `config_changed` query keys.
- **Docs:** MCP_API.md's tool/resource counts, DATA_MODEL.md's two missing
  phases of schema, HERMES_INTEGRATION.md's stale permission table,
  TESTING.md's suite table, OPERATIONS.md's wrong emergency-stop route.
- **Operational, outside the repo:** the GitHub Actions runner/billing
  failure — no CI run has ever executed; until that is fixed at the account
  level, `make check` is the only real gate.

---

## What is *not* on this list

Everything else BUILD_SPEC describes — the eleven phases, the MCP surface,
Console screens, memory/world/task/action machinery, universal search,
chaos-test coverage, self-configuration, per-fact entity history — is built,
tested, and passing as of this snapshot. See CLAUDE.md's "Where things
stand" and "Known gaps" sections for the full, current picture, and the two
audit documents under `docs/audits/` for the session-by-session record of
what closed and when.
