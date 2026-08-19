# 2026-08-19 — Live deployment audit (gh-ai)

The first audit of LifeOps running as a real deployment rather than a
checkout: systemd user units on `gh-ai`, Console published to the tailnet,
Hermes attached over MCP, ElevenLabs live. Eight passes; every claim below
was exercised against the running system, not read from code.

## Verdict

Functional. Every surface — HTTP, MCP, Console, WebSocket, tailnet — works
and enforces its boundaries. Two real defects found and fixed the same day
(one data-correctness, one backup-consistency), both specific to conditions
no sandbox run could have produced.

## Findings

### P1 — Universal search returned duplicate rows (fixed)

`CONTAINS` + `ORDER BY` + `LIMIT` in a single Cypher clause makes NornicDB
return one row per text-index posting rather than one per node: a task that
had been written to a few times came back **seven times** from one search.
Isolated by bisection — `LIMIT` alone, `ORDER BY` alone, and equality-`WHERE`
plus both are all clean; only the text-scan path breaks, and only with both
sort and limit present. Four queries had the fatal shape (tasks,
preferences, people, memory substring). All now sort and limit through a
`WITH` stage before the projection, with a Python seen-set as backstop —
`DISTINCT` was rejected as the fix because this database already
demonstrated it does not reliably dedupe aliased columns (`shopping.py`).
Pinned by `test_search_returns_each_match_exactly_once` in
`tests/persistence/test_nornic_search.py`; quirk recorded in CLAUDE.md.

### P1 — backup.sh copied the live database hot under systemd (fixed)

The script's was-it-running check reads its own PID file, which a
systemd-managed database never writes. It concluded "not running" and copied
`nornicdb-data/` mid-write — silently forfeiting the consistency stop that
is the script's whole reason for stopping the database. Verified against
unit timestamps: the DB was started 23:06:37 and untouched by the 23:07:22
backup. The script now detects the manager (script PID file → script;
active `lifeops-nornicdb` unit → systemctl; anything else holding Bolt →
refuse loudly rather than hot-copy), and restarts **both** database and
core afterwards, because `Requires=` propagates stops but starts do not
propagate back. Re-verified: cold backup taken, restored into a disposable
home, and the restored data (preference, provider, memory) read back
through an isolated NornicDB instance.

## What was verified clean

- **Network posture.** Every LifeOps listener on loopback (7474, 7687,
  8085, 5173, 9090); the only tailnet exposure is `tailscale serve` → 8445.
  No credential on any process cmdline; none in journal or file logs.
- **Secrets.** All state files 0600; raw API key absent from database
  storage and the repo; secret store holds 2 encrypted entries.
- **Auth wall.** Ten route classes 401 unauthenticated; `/health` and
  `/auth/login` open by design; unauthenticated WebSocket refused (403).
- **MCP identity.** Unknown `--client` exits with a named error.
  `claude-code` is offered `save_preference` but the call is refused at
  the capability layer (`capability_denied`) — enforcement in core, not in
  tool listing, as documented.
- **Cross-surface state (section 102).** A task created by `claude-code`,
  a preference and memory written by `hermes-personal`, and a provider via
  `record_provider` all read back over Console HTTP; `lifeops://today`
  reflects them; live `task_changed` event received over the WebSocket
  within the same second as the write.
- **Emergency stop.** Engaged over `PUT /config/system`: `send_email`
  refused with `safe_mode` error naming the blocked capability; reads kept
  working; disengaged; state persisted to `lifeops.config.json`.
- **Resilience.** `systemctl restart lifeops-nornicdb` propagates to core
  (`Requires=`), stack self-heals, all state survives. `kill -9` on core:
  systemd resurrects it within seconds, health 200. `dev.sh start` under
  systemd refuses the held Bolt port rather than racing it.
- **Reboot survival.** All three units enabled, linger on, tailscale serve
  configuration persistent.
- **Suite.** 1215 passed, 5 skipped; ruff and mypy clean; Console 202/202.

## Residue

Audit probe data was removed: probe tasks cancelled (terminal records kept
by design), probe memory and preference invalidated (supersession chains,
not deletion), probe provider node removed directly (the API rightly
offers no world-entity delete), drill backup deleted (it contained a
master.key copy). Two CANCELLED tasks and the audit-trail records remain,
by design — the audit log is append-only.

## Watch items (no action taken)

- The task list API returns terminal (CANCELLED) tasks in the default
  listing; the Console filters them visually. Cosmetic at current scale.
- Log files under `~/.local/share/lifeops/logs/` have no rotation; the
  systemd units log to the journal, which does. Revisit if the file logs
  are still growing in a month.
- The due-work worker logged exactly one failed tick — timestamped to the
  deliberate database restart during the password migration, self-recovered
  on the next tick. Working as designed.
