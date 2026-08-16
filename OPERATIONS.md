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

Back up together:

```
~/.local/share/lifeops/nornicdb-data/        the world model
~/.local/share/lifeops/config/               non-secret configuration
~/.local/share/lifeops/secrets/secrets.json  encrypted secrets
```

Back up **separately**, to a different medium:

```
~/.local/share/lifeops/secrets/master.key
```

The master key decrypts every secret. Storing it beside the vault means one
compromised backup yields both halves.

Also worth keeping: `nornicdb.env`, without which the restored database is
unreachable.

Stop NornicDB before copying its data directory, or use its own export, so the
copy is not taken mid-write.

**A backup is not complete until a restore has been tested.** Automating that
loop is Phase 10 work (BUILD_SPEC section 80); until then, do it by hand
periodically:

```bash
make stop
cp -a ~/.local/share/lifeops/nornicdb-data /tmp/restore-test
LIFEOPS_NORNIC_DATA_DIR=/tmp/restore-test ./scripts/nornicdb.sh start
make health
# confirm known entities, relationships, and task state are present
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

Console → System → Safe mode blocks external communication, bookings, shopping,
and payments while leaving reads, conversation, and tasks working.

Phase 0 has no external write paths, so it currently changes nothing observable.
It exists now so later phases inherit it rather than bolting it on.

To stop everything: `make stop`. State, logs, and the database are preserved.
