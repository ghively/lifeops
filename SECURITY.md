# Security

What LifeOps protects, how, and what is still open.

---

## Threat model

LifeOps holds a person's private world: who they know, what they prefer, what
they owe, and eventually the authority to act on their behalf. The concerns that
follow from that, in priority order:

1. **An agent exceeding its authority.** Models are influenceable. The system
   must not rely on any model choosing correctly.
2. **Credential exposure.** Provider keys, once leaked, are leverage over
   accounts LifeOps does not control.
3. **Untrusted content becoming authority.** Email and web pages are inputs. A
   web page must never be able to rewrite what the user said.
4. **Unverified external commitments.** A booking or payment that "probably
   happened" is worse than one that clearly failed.

---

## Client identity

Authority never comes from a model or provider name. Every request resolves to a
declared client identity, and policy consults that.

Identity is bound **per connection**:

- **MCP** — `--client` on the server process, set in the launch configuration
  the user writes.
- **HTTP** — the `X-LifeOps-Client` header; absent, the caller is treated as the
  Console, which is that API's purpose.

A tool argument would be model-controlled, letting any agent name itself
`hermes-personal`. An unrecognised `--client` exits non-zero rather than falling
back, so a typo is loud rather than a silent downgrade. A missing identity
resolves to the *least* privileged interactive default, never to Hermes.

---

## Capabilities

| Capability | Hermes | Interactive | Coding agent | Console |
|---|:---:|:---:|:---:|:---:|
| `read_world` | ● | ● | ● | ● |
| `read_preferences` | ● | ● | ● | ● |
| `read_tasks` | ● | ● | ● | ● |
| `create_task` | ● | ● | ● | ● |
| `update_task` | ● | ● | — | ● |
| `write_preference` | ● | ● | — | ● |
| `manage_configuration` | — | — | — | ● |
| `approve_action` | — | — | — | ● |
| `send_external_message` | — | — | — | — |
| `book_appointment` | — | — | — | — |
| `shopping_checkout` | — | — | — | — |
| `financial_payment` | — | — | — | — |

Enforced server-side in `LifeOpsCore`, before any repository call. A client
cannot grant itself more, and the grants are immutable at runtime.

**No client holds any external-action capability in Phase 0.** Those enums exist
so that audit records and configuration have a stable vocabulary before the
adapters land; nothing can exercise them.

Two deliberate asymmetries:

- **The coding agent cannot write preferences or update tasks.** Its job is the
  repository, not the user's life. It can read the world and file a task.
- **Only the Console configures and approves.** An agent approving its own
  action would defeat the gate; approval requires the surface where a human is
  actually present.

---

## Secrets

Secrets never enter NornicDB. The database holds the world model, which agents
read broadly and the Console renders; credentials have no business in that blast
radius.

`LocalEncryptedSecretStore` is the default backend:

| Property | Choice | Why |
|---|---|---|
| Cipher | AES-256-GCM | Tampering is detected, not decrypted into garbage |
| Key | 32 random bytes, generated on first use | |
| Key location | `~/.local/share/lifeops/secrets/master.key`, mode 0600, created with `O_EXCL` | Outside the repository; no default-umask window |
| Nonce | Fresh 12 bytes per write | Nonce reuse under one GCM key is a break |
| AAD | The secret's name | A ciphertext cannot be relabelled to another field |
| Storage | `secrets.json`, mode 0600, written then renamed | An interrupted write cannot truncate the vault |

Reads return `{"configured": true, "fingerprint": "a1b2c3d4e5f6"}` — never the
value. The fingerprint is a salted SHA-256 prefix, so a human can confirm *which*
key is installed without it being readable.

`rotate_master_key()` re-encrypts every secret under a fresh key.

The master key is the entire security boundary: anyone who can read it can read
every secret. Back it up **separately** from the vault.

### Never logged

API keys, tokens, cookies, passwords, card data, and MFA codes are redacted
from every structured log line by field name, recursively, at all levels.

---

