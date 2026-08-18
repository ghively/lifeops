# Full codebase audit — 2026-08-18

A complete sweep of the repository: LifeOps Core (`core/lifeops/`, ~26k lines),
the Console (`console/src/`, 77 files), the test suites (~1,200 tests), shell
scripts, deploy units, CI, the Hermes skills, and every documentation file —
each reviewed against the code, and the code against BUILD_SPEC's and
CLAUDE.md's own invariants.

**Method.** Eight independent review passes (core service and domain;
repositories and Cypher; security boundaries; provider adapters; HTTP/MCP
adapter parity; Console; tests and tooling; documentation truthfulness), each
required to quote code evidence for every claim, followed by a verification
pass that re-checked the highest-severity findings directly against the code
and — for the two most consequential — reproduced them (the MCP tool-set
mismatch was reproduced in-process; the CI state was confirmed against the
live GitHub Actions API). Findings whose confirmation depends on an
environment this sandbox lacks (live NornicDB concurrency, a GPU) are marked.

**Where things stand overall.** The architecture holds. Every automated gate
passes locally: ruff clean, mypy clean over 100 files, 999 Python tests green,
202 Console tests green, production build green. The security model was
checked systematically and held: no MCP path exists to approvals, execution,
or payments; client identity is bound per connection; the approval hash is
canonical and re-checked at commit; approvals are single-use (sequentially);
the secret store's cryptography is sound (fresh nonces, AAD-bound names,
0600/O_EXCL, atomic writes, crash-safe rotation); secrets never reach
NornicDB, logs, or HTTP responses; there are no injection sinks, no XSS sinks
in the Console, and no Cypher outside `repositories/nornic/`; none of
CLAUDE.md's five NornicDB quirks is violated anywhere. What follows is what
needs fixing anyway — ordered by how much it matters.

---

## P0 — fix first

### 1. The Phase 0 exit gate currently fails: the exact-tool-set pin was never updated for the self-configuration tools

`tests/e2e/test_phase0_exit.py` (`test_exactly_the_sanctioned_tools`) asserts
the Hermes tool set is **exactly 45 names**. The server registers **50** —
`save_workflow_template`, `list_workflow_templates`, `due_routines`,
`delete_workflow_template`, and `propose_self_change` were added to
`mcp/server.py` after the pin's last update. Reproduced in-process:
`build_server(..., HERMES).list_tools()` returns 50 tools; the diff is exactly
those five. The suite passes in this sandbox only because e2e needs a live
NornicDB and skips. Every "all Phase 0 exit criteria still pass" claim
(README, CLAUDE.md, TESTING.md) is therefore currently untrue — the review
gate did its job and nobody ran it.
**Fix:** add the five tools to the pinned set (they are sanctioned — sections
73-76) and run `make test-e2e` against a live NornicDB to re-verify the rest.

### 2. CI has never been green — and its workflow is missing two suites even when it runs

The repository's two CI runs to date **both failed within ~5 seconds** with no
runner ever starting (confirmed via the Actions API; logs unavailable —
consistent with an Actions billing/runner-availability problem, not a test
failure). So no CI run has ever executed a single test. Independently, the
workflow itself has gaps:

- `.github/workflows/ci.yml:66` runs `pytest tests/unit tests/policy
  tests/spec tests/integration -q` — **`tests/chaos` is absent**, though
  `make test-fast` includes it. A regression in the section-86 guarantees
  (stranded actions, retry budget, duplicate requests) would merge green.
- `LIFEOPS_NORNIC_RESTART_CMD` is never set in CI's env, so the three
  restart-durability tests (Phase 0 exit criterion D) skip on every CI run
  (`test_phase0_exit.py:465-467, 497-499`).
- The Console job runs `tsc`, `vitest`, and `build` but never `npm run lint`,
  although ESLint is configured with `--max-warnings 0` (react-hooks rules —
  real bug detection, not style). `make lint` is Python-only too.
- `make check`'s comment says "Everything CI runs" — untrue in both
  directions (CI adds secret-file and prohibited-datastore assertions that
  `make check` lacks; `make check` runs chaos, which CI lacks).

**Fix:** repair the Actions runner/billing situation, add `tests/chaos` to
the CI test list, set a Docker-based restart command for the e2e job, add
`npm run lint` to both `make check` and CI, and align the two gates.

