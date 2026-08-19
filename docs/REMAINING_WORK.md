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

### ~~Instacart site adapter~~ — done, plus Amazon (BUILD_SPEC section 98)

**Status: built and verified live, 2026-08-19**, on the deployment host
(`gh-ai`), which is not the sandbox the paragraphs below were written in.

The claimed blocker was wrong twice over. Chromium is not missing system
libraries here — it launches and loads live pages — and outbound network
works. Both retailers were driven end to end through `RealBrowserWorker`
against the real sites:

| | Amazon | Instacart |
|---|---|---|
| `search` | real, verified | real, verified |
| `build_cart` | real, verified (guest cart) | refuses: no guest cart |
| `confirm_cart` | real, verified across a browser restart | refuses |
| `submit_order` | refuses: unverified checkout | refuses |
| `confirm_order` | refuses: needs sign-in | refuses |

Adapters live in `core/lifeops/browser/sites/`, registered through the
`_SITE_ADAPTERS` extension point the module docstring always pointed at.
Every selector is recorded in its adapter's docstring with what it returned
on the day it was read, so a future break reads as "the site changed".

**What is deliberately still open: checkout.** Both `submit_order` methods
raise a specific error instead of clicking through a purchase. Amazon's needs
a signed-in session with an address and payment method; Instacart needs an
account before it will hold a cart at all. Writing those selectors from
documentation, next to an action that spends real money, is the speculative
build section 105 forbids — and the failure mode is not a red test but a
wrong order placed for real. Closing it means signing the per-store profile
in once (the profile under `profile_root/<store>` persists between calls,
which is what section 66's persistence is for) and verifying the flow against
a real basket.

Two things worth knowing operationally:

- **Locale follows the browser's apparent location.** From this datacenter
  host, amazon.com answers in EUR. Prices are passed through verbatim, symbol
  included, and never parsed into a number.
- **`tests/unit/test_site_adapters.py` carries opt-in live tests**
  (`LIFEOPS_LIVE_SITE_TESTS=1`). They are how the recorded selectors get
  re-verified when a site changes; they stay out of the default suite so a
  unit run never depends on the public internet.

### Local voice providers on real hardware

**Status:** code is real and tested against fakes. **Deferred by decision, not
blocked** — voice stays on ElevenLabs for now.

`LocalASRProvider` (faster-whisper) and `LocalTTSProvider` (Kokoro) in
`core/lifeops/voice/local.py` do real transcription and synthesis, with a real
load/unload lifecycle and an in-process weight cache. Neither package is
installed by default: both sit behind `pyproject.toml`'s `voice-local` extra,
with the AGENTS.md dependency justification written out, because it is a
GPU-class footprint most deployments never touch.

The earlier claim here — "this sandbox has no GPU" — was wrong about this
deployment. There is a GPU host on the LAN: **`gh-nvidia` at
`192.168.0.212`**, running Ollama 0.32.9 with qwen3 (1.7b–14b), a qwen2.5vl
vision model, and `mxbai-embed-large`.

It does not unblock these two providers, and the reason is architectural
rather than a missing machine. **Ollama serves LLMs and embeddings; it serves
no ASR or TTS endpoint.** faster-whisper and Kokoro are in-process Python
libraries that load weights into the calling process, and LifeOps Core runs on
`gh-coder`. There is nothing on `gh-nvidia` for them to call.

Three real routes, should this be picked up later:

1. **Run LifeOps Core on `gh-nvidia`.** The providers work exactly as written;
   no code changes at all.
2. **Stand up a remote ASR/TTS service there** (a whisper.cpp server, a Kokoro
   HTTP wrapper) and add remote adapters beside the local ones. This is the
   shape BUILD_SPEC section 28's provider abstraction exists for — the point
   of not hardwiring Hermes to one backend.
3. **Stay on ElevenLabs.** Already built, already tested, ships disabled
   pending a key.

**Decision (2026-08-19): route 3 for now.** Nothing here is broken or
half-built; the local path is complete code waiting on a deployment choice
that has been made the other way for the moment.


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

BUILD_SPEC section 32's own diagram places the Voice Bridge between raw audio
and "the same Hermes runtime" — not LifeOps Core. Combined with CLAUDE.md
rule 4 (do not build a second agent runtime), duplex-audio orchestration
belongs in Hermes.

**Finding, 2026-08-19: Hermes already ships most of it, and it works here.**
This was checked on the deployment host rather than assumed. `~/.hermes/config.yaml`
carries a configured `tts:` block (provider `elevenlabs`), an `stt:` block
(enabled, provider `local`, whisper `base`), and a `voice:` block with
push-to-talk (`record_key: ctrl+b`), silence detection, and `auto_tts`.
`faster_whisper` 1.2.1 is installed in Hermes's own venv and
`ELEVENLABS_API_KEY` is present.

A full round trip was run end to end: text → ElevenLabs synthesis → MP3 →
faster-whisper transcription → text, and the words came back. So "no duplex
audio streaming code anywhere, not even scaffolding" is no longer the right
description of the situation. The path exists; what is missing against
sections 31-33 specifically is narrower than "the Bridge":

- **Duplex/barge-in.** What Hermes has is push-to-talk with silence
  detection, not full duplex — you cannot interrupt it mid-sentence. That is
  section 32's remaining gap, and it is a Hermes-side change.
- **Latency instrumentation (section 33).** Still absent, and now clearly
  worth having: the round trip above measured **2.6s to transcribe a ~1.5s
  clip** on this host's CPU, roughly 1.7× real time. That is not
  conversational latency, and it is the strongest argument yet for section
  31's GPU routing.
- **GPU routing (section 31).** `gh-nvidia-1` is reachable on the tailnet
  (`100.96.94.19`). It serves Ollama only — no ASR/TTS endpoint — so it does
  not help until something is stood up there. Route 2 from section 1 above (a
  whisper.cpp or Kokoro HTTP service on that host, plus remote adapters beside
  the local ones) is what the measurement argues for.

**What unblocks the rest:** a decision to modify Hermes's own voice loop for
duplex, and/or standing up an ASR service on `gh-nvidia-1`. Nothing in *this*
repository blocks either — LifeOps Core's job, the swappable ASR/TTS provider
layer, is built, and ElevenLabs is now live-configured and healthy here.

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

### ~~Hermes itself is not attached to this machine~~ — done

Attached 2026-08-19 on `gh-ai`. Hermes connects over stdio MCP as
`hermes-personal` and discovers all 52 tools (`hermes mcp test lifeops`). The
entry lives in `~/.hermes/config.yaml` under `mcp_servers.lifeops`.

The memory-provider plugin is a separate switch and is **not** flipped:
`memory.provider` is still Hermes's built-in. Note its default `base_url` is
`127.0.0.1:8080`, which is not where Core listens on this host.

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

## 5. The 2026-08-18 full-audit backlog

A complete code review and audit
([docs/audits/2026-08-18-full-codebase-audit.md](audits/2026-08-18-full-codebase-audit.md))
swept the whole repository. Its eight P0 findings were **fixed the same
day**, and its P1 and P2 backlogs were **fixed the day after** — the
disposition notes at the top of that document record all three passes item
by item. What remains open:

- **One qualified P2 remnant:** `nornicdb.sh` still passes the admin
  password as a flag by default (visible in `/proc/*/cmdline`), because
  upstream's docs never name the admin-password env var and this sandbox
  cannot run the binary to verify. The script already exports
  `NORNICDB_ADMIN_PASSWORD` alongside it — verify one start on a real
  deployment with `LIFEOPS_NORNIC_PASSWORD_VIA_ENV=1`, then make that the
  default and mirror it in the systemd unit.
- ~~DATA_MODEL.md's two missing phases of schema and stale storage
  narratives.~~ **Done:** bills/payees, workflow templates, and shopping
  items are documented, the shopping and service-request storage narratives
  now describe the dedicated repositories rather than the abandoned
  facts-bag blobs, and the constraint list is complete.
- **Docs corrections still outstanding:**
  HERMES_INTEGRATION.md's stale permission table; ARCHITECTURE.md's
  incomplete capability table; TESTING.md's suite table and stale
  `test-fast` description; OPERATIONS.md's wrong emergency-stop route;
  CONFIGURATION.md's stale fresh-deployment states.
- **One deliberate policy decision, parked in SECURITY.md:** phone-call
  destinations are model-influenced (a provider `phone` fact Hermes can
  write) while calls stay R2 per BUILD_SPEC section 101 — decide between
  accepting, reclassifying, or a number allowlist *before* enabling real
  telephony credentials.
- ~~**Live-NornicDB verification** of the lease claim and approval consume.~~
  **Done — and it found a real bug.** `tests/persistence/test_concurrency.py`
  races twelve callers at each. NornicDB isolates them correctly, but the
  loser arrived as a `TransientError` wrapped into `RepositoryError`, so
  `claim()` raised where it documents returning `None`; the due-work worker
  would have logged "another worker got it" as a database failure, and a
  second concurrent commit would have surfaced a retryable-looking fault next
  to a payment. `ConcurrentWriteError` now carries that case and the four
  conditional writes that elect a single winner treat it as their documented
  `None`.
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