## Trust hierarchy

```
user_explicit  >  system  >  calendar  >  document  >  email / phone_call
               >  conversation  >  website  >  user_inferred  >  agent
```

A weaker source cannot supersede a stronger one. An inference that tries to
overwrite what the user said directly is refused with `conflict`.

Equal authority *may* supersede — the user restating a preference, or a calendar
re-sync, is a legitimate update.

External content creates evidence. It does not create user authority. This is
the structural answer to prompt injection in email and web content: a message
can persuade a model to *call* `save_preference`, but it cannot make the
resulting record outrank the user, and it cannot reach a capability the client
does not hold.

---

## Verification

A task marked `verification_required` reaches `COMPLETED` only through
`VERIFYING`, and only with evidence attached. Both conditions are checked in the
domain layer, so the HTTP and MCP paths get the same gate.

An external action is not complete because a model says so.

---

## Safe mode

Blocks external communication, bookings, shopping checkout, and payments while
leaving conversation, reads, memory search, and tasks working. Checked *before*
the capability grant, so it cannot be defeated by a client that happens to hold
the capability.

Toggle it from Console → System.

Phase 0 has no external write paths, so it currently changes nothing observable.
It exists now so later phases inherit it rather than bolting it on.

---

## Network exposure

| Service | Binds | Reachable from |
|---|---|---|
| NornicDB Bolt | `127.0.0.1:7687` | localhost |
| NornicDB HTTP | `127.0.0.1:7474` | localhost |
| LifeOps Core | `127.0.0.1:8080` | localhost |
| Console (dev) | `127.0.0.1:5173` | localhost |

Nothing listens on a routable interface by default. NornicDB's own admin UI is
disabled (`--headless`) — LifeOps Console is the only interface LifeOps offers,
and a second administrative surface on the same data is a second thing to
secure.

The NornicDB admin password is generated at first initialisation, stored 0600 in
`~/.local/share/lifeops/nornicdb.env`, and never committed or typed by a human.

---

## Repository hygiene

`.gitignore` excludes `.venv/`, `*.key`, `secrets.json`, and `.env`. The Phase 0
exit test asserts that no `master.key` or `secrets.json` is tracked, so this is
checked rather than assumed.

No provider credential appears anywhere in the repository. A fresh checkout
boots with every provider unconfigured, which is what lets development proceed
without anyone holding the user's keys.

---

## Known gaps

Recorded rather than hidden. Each has a phase.

### The Console has no authentication (Phase 1)

Phase 0 ships no login. Anyone with access to `127.0.0.1:5173` — or to any
process on the machine — can read and modify LifeOps state through the Console.

The exposure is bounded: loopback-only binding, and no client holds an
external-action capability, so the worst case is local disclosure and corruption
of personal state, not action taken in the user's name.

Do not port-forward or reverse-proxy LifeOps Core or the Console to a routable
address until Phase 1 lands.

### The MCP server trusts its launch configuration (by design)

Any local process that can execute `lifeops-mcp --client hermes-personal` gets
Hermes's capabilities. This is inherent to stdio MCP: the transport has no
authentication layer, and the launch configuration is the trust anchor.

Mitigated by the fact that such a process already has the user's filesystem
access. Revisit if LifeOps ever moves to a networked MCP transport.

### There is no audit log yet (Phase 4)

Semantic operations are logged with trace IDs and durations, but there is no
durable, queryable audit trail in NornicDB, and no Activity screen. "Why did
Hermes do that?" is currently answerable only from log files.

### The Console's transition list duplicates the server's (accepted)

`TASK_TRANSITIONS` in the Console mirrors the server's table so the UI offers
only valid choices. They could drift.

The consequence of drift is bounded: the server re-validates every transition
and rejects an illegal one, so a stale UI shows a choice that then fails with a
clear error. It never permits an illegal write. Phase 1 should serve the table
from the API instead.

---

## Reporting

This is a personal system with a single operator. If you are that operator and
find a problem, file it in `changes/requests/`.