### 3. Approval consumption is not atomic — one approval can authorise two executions

`core.py:947-978` (`begin_commit`): read approval → `authorises()` → consume,
as three separate awaits, and `NornicApprovalRepository.update` is a blind
last-write-wins `SET` with no `WHERE ap.consumed_at IS NULL` guard. The HTTP
server and MCP server are **separate processes** over one NornicDB, so two
concurrent `execute_action` calls (double-click, retry after a timeout,
Console + Hermes racing) can both see the approval unconsumed, both consume,
and both perform the external call. The docstring's fallback — "a provider
honouring the idempotency key" — does not exist: **no wired executor
transmits `action.idempotency_key` to any provider** (`execute_booking`,
`execute_checkout`, `_execute_send_email` — verified). No test exercises
concurrent commit (all replay tests are sequential); contrast the waiting-item
lease, which got both an atomic conditional write and a race test.
**Fix:** make consumption a compare-and-set (`SET ... WHERE ap.consumed_at IS
NULL`, returning a row only on success) in both the Nornic repository and the
fake, and add a concurrent-commit test. Passing the idempotency key to
providers that accept one is a worthwhile second layer.

### 4. A declined action can be resurrected and executed via a stale duplicate approval

Two defects compose (`core.py:902-945`, `980-1023`):

- `update_payload` creates a fresh approval for the revised payload but never
  expires/declines the previous PENDING one — both now render as decidable
  cards (`list_pending` filters on status alone).
- `decide` applies the decision to the action **unconditionally** — no check
  that the approval's `payload_hash` matches the action's current payload,
  and no precondition on the action's status.

Sequence: substitution → approval B issued, approval A still pending → human
declines stale card A → action CANCELLED → human (or another tab) approves
card B → `decide` sets the CANCELLED action back to APPROVED → `begin_commit`
fetches the newest approval (B), hash matches, `authorises()` passes → the
order executes despite an explicit recorded decline.
**Fix:** in `update_payload`, supersede (expire) any live approval for the
action when issuing the new one; in `decide`, refuse to move an action that is
not `NEEDS_APPROVAL`/live, and ignore approvals whose hash no longer matches.

### 5. Telephony executor does bookkeeping after the call is placed — a placed call can be recorded as FAILED and the call SID lost

`core.py:2935-2962` (`_execute_phone_call`): `dial()` happens first, then
`_apply_call_result` writes quotes/waiting items — inside `execute_action`'s
try. If that bookkeeping raises (e.g. the service request was cancelled
meanwhile, making its state machine refuse the update), the except path
records `succeeded=False` with **no external_reference**: the outbox says a
call that happened didn't, the Twilio SID is discarded, and the natural retry
dials the provider again (PLACE_PHONE_CALL requires no approval). Every other
executor performs the external effect last.
**Fix:** record the action result (success + SID) immediately after `dial()`
returns, then apply service-request bookkeeping outside the failure path (its
own failure should mark the request degraded, not falsify the outbox).

### 6. Engaging safe mode mid-execution strands an in-flight action in EXECUTING forever

`record_action_result` (`core.py:2789-2806`) re-runs the capability check for
the action type; all executable types are in `SAFE_MODE_BLOCKED`, and
`safe_mode` is re-read live on every check. Flip the emergency stop while an
email/booking is in flight and the *bookkeeping write for an effect that
already happened* raises `SafeModeError`: the action is stuck EXECUTING (not
re-committable — `may_execute` refuses EXECUTING), its approval is consumed,
and no HTTP/MCP surface can record the result later. This is the exact strand
the chaos suite's retry work exists to prevent, reintroduced via policy.
**Fix:** exempt result-recording from the safe-mode gate (record with
`safe_mode=False` semantics, as the config routes already do) — safe mode
should stop new effects, not the truthful recording of finished ones.

### 7. MCP with no client identity silently defaults to `interactive-mcp` — SECURITY.md says the opposite

