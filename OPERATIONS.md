# Operations

Running, backing up, and recovering LifeOps.

---

## Layout on disk

```
~/.local/lib/lifeops/nornicdb          the database binary
~/.local/share/lifeops/
  nornicdb-data/                       NornicDB storage
  nornicdb.env                         generated admin credential, 0600
  secrets/master.key                   secret-store master key, 0600
  secrets/secrets.json                 encrypted secrets, 0600
  config/lifeops.config.json           non-secret provider and system settings
  logs/                                nornicdb, lifeops-core, lifeops-console
```

All durable state lives outside the repository. `make clean` never touches it.

---

## Daily operation

```bash
make dev        # start NornicDB, LifeOps Core, and the Console
make status     # what is running
make health     # component health
make stop       # stop everything
```

Individually:

```bash
./scripts/nornicdb.sh start|stop|restart|status|logs
./scripts/dev.sh start|stop|restart|status
./scripts/healthcheck.sh
```

`healthcheck.sh` exits non-zero if anything required is unhealthy, so it can
gate a deploy or drive a monitor. Its component detail comes from LifeOps
itself, so it reflects what the Console shows rather than a second, drifting
definition of health.

---

## Due-work worker

BUILD_SPEC section 55's continuation loop: an asyncio task inside LifeOps
Core, started by `Container.startup()` and stopped by `Container.shutdown()`.
No separate process, queue, or scheduler — see `core/lifeops/worker/due_work.py`.

It holds no state of its own. Every tick it re-reads what is due from
NornicDB, claims a lease, and acts; killing and restarting LifeOps loses
nothing, which is BUILD_SPEC section 93's acceptance criterion for Phase 4.

Deployment settings (`.env` / environment, not the Console):

```
LIFEOPS_DUE_WORK_ENABLED=true         # set false to disable the worker entirely
LIFEOPS_DUE_WORK_POLL_INTERVAL_S=60   # how often it checks for due items
LIFEOPS_DUE_WORK_BATCH_LIMIT=50       # items claimed per tick
```

Running more than one LifeOps process against the same NornicDB runs more
than one worker; this is safe by construction because leases are claimed
atomically (`repositories/nornic/waiting.py`), so at most one worker acts on a
given item at a time.

---

## First run

```bash
make setup
make nornic-build
make dev
```

`nornicdb.sh` generates a random admin password into `nornicdb.env` on first
start. You are never asked for it and it is never committed.

**The password is fixed when the data directory is initialised.** NornicDB
writes it into storage on first boot, so `--admin-password` has no effect on an
existing data directory. Pointing a fresh `nornicdb.env` at existing data fails
to authenticate. To change it, use NornicDB's admin API — or delete the data
directory, which destroys everything in it.

---

## Building NornicDB

```bash
./scripts/build-nornicdb.sh [version]    # defaults to v1.2.2
```

Upstream ships Docker images and macOS packages. On a Linux host without Docker,
building the Go binary is the shortest path and avoids adding a container
runtime to satisfy one dependency. The script downloads a Go toolchain if the
system one is older than 1.26.

Build tags `noui,nolocalllm` match upstream's CPU image:

- `noui` — LifeOps Console is the only interface LifeOps offers. A second
  administrative surface on the same data is a second thing to secure.
- `nolocalllm` — no bundled llama.cpp. Embeddings, when Phase 2 needs them, come
  from a configured provider rather than from the database process.

Embeddings are off in Phase 0. There is nothing to embed until memory arrives,
and loading a model now would be capacity held against a problem that does not
exist yet.

---

## Configuration

Two distinct things, deliberately separated:

| | Deployment settings | Runtime configuration |
|---|---|---|
| What | Ports, data directories, database URI | Provider keys, models, voices, accounts |
| Where | Environment / `.env` | LifeOps Console |
| Set by | Whoever installs it | The user, after deployment |
| In git | Never (values) | Never |

See [CONFIGURATION.md](CONFIGURATION.md).

---

## Backups

```bash
./scripts/backup.sh [destination-dir]                        # defaults to
                                                                # $LIFEOPS_HOME/backups/<timestamp>
./scripts/restore.sh <backup-dir> <destination-home> [--force]
```

`backup.sh` stops NornicDB if it is running (so the copy is not taken
mid-write), copies its data directory, `nornicdb.env`, non-secret
configuration, and the encrypted secret store, then restarts NornicDB if it
had been running. It writes:

