# Testing

Five suites, each proving something different. Run everything with `make test`
plus `make console-test`.

| Suite | Needs NornicDB | Proves |
|---|:---:|---|
| `tests/unit` | no | Domain rules: state machine, temporal preferences, secrets, config |
| `tests/policy` | no | Capability enforcement and the trust hierarchy |
| `tests/integration` | no | The HTTP API contract the Console depends on |
| `tests/persistence` | yes | The Cypher is right and the graph shape is what later phases will traverse |
| `tests/e2e` | yes | The Phase 0 exit criteria, over real MCP |
| `tests/spec` | no | BUILD_SPEC enumerations are implemented in full, every repository Protocol has a matching fake, no test fakes LifeOpsCore, every NornicDB repository has a persistence test |
| `console/src/**/__tests__` | no | Console rendering and data flow |

---

## Running

```bash
make test-fast          # unit + policy + integration — no database, ~1s
make test-integration   # persistence, against a live NornicDB
make test-e2e           # the Phase 0 exit test
make test               # everything Python
make console-test       # Console
make check              # what CI runs
```

Suites needing NornicDB skip themselves when it is not reachable, so the fast
path runs anywhere. `make` sources the generated credential from
`~/.local/share/lifeops/nornicdb.env` automatically.

---

## What the fakes are for

`repositories/fakes/` holds in-memory implementations of every repository
Protocol. Domain and policy tests run against them.

They are not a second storage backend — nothing there survives a restart, and
they are never wired into a running deployment. Their real job is to keep the
abstraction honest: **if a domain test ever needs Cypher to pass, the
abstraction has leaked.**

---

## The Phase 0 exit test

`tests/e2e/test_phase0_exit.py` is the acceptance gate from BUILD_SPEC
section 109.

Every MCP session in it is a **real subprocess** speaking the real protocol over
stdio. "Kill that Hermes session" means the process actually dies. Nothing is
shared between sessions except NornicDB — which is the point: if state survived
because it sat in a Python object, the tests would pass while the architecture
was wrong.

| Criterion | Test |
|---|---|
| A–C. A preference outlives the session that wrote it | `test_a_through_c_preference_survives_the_session_that_wrote_it` |
| D. It survives a NornicDB restart | `test_preference_survives_a_nornic_restart` |
| E. A second client reads the same preference | `test_e_second_client_reads_the_same_preference` |
| F–G. The second client creates a task; Hermes lists it | `test_f_and_g_second_client_creates_a_task_hermes_lists_it` |
| H. The Console sees the same task state | `test_h_console_sees_the_same_task_state` |
| I. No parallel source of truth | `TestNoParallelSourceOfTruth` |
| J. The Console boots with no provider credentials | `TestFreshDeploymentNeedsNoCredentials` |

Plus: exactly the sanctioned tools are exposed — five from Phase 0, three
from Phase 2, four from Phase 3 — no raw-database tool exists, the
capability manifest holds across the MCP boundary, and an unknown client
identity is refused at launch.

### The restart test

Criterion D needs a way to restart the database, which the test cannot assume.
It skips unless `LIFEOPS_NORNIC_RESTART_CMD` is set — a skip rather than a
silent pass, so a missing restart mechanism is visible.

`make test-e2e` sets it to `./scripts/nornicdb.sh restart`.

### A note on the Hermes client

This repository does not contain the user's Hermes runtime. The e2e sessions
connect with `--client hermes-personal`, which is exactly the identity and
interface Hermes uses. What is exercised is the LifeOps side of that contract —
the half this repository owns. See [HERMES_INTEGRATION.md](HERMES_INTEGRATION.md).

---

## Test isolation

Persistence tests write under a per-test label and clean up in a fixture
teardown, so they leave no residue in a shared database and do not collide with
each other.

The e2e suite purges its own keys before *and* after each test — before as well,
because a previous crashed run should not make the next one fail for the wrong
reason.

---

## Determinism

`FrozenClock` is injected wherever time affects behaviour. Supersession
windows, validity ranges, and ordering are all tested against a clock the test
advances explicitly, rather than against the wall clock.

---

## What is not tested here

**Browser end-to-end.** Playwright does not support this host's OS version, so
Console coverage is vitest component tests against a mocked LifeOps client plus
a live curl check of the Vite proxy. Real browser coverage should return in
Phase 1 on a supported host.

**Provider adapters.** None exist in Phase 0. `POST /config/providers/{id}/test`
reports honestly that the adapter is not implemented rather than returning a
fake success — a Test button that lies is worse than one that says "not yet",
and that behaviour is itself asserted.

**Chaos and failure injection.** BUILD_SPEC section 86 lists 16 scenarios; all
16 are now covered — `tests/chaos/` (13, fakes-only, part of `make test-fast`)
and `tests/e2e/test_chaos_duplicate_mcp_request.py` (the one that needs a live
NornicDB and a real MCP subprocess). Three (DeepSeek timeout, local ASR crash,
local TTS crash) are honest, documented skips: no adapter or runtime exists
yet for the failure to happen to.