`policy/capabilities.py:279-280`: `resolve_client` returns the default
identity for an **empty/missing** id before the `UnknownClientPolicy.DENY`
branch is consulted; `mcp/server.py` defaults `--client` to an env var that
may be unset. Launching the MCP server with neither flag nor env yields a
working server holding `write_preference`/`create_task`/`update_task`/
`read_memory` — while SECURITY.md ("Over MCP a missing identity is refused,
never defaulted") documents a refusal that does not exist. Related on the HTTP
side: an *unrecognised* `X-LifeOps-Client` is silently downgraded to the
default identity (`api/http.py:168-179`), where the MCP side treats the same
typo as fatal by explicit design ("a typo in a launch config should be
visible").
**Fix:** make a missing id under `DENY` policy also refuse (MCP), and use
`DENY` for non-empty unknown ids on HTTP; keep the headerless→CONSOLE default
only as the documented loopback-Console convention it is.

### 8. IMAP and SMTP send credentials over TLS with certificate verification disabled

`email/imap_smtp.py:105-108, 180-182, 218-220`: `imaplib.IMAP4_SSL(...)` and
`smtp.starttls()` are called with no `ssl_context`. The stdlib default for
these modules (unlike HTTP) is an **unverified** context — confirmed on this
interpreter (`ssl._create_stdlib_context is ssl._create_unverified_context`).
Any on-path attacker with a self-signed cert receives the mailbox password.
The adapter is disabled until credentials exist, so nothing is exposed today —
fix before the email provider is ever enabled.
**Fix:** pass `ssl.create_default_context()` to `IMAP4_SSL(ssl_context=...)`
and `starttls(context=...)` (and see P1 for the SMTP-465 gap).

---

## P1 — significant defects to schedule

### Core / approval flow

- **`record_result` has no status guard** (`core.py:1025-1040`): sets
  EXECUTED/FAILED on any action regardless of state — the raw assignment the
  project's state-machine discipline forbids. Internal-only today (no
  HTTP/MCP route), but load-bearing in P0-4's aftermath. Add an
  EXECUTING-only precondition.
- **`_prepare_provider_contact` prepares the dialable action before
  validating the service-request transition** (`core.py:3266-3302`): on
  refusal, an orphan live PLACE_PHONE_CALL action remains executable with the
  request unaware of it. Validate the transition first (or prepare after
  `record_contact`).
- **`settle_bill` has no bill-status guard** (`core.py:3940-3965`): a PAID,
  CANCELLED, or DISPUTED bill can be re-marked PAID, silently overwriting
  `paid_at`/`external_reference` evidence. Apply `may_pay`-style gating.
- **`decide_approval`'s post-decision work can fail after the decision
  persisted** (`core.py:2716-2731`): the `action is not None` guards are dead
  (`ActionService.get` raises), so a missing action — or a declined grocery
  order in a deployment with no browser provider (`self._shopping()` raises
  `ConfigurationError`) — surfaces as an error *after* the decision landed.
  Use the nullable repository get, and guard the shopping revert.
- **`prepare`'s idempotency dedup is check-then-create** (`core.py:861-889`).
  The DB uniqueness constraint (`client.py:53-54`) backstops production —
  a concurrent duplicate errors rather than double-preparing — but the caller
  gets a raw `RepositoryError` instead of the existing action, and the fake
  repository enforces no uniqueness, so fake-backed tests can't see any of
  this. Catch the constraint violation and return the existing action;
  enforce uniqueness in the fake.

### Concurrency and processes

- **`ConfigurationService` does unlocked cross-process read-modify-write of
  the whole config document** (`config/service.py:121-166, 273-313, 328-342`).
  The HTTP and MCP processes share the file; a `record_health` racing an
  `update_provider` (or the safe-mode flag, which lives in the same document)
  silently reverts one side's write. Add file locking (`fcntl.flock`) or a
  per-key merge on save.
- **Waiting-item lease `claim()` may not be the atomic compare-and-set its
  comment claims** (`repositories/nornic/waiting.py:191-211`). Under standard
  Neo4j read-committed semantics the WHERE clause is evaluated before the
  write lock, so two concurrent claimants can both win. NornicDB's actual
  isolation could not be exercised here (persistence tests cover only
  sequential claims) — verify with a live concurrent test, and rewrite as
  write-then-verify in one transaction if it fails. Also: `claim()` returns
  `await self.get(...)` immediately after its own auto-commit write with no
  fallback, the exact stale-read pattern CLAUDE.md warns about (same shape,
  lower stakes, in `preferences.invalidate` and `memory.invalidate`).

### Calendar adapter (fix before enabling CalDAV)

- **Timestamp parsing mishandles TZID, floating-time, and all-day values**
  (`caldav.py:47-62, 284-296`): only `...Z` and bare-date forms parse;
  a `DTSTART;TZID=...` event (the normal form from Google/Apple/Nextcloud
  clients) is returned as a raw compact stamp — poisoning `start_at`
  ordering/free-busy string comparisons — and `update_event` re-parses that
  raw stamp as a *naive* datetime interpreted in the server's local timezone,
  silently shifting the event. All-day `VALUE=DATE` values become UTC
  midnight (the previous evening west of UTC).
- **`update_event` erases DESCRIPTION on every update** (`caldav.py:295`
  `notes=notes or ""`, and the parser never reads DESCRIPTION back).
- **Recurrence is ignored** (first VEVENT only, master DTSTART) — a weekly
  event queried next week reports its first-ever occurrence, so free/busy can
  report a genuinely-busy slot as free and double-book it. **XML entities are
  never unescaped** (`Tom &amp; Jerry` reads back wrong).
- **Fake drift:** the fake's holds occupy nothing and ignore
  `hold_reference`, while the real adapter PUTs a VEVENT and upgrades
  hold→event by UID; the fake raises `NotFoundError` where the real raises
  `ProviderError`. Tests of hold semantics are asserting behavior production
  doesn't have.

### Email adapter (fix before enabling IMAP/SMTP)

- **`confirm_sent` cannot work**: nothing APPENDs sent mail to a Sent folder,
  `"Sent Items"` is sent unquoted (a two-token protocol error), and Gmail's
  `[Gmail]/Sent Mail` isn't probed — so every genuinely-sent email records
  false "not found in the Sent folder" verification evidence
  (`imap_smtp.py:166-206`, consumed at `core.py:3034-3040`). The fake returns
  True for everything, hiding it.
- **SEARCH criteria built by unescaped f-string** (`imap_smtp.py:114, 140,
  201`): quotes break the grammar, any non-ASCII query raises
  `UnicodeEncodeError`, and crafted input can smuggle extra SEARCH keys.
- **Search omits body matching** though the module docstring promises it and
  the fake implements it (`(OR SUBJECT FROM)`, no `TEXT`/`BODY` key).
- **Raw `imaplib.IMAP4.error`/`OSError` escape unwrapped** from
  search/read/confirm paths (bad password = unhandled 500), unlike every
  sibling adapter's deliberate `ProviderError` wrapping.
- **Port 465 (implicit TLS) cannot work** with `smtplib.SMTP`+`starttls()`;
  the registry permits it. Branch to `SMTP_SSL` or reject the port.
- Unknown MIME charsets raise uncaught `LookupError`, killing a whole search
  for one malformed message; `received_at` is the raw RFC 2822 Date header,
  which the fake sorts lexicographically.

### Other adapters

- **Twilio's `httpx.AsyncClient` is never closed** (`telephony/service.py:
  72-87`): every dial/status/health leaks a connection pool. Calendar and
  voice services fixed this exact bug (`_with_provider`/`_close_provider`);
  telephony missed it. (Voice's `transcribe_stream` also skips
  `_close_provider` — harmless today, a leak for future ASR adapters.)
- **Local ASR passes `device="cuda:0"` straight to faster-whisper**
  (`voice/local.py:182`), which accepts only `cpu|cuda|auto` plus a separate
  `device_index` — the registry's default GPU options can never load. The
  sibling TTS provider already normalizes the same shape
  (`_kokoro_device`). Unverified on hardware (no GPU here), but the API
  contract and the internal inconsistency both say it's wrong.
- **Telephony destinations are model-influenced with no human gate**:
  `place_phone_call`/`request_quote` are R2 (no approval), and the number is
  resolved from the provider entity's `phone` fact — which Hermes can write
  via `record_provider`. Dormant while telephony is disabled; before enabling
  credentials, either reclassify as R3 or gate on a payee-style approved
  number list.

### HTTP/MCP surface

- **Agent memories and tasks cannot link to world entities over MCP**: the
  `remember` tool drops `entity_ids`/`source_id` and `create_task`/
  `update_task` drop `related_entity_ids`, all present in the HTTP schemas.
  Hermes records a provider, then cannot bind a task or memory to it — the
  entity-centric aggregation the graph exists for is Console-only, which no
  doc states. Add the parameters.
- **Shopping has full write surface over MCP but no read-back** (no
  get/list-shopping-list tools; the capability is held; no recorded
  rationale, unlike documents). A next-session Hermes must guess or duplicate
  lists. Add read tools or record the rationale.
- **`_approval_out` swallows a missing action into an empty payload**
  (`http.py:247-265`) — the Approval screen can render a decidable card whose
  "what will happen" section is empty, with no error flag.
- Filter/shape parity holes: HTTP `/appointments` lacks the `status` filter
  core supports; MCP `list_bills` lacks `statuses`; MCP `search_memory` lacks
  type filtering; `total` means "all tasks" on HTTP but "this page" on MCP;
  MCP `create_calendar_hold` drops `hold_minutes`; MCP `save_preference`
  drops `importance`; MCP `list_appointments` reports a bad status value as
  `not_found` instead of `validation_error` (untyped arg); HTTP `create_task`
  accepts a client-supplied `source` string that can impersonate
  `"mcp:hermes-personal"` display provenance (real provenance is
  `created_by_client`; stamp or document it).
- `GET /config/clients` (`http.py:2177-2180`) is the only `/config` route
  with no client dependency — harmless data, but add the guard for
  consistency.
- `events.py:47-66`: the WS loop's broad `except RuntimeError` treats any
  runtime bug as a normal disconnect; `?token=` puts the bearer token in
  access logs (browser constraint — consider a one-time ticket).

### Console

- **CalendarPage hold form is broken in real browsers**
  (`CalendarPage.tsx:250-263`): `onChange` does
  `new Date(v).toISOString()` fed back as the controlled `datetime-local`
  value — clearing/partial edits throw `RangeError` leaving stale hidden
  state (submitting the *previous* time = holding the wrong slot), and a
  complete entry blanks the visible field. `RoutinesPage` already has the
  correct round-trip helper; use it. The test masks the bug by asserting only
  `subject`.
- **The Approvals screen silently caps at 50** (`ApprovalsPage.tsx:130`) with
  no pagination or "N of M" — a pending approval past the 50th is invisible
  on the one surface where invisibility matters. Same pattern on Tasks/Today/
  Bills (limit 200) and Search (10/category); the server's `total`/`offset`
  are never surfaced.
- **Sidebar still phase-gates live screens** (`LifeOpsSidebar.tsx:62-82,
  132-171`): Calendar, World, Knowledge, Files, Hermes render dimmed with
  "arrives in phase N" tooltips and the footer says "Phase 1", though all
  eleven phases shipped. Users will conclude working screens don't exist.
- **VoiceModeCard shows a rejected mode as active** (`ConfigurationPage.tsx:
  642-676`): `save.variables` persists after `onError` and no error renders.
- **MemoryPage search drops the active view's filters** (`MemoryPage.tsx:
  614-645`): searching in the Invalidated view returns current-only,
  all-type results under the still-active chip (backend `/memory/search`
  also lacks a type filter — needs both ends).
- **`config_changed` events invalidate the wrong query keys**
  (`useLifeOpsEvents.ts:55-59`): `['lifeops','system-config']` matches
  nothing; the real keys (`['lifeops','system']`,
  `['lifeops','voice','mode-status']`) never refresh, so safe-mode/voice-mode
  changes from other surfaces never appear.
- WorldPage: expansion clicks are silently dropped while another expansion is
  in flight; search is client-side over the 500-node cap so uncapped
  entities are unfindable (the server `query` param the client already types
  is never used); the History tooltip falsely claims non-preference entities
  have no history. HermesPage renders "No skills instantiated yet" — nine
  exist. BillsPage's "Payment prepared" banner never clears. Decide/execute
  buttons permit a double-click race (server-side bounded to a 409).
- Dead code: `Toaster`, `useToast`, `TweaksPanel`, `useInstallPrompt`,
  several `utils.ts` helpers; theme persists under the legacy
  `knowledge-os:theme` key.

### Test-suite hardening

- **`authority_of` silently ranks unmapped `PreferenceSource` members at 0**
  (`policy/trust.py:32`) — below AGENT, and self-superseding (0 ≥ 0). No test
  pins enum↔map completeness the way `risk_for_action` (which raises) is
  pinned. Make it raise, or add the exhaustiveness test.
- Policy denial loops omit `DUE_WORK_WORKER` for `MANAGE_CONFIGURATION`
  (`test_capabilities.py:111-120`) — use `all_clients()` as the
  `FINANCIAL_PAYMENT` test does.
- Fake↔real repository drift that lets fake-backed tests assert wrong
  behavior: fake person `upsert` overwrites `created_at` (real preserves via
  `ON CREATE`; affects `get_primary` ordering); fake action `create` ignores
  idempotency-key uniqueness; fake memory search drops the 8-term cap; fake
  `find_by_name` is unordered/unlimited (real: `ORDER BY … LIMIT 25`); fake
  world `link` records edges to missing endpoints (real MERGE no-ops
  silently); assorted missing `id DESC` tiebreaks and a per-label vs global
  LIMIT difference in `list_entities`.
- Console test fixtures use `as never` casts with wrong field names/casing
  (`status` vs `state`, uppercase types) — the type check that would catch a
  drifted page is suppressed.

---

## P2 — small fixes and polish

- `repositories/nornic/waiting.py:223-247`: `update()` never repairs the
  Task→`WAITING_ON` edge when `task_id` changes (property stays correct;
  graph shows the item blocking the wrong task).
- `repositories/nornic/shopping.py:61`: `substitution_allowed` default is
  unreachable and inverted — `row.get(..., True)` never applies (alias always
  present as `None`) so a missing property reads `False`, opposite the
  domain default.
- `events.py:68`: `SHOPPING_CHANGED` is defined and documented but never
  published (shopping publishes `WORLD_CHANGED`) — a subscriber written
  against the constant waits forever.
- `config/provider_registry.py`: email/calendar `password` secret fields are
  not `required=True`, so "configured" includes a password-less login that
  then attempts `LOGIN username ""`; `streaming` (ElevenLabs) and
  `default_calendar` (calendar) are Console switches nothing reads.
- `config/validation.py:51-53`: `FieldKind.URL` validates as bare text;
  ports carry no min/max (`-1` validates).
- `secrets/local_encrypted.py:232-239`: the fingerprint's "salt" is a fixed
  public string — fine for random API keys, but a human-chosen mail password
  can be dictionary-confirmed by anyone holding `secrets.json`. Consider
  HMAC keyed by the master key.
- `scripts/build-nornicdb.sh:24-25`: Go version gate is a lexical string
  compare (`go1.5` passes a `>= go1.26` check).
- `scripts/nornicdb.sh:84-91` + the systemd unit pass `--admin-password` on
  argv — visible in `/proc/*/cmdline` for the daemon's lifetime, defeating
  the 0600 file care. Check whether the binary accepts env/file input.
- `scripts/healthcheck.sh:27-28`: the NornicDB probe is a bare TCP connect —
  any listener on 7687 reports OK (the Core check authenticates, bounding
  the false positive to Core-down scenarios).
- `scripts/dev.sh:95-105`: `pkill -P` is single-level, orphaning Vite's
  esbuild children on stop; the console is never health-checked after
  launch.
- `pyproject.toml` markers `integration`/`persistence` are declared but no
  runner uses `-m`; the `integration` marker's description ("requires a
  running NornicDB") contradicts `tests/integration/` needing none.
- `browser/real.py:182-184`: the CDP connect branch never closes the browser
  it connects — dead code today, a pre-planted leak for the first site
  adapter.
- `voice/local.py:356-381`: the TTS producer thread has an unbounded queue
  and no cancellation when a consumer abandons the stream.
- `core.py:4103-4111` does synchronous file I/O in an async path;
  `container.py:123`'s `safe_mode` closure does a synchronous config read per
  capability check. Fine at single-user scale; noted.
- `domain/self_config.py:174-201`: the forbidden-effects gate inspects only
  the caller-declared `effects` list. The real boundary (frozen capability
  grants) holds regardless — add the one-line docstring note.

---

## Documentation corrections needed

The headline counts: **MCP_API.md documents 34 tools and 3 resources; the
server exposes 50 and 8** — the entire self-configuration write family
(`save_workflow_template` etc.) is absent, so the one document describing
what agents can do implies the agent surface cannot change durable routine
state when it can. Beyond that:

- **SECURITY.md**: "Over MCP a missing identity is refused, never defaulted"
  is false (P0-7). The stale Phase-0 paragraphs ("No client holds any
  external-action capability", "safe mode currently changes nothing
  observable") contradict the accurate capability table two lines above and
  understate a live safety mechanism. "Salted SHA-256" overstates the
  fingerprint. (The capability table itself verified cell-by-cell correct.)
- **DATA_MODEL.md**: the ServiceRequest and Shopping storage stories describe
  the pre-refactor JSON-blob design their own repositories' docstrings
  disavow; `(:Bill)`, `(:Payee)`, `(:WorkflowTemplate)`, `(:ShoppingItem)`,
  `OWED_TO`/`PAYEE_FOR`/`CONTAINS` edges, the `Knowledge` entity type, and
  nine boot-applied constraints/indexes are entirely undocumented; the
  telephony paragraph ("no default factory") predates the Twilio adapter.
- **HERMES_INTEGRATION.md**: the permission table says `hermes-personal` and
  `interactive-mcp` are "the same" and lists neither Hermes's external-action
  capabilities nor the Console's `FINANCIAL_PAYMENT` — it materially
  understates what a Hermes connection can do.
- **ARCHITECTURE.md**: the capability table omits every external-action
  capability and the Worker identity (all cells present are correct).
- **TESTING.md**: "Five suites" heads a seven-row table; `tests/chaos` is
  missing from the table; `make test-fast` is described as "unit + policy +
  integration — no database, ~1s" (it runs five suites in ~60-75s); the
  Phase 0 exit-test description is two eras stale (12 tools vs 45 pinned vs
  50 real); "Provider adapters. None exist" is present-tense false.
- **OPERATIONS.md**: the emergency stop documents `PATCH
  /api/v1/system/config`; the real route is `PUT /config/system`. (Everything
  else in OPERATIONS.md verified accurate against the scripts.)
- **CONFIGURATION.md**: fresh-deployment table says Telephony "Disabled"; with
  three required fields missing it reports "Not configured". The Phase-0
  claim that `/test` and `/discover` "report honestly that no adapter exists"
  is stale — both do real work now.
- **README.md**: the layout section omits the `spec` and `chaos` suites; the
  "all criteria pass" status claims are wrong until P0-1 and P0-2 land.
- Console-rendered claims (HermesPage "no skills", WorldPage history tooltip,
  sidebar phase copy) are documentation too — covered under Console above.

## Known-unverifiable in this environment

- NornicDB's transaction isolation for the lease claim and approval consume
  (needs a live concurrent test — recommended as part of P0-3's fix).
- faster-whisper's rejection of `cuda:0` (needs GPU hardware; API contract
  says it fails).
- The two acceptance-scenario e2e tests' current pass state (need live
  NornicDB; unlike the exit test, no static failure was found in them).
- CalDAV `{uid}.ics` href assumption may 404 for events created by other
  clients on servers that don't name resources by UID (server-dependent).

## What was checked and held (so it isn't re-litigated)

Local quality gates all green (ruff, mypy ×100 files, 999 Python + 202
Console tests, build). No approval/execute/payment path over MCP (verified
against all 50 tools); approval hash canonical, re-checked at commit, replay
closed sequentially; identity bound per connection, never a tool argument;
world writes over MCP hard-coded to sanctioned types; trust hierarchy blocks
external-content escalation; secret store cryptography sound end-to-end;
redaction recursive and correct; CSRF non-viable (non-wildcard CORS +
preflighted JSON writes); no subprocess/eval/XSS sinks; no Cypher outside
`repositories/nornic/`; all five documented NornicDB quirks respected
everywhere; Twilio and ElevenLabs adapters protocol-correct; blocking work
properly thread-wrapped; Hermes skills reinforce the boundaries; shell
scripts otherwise sound; no tautological tests found in sampling, and the
spec-suite scanners carry their own detector controls.
