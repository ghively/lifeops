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
back, so a typo is loud rather than a silent downgrade. Over MCP a missing
identity is refused, never defaulted. Over HTTP, a request with no header is
treated as the Console — the most privileged interactive identity. That is a
deliberate trade recorded here honestly: the HTTP API exists for the Console,
binds to loopback, and can be put behind the console password; but any local
process that can reach the port can claim the header, so the password (and the
loopback bind) are the boundary, not the header.

---

## Capabilities

As granted in `policy/capabilities.py` (the code is authoritative; this table
is a rendering of it):

| Capability | Hermes | Interactive | Coding agent | Worker | Console |
|---|:---:|:---:|:---:|:---:|:---:|
| `read_world` | ● | ● | ● | — | ● |
| `read_preferences` | ● | ● | ● | — | ● |
| `read_tasks` | ● | ● | ● | ● | ● |
| `read_memory` | ● | ● | ● | — | ● |
| `create_task` | ● | ● | ● | — | ● |
| `update_task` | ● | ● | — | ● | ● |
| `write_preference` | ● | ● | — | — | ● |
| `write_memory` | ● | — | — | — | ● |
| `write_world` | ● | — | — | — | ● |
| `self_configure` | ● | — | — | — | ● |
| `manage_configuration` | — | — | — | — | ● |
| `approve_action` | — | — | — | — | ● |
| `send_external_message` | ● | — | — | — | ● |
| `book_appointment` | ● | — | — | — | ● |
| `shopping_checkout` | ● | — | — | — | ● |
| `financial_payment` | — | — | — | — | ● |

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

### Console authentication (added in Phase 1, off until configured)

The Console and API ship with optional bearer-token authentication. It is
**disabled until a console password is set**: with no password configured,
every route answers without a token. Since Phases 7-10 the clients *do* hold
external-action capabilities (booking, messaging, shopping for Hermes and the
Console; payment for the Console alone), so the loopback bind is the only
boundary until the password is set — set one before enabling any real
provider. A headerless HTTP request is treated as the Console (see
Identity above), which makes this the first thing to harden.

Once a password exists in the secret store, all `/api/v1` routes except
`/health` and `/auth/login` require `Authorization: Bearer <token>`; the
Console shows a login screen. Tokens live in memory with a 12-hour expiry and
never touch NornicDB. The password itself is stored only in the encrypted
secret store and is never returned or logged. `LIFEOPS_CONSOLE_AUTH_ENABLED=false`
forces auth off even if a password exists.

Do not port-forward or reverse-proxy LifeOps Core or the Console to a routable
address with auth disabled.

### The MCP server trusts its launch configuration (by design)

Any local process that can execute `lifeops-mcp --client hermes-personal` gets
Hermes's capabilities. This is inherent to stdio MCP: the transport has no
authentication layer, and the launch configuration is the trust anchor.

Mitigated by the fact that such a process already has the user's filesystem
access. Revisit if LifeOps ever moves to a networked MCP transport.

### Configuration routes check MANAGE_CONFIGURATION (since 2026-08-18)

The `/config/*` and `/voice/*` management routes require the
`MANAGE_CONFIGURATION` capability, enforced in the HTTP adapter because the
config surface deliberately bypasses LifeOpsCore. The check ignores safe
mode on purpose: configuration is how the emergency stop is lifted, so the
stop must not lock the door to its own switch. Note the limit of what this
buys: HTTP identity is a self-declared header (see Identity above), so with
auth disabled a local process can still claim the Console's identity — the
capability check removes the accidental paths, the console password removes
the deliberate ones. Set the password.

### Phone-call destinations are model-influenced (dormant; decide before enabling telephony)

`place_phone_call` and `request_quote` are R2 — policy-controlled, not
approval-gated — because BUILD_SPEC section 101's acceptance scenario has
Hermes call the electrician on its own. The destination number is resolved
from the target provider entity's `phone` fact, and Hermes can write that
fact through `record_provider`. So once telephony credentials exist, a
model-authored fact chooses where an autonomous call is placed (the call's
*authority* stays hard-bounded — section 97: no charge, no repairs — but the
number itself is model data). Today this is dormant: telephony ships
disabled, and nothing here can dial. Before enabling real credentials,
decide deliberately between accepting this as-is, reclassifying the two
action types as R3 (which changes section 101's autonomous flow), or gating
dialable numbers behind a payee-style human confirmation. Recorded by the
2026-08-18 audit; deliberately not changed unilaterally because either code
change alters BUILD_SPEC-specified behavior.

### WebSocket events carry no payload beyond the type (accepted)

`/api/v1/events` publishes change notifications (`task_changed`,
`preference_changed`, and so on) so the Console can invalidate and refetch.
The events name what changed, not its contents; clients always read the data
back through the authenticated API.

---

## Reporting

This is a personal system with a single operator. If you are that operator and
find a problem, file it in `changes/requests/`.