```
<destination>/
  manifest.json               what was captured, and when
  nornicdb-data/               the world model
  nornicdb.env                 the generated admin credential — without it,
                                the restored database cannot authenticate
                                (CLAUDE.md: the password is fixed at
                                data-directory initialisation)
  config/                      non-secret configuration
  secrets/secrets.json         encrypted secrets
  secret-master-key/master.key kept in its own subtree
```

**Move `secret-master-key/master.key` to separate, secure storage right
away.** The master key decrypts every secret; leaving it beside the rest of
the backup means one compromised copy yields both halves.

`restore.sh` takes an explicit destination — there is no default and it is
never inferred from `LIFEOPS_HOME` — so a restore can never land on a real
deployment by accident. It refuses a non-empty destination unless `--force`
is given.

```bash
LIFEOPS_HOME=$RESTORE_DEST ./scripts/nornicdb.sh start
make health
# confirm known entities, relationships, and task state are present
```

**A backup is not complete until a restore has been tested.** That loop is no
longer manual: `tests/persistence/test_backup_restore.py` drives
`backup.sh` and `restore.sh` against a disposable NornicDB instance on a
temporary data directory — never `~/.local/share/lifeops` — writes known
state, backs it up, destroys the original, restores into a fresh location,
and asserts the known state (a person, a preference, an encrypted secret,
and non-secret configuration) reads back exactly. It skips cleanly, rather
than failing, when the NornicDB binary is not present to spin up an isolated
instance. Run it with `make test-integration` or directly:

```bash
./.venv/bin/pytest tests/persistence/test_backup_restore.py -q
```

---

## Logs

Structured JSON to stderr, collected per process under `logs/`.

```json
{"time":"2026-08-16T16:40:00Z","level":"INFO","component":"lifeops.operation",
 "message":"preference.write","trace_id":"a1b2…","client_id":"hermes-personal",
 "operation":"preference.write","result":"ok","duration_ms":4.2}
```

Semantic operation names — `preference.write`, `task.transition`,
`policy.evaluate` — with trace IDs and durations. Every HTTP response carries
`x-trace-id`, so a Console error can be traced to its server-side operation.

API keys, tokens, cookies, passwords, card data, and MFA codes are redacted by
field name, recursively.

The MCP server logs to stderr only, because stdout carries the protocol.

Full observability (Grafana, Tempo, Prometheus) is optional and deliberately
deferred — for a single-user system, structured logs and trace IDs answer the
questions that come up.

---

## Troubleshooting

**"Cannot reach LifeOps Core"** — `make status`. If Core is stopped, check
`logs/lifeops-core.log`; the usual cause is NornicDB not running.

**`repository_error` from the API** — NornicDB is down or the credential is
wrong. `./scripts/nornicdb.sh status`, then `logs/nornicdb.log`.

**`AuthError: Invalid credentials`** — `nornicdb.env` does not match the
password baked into the data directory. See "First run" above.

**"Something is already listening on Bolt port 7687"** — a stray instance from a
previous run. It would hold the port while serving a *different* data directory,
which is a confusing way to lose data, so the script refuses to start rather
than racing it.

**MCP client will not connect** — run the server by hand to see the error:

```bash
./.venv/bin/python -m lifeops.mcp.server --client hermes-personal
```

An unknown `--client` exits non-zero on purpose.

---

## Emergency stop

Console → System → **Emergency stop** engages safe mode (BUILD_SPEC sections
83, 84). It blocks external communication, bookings, browser writes, shopping
submission, telephony writes, and payments while leaving conversation, reads,
memory search, tasks, local state, and Console inspection working. The current
state (on/off) is always shown, and the toggle round-trips through
`PATCH /api/v1/system/config` — the setting lives in `lifeops.config.json`, not
just process memory, so it survives a restart.

Engaging it deletes nothing: state, logs, the audit log, the database, and
every previously prepared action stay exactly as they were and remain readable.
`tests/policy/test_emergency_stop.py` proves both halves — every `ActionType`
is refused at `core.prepare_action` while it is engaged, and everything it is
supposed to preserve still reads back afterward. `console/src/pages/lifeops/__tests__/SystemPage.test.tsx`
proves the Console control itself is present, clearly labelled, and reflects
the real state.

To stop everything, including the process: `make stop`. State, logs, and the
database are preserved.
