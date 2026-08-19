# LifeOps MCP API

The portable agent interface. Hermes is the primary consumer; any trusted MCP
client can connect to the same server and operate on the same personal state,
subject to its own permissions.

**The server exposes fifty-two tools and eight resources** (the authoritative
list is `test_exactly_the_sanctioned_tools` in
`tests/e2e/test_phase0_exit.py`, which pins the surface exactly). Phases 0-4
shipped the set documented in detail below: the Phase 0 tools (BUILD_SPEC
section 49), the memory tools of section 91, the world-graph reads of section
92, and the durable-work tools of section 51. Phases 7-9 added calendar,
email, telephony, service-request, and shopping tools, summarised in
"Phase 7-9 tools" at the end of this document. The self-configuration pass
(sections 73-76) added `save_workflow_template`, `list_workflow_templates`,
`due_routines`, `delete_workflow_template`, and `propose_self_change` — the
first two of which write durable routine state; `propose_self_change` and
`request_code_change` are pure gates that write nothing themselves. The
2026-08-18 audit follow-up added the shopping read-back pair
(`list_shopping_lists`, `get_shopping_list`) and the section-50 read tools,
and gave `remember` (`entity_ids`, `source_id`), `create_task`/`update_task`
(`related_entity_ids`), `save_preference` (`importance`),
`create_calendar_hold` (`hold_minutes`), `search_memory` (`memory_types`),
and `list_bills` (`statuses`) the parameters their HTTP counterparts already
had. Beyond the three resources documented below, the server also serves
`lifeops://household`, `lifeops://approvals`, `lifeops://entity/{id}`,
`lifeops://task/{id}`, and `lifeops://provider/{id}`.

World writes over MCP are narrow and named: `record_provider`,
`record_asset`, and `create_service_request` are the only tools that spend
`write_world` (section 51 sanctions exactly these). Creating relationships
and generic entities stays on the Console: shaping the user's world is their
act, not a model's.

---

## Resources

Read-only context, fetched as MCP resources rather than called as tools.
Failures come back as the same `{"ok": false, "error": ...}` data shape the
tools use, honouring the connecting client's capabilities.

### `lifeops://me`

The person the assistant is acting for — the primary user. Consult at session
start instead of asking who you are talking to.

### `lifeops://today`

The current operating picture: open tasks, the subset already due, and the
standing preferences in effect right now. Read this before planning the day's
work; do not treat it as a license to act — actions still go through the tools
and their capability checks.

### `lifeops://waiting`

Tasks in `WAITING_EXTERNAL` with their waiting context — what was attempted and
when. Use it to decide whether to follow up. Follow-up automation (the
due-work worker) is server-side; there is no tool to trigger it directly.

---

## Connecting

```bash
python -m lifeops.mcp.server --client <client-id> [--transport stdio]
```

Generate a ready-made launch entry:

```bash
./hermes/bootstrap/register-mcp-client.sh hermes-personal
```

### Client identity

Identity is declared **per connection**, not per call.

A `client_id` tool argument would be model-controlled, which would let any agent
name itself `hermes-personal` and inherit Hermes's capabilities. Binding it to
the connection means the launch configuration — written by the user — decides.

An unrecognised `--client` exits non-zero rather than falling back, so a typo in
a launch config is loud instead of a silent downgrade.

| Client ID | Role | Intended for |
|---|---|---|
| `hermes-personal` | primary_assistant | Hermes |
| `interactive-mcp` | interactive_assistant | ChatGPT and other conversational clients |
| `claude-code` | engineering_assistant | Coding agents |
| `lifeops-console` | console | The Console's HTTP path |

Permissions per identity: [SECURITY.md](SECURITY.md).

---

## Result shape

Every tool returns a JSON object with an `ok` field.

```json
{ "ok": true, "preference": { "id": "preference_01j...", "key": "...", "value": "..." } }
```

Failures come back as data, not as a protocol error:

```json
{ "ok": false, "error": "capability_denied", "message": "client 'claude-code' may not write_preference", "client_id": "claude-code" }
```

The `error` code is stable, so a model can tell "you may not do that" from "that
does not exist" and react accordingly instead of retrying blindly.

| Code | Meaning |
|---|---|
| `not_found` | No such entity |
| `validation_error` | The input was malformed |
| `conflict` | The write contradicts existing state |
| `invalid_transition` | The task state machine forbids this move |
| `verification_required` | Completion needs evidence from the target system |
| `capability_denied` | This client identity lacks the capability |
| `safe_mode` | Blocked while LifeOps is in safe mode |
| `repository_error` | NornicDB is unreachable or failed |

---

## Tools

### `get_person`

Look up a person. With no arguments, returns the primary user — who the
assistant is acting for.

| Argument | Type | Default | Notes |
|---|---|---|---|
| `person_id` | string? | — | Canonical ID, e.g. `person_gene` |
| `name` | string? | — | Search display names and aliases instead |

```json
{ "ok": true, "person": { "id": "person_gene", "display_name": "Gene", "is_primary": true } }
```

With `name`, returns `people` (a list) rather than `person`.

---

### `get_preferences`

Current preferences for a subject. Only records still in effect are returned;
superseded ones are omitted.

Consult this before making any scheduling, purchasing, or contact decision on
the user's behalf.

| Argument | Type | Default | Notes |
|---|---|---|---|
| `subject_id` | string? | primary user | Whose preferences |
| `key_prefix` | string? | — | e.g. `scheduling` |

```json
{
  "ok": true,
  "preferences": [
    {
      "id": "preference_01j...",
      "key": "scheduling.earliest_appointment_time",
      "value": "I don't like appointments before ten.",
      "confidence": 1.0,
      "source": "user_explicit",
      "since": "2026-08-16T16:40:00Z"
    }
  ],
  "total": 1
}
```

---

### `save_preference`

Record a lasting preference.

Use it when the user states how they want things done — "nothing before ten",
"always the same mechanic" — not for one-off instructions about the current
task.

| Argument | Type | Default | Notes |
|---|---|---|---|
| `key` | string | — | Stable dotted topic key. Reuse the existing key when updating. |
| `value` | string | — | The preference, in the user's own terms |
| `subject_id` | string? | primary user | |
| `source_type` | enum | `user_explicit` | Governs whether it may supersede |
| `confidence` | float | `1.0` | 0–1 |
| `notes` | string? | — | |

**Supersession.** Saving a key that already exists closes the previous record's
validity window and links the new one with `SUPERSEDES`. Nothing is overwritten.
Re-saving an identical value is a no-op, so repeated conversation turns do not
pile up history.

**Trust.** A weaker source cannot displace a stronger one. Set `source_type` to
`user_explicit` only when the user actually said it; use `user_inferred` when
you are guessing. An inference that tries to overwrite an explicit statement is
refused with `conflict`:

```
user_explicit  >  system  >  calendar  >  document  >  email
               >  conversation  >  website  >  user_inferred  >  agent
```

External content creates evidence. It does not create user authority.

---

### `create_task`

Capture a durable task. It persists across conversations and is visible in the
Console and to every other client.

This records intent only; it executes nothing.

| Argument | Type | Default | Notes |
|---|---|---|---|
| `title` | string | — | Short imperative summary |
| `description` | string? | — | |
| `priority` | enum | `medium` | `low`/`medium`/`high`/`urgent` |
| `due_at` | string? | — | RFC 3339 |
| `owner_entity_id` | string? | primary user | |
| `verification_required` | bool | `false` | See below |

Set `verification_required` when completion will depend on an outside party
confirming it — a booking, an order, a payment. Such a task cannot be closed on
assertion alone; it must pass through `VERIFYING` with evidence attached.

Tasks are created in `CAPTURED`. There is no way to create one directly in a
later state, because that would be a way to skip the state machine.

---

### `list_tasks`

| Argument | Type | Default | Notes |
|---|---|---|---|
| `state` | string[]? | all | Filter by state |
| `owner_entity_id` | string? | all | |
| `limit` | int | `50` | 1–200 |

```json
{
  "ok": true,
  "tasks": [
    {
      "id": "task_01j...",
      "title": "Call dentist",
      "state": "CAPTURED",
      "priority": "medium",
      "due_at": null,
      "needs_attention": false
    }
  ],
  "total": 1
}
```

`needs_attention` is true in `NEEDS_APPROVAL`, `BLOCKED`, and `FAILED`.

---

### `search_memory`

Recall relevant memories before answering questions about the user's past,
people, routines, or prior decisions.

Do **not** use it for current transactional state — open tasks, today's
preferences, approvals — that is what `list_tasks` and `get_preferences` are
for. Do not use it to store anything; that is `remember`.

| Argument | Type | Default | Notes |
|---|---|---|---|
| `query` | string | — | What to recall |
| `subject_id` | string? | primary user | Whose memories |
| `limit` | int | `10` | |

---

### `remember`

Store a durable memory: a semantic fact, an episodic note, or a low-confidence
`preference_candidate`.

This records memory only. It cannot change tasks, preferences, approvals, or
any transactional state (BUILD_SPEC section 44). When the user *states* a
preference, use `save_preference` instead — a memory is not a preference.
Never store secrets; the server refuses credential-shaped content.

| Argument | Type | Default | Notes |
|---|---|---|---|
| `content` | string | — | The memory, in plain terms |
| `type` | enum | — | `episodic` / `semantic` / `preference_candidate` / `summary` / `association` |
| `subject_id` | string? | primary user | |
| `source_type` | enum | `conversation` | Same trust ranking as preferences — do not mark inferences `user_explicit` |
| `confidence` | float? | — | 0–1 |
| `importance` | float? | — | 0–1 |

---

### `invalidate_memory`

Mark a memory as no longer valid. This is a temporal close, never a delete —
the record stays in the history chain.

| Argument | Type | Default | Notes |
|---|---|---|---|
| `memory_id` | string | — | |
| `reason` | string | — | Why it no longer holds |

To correct a memory's content, `remember` the corrected version and invalidate
the old one, or use the Console's correct action, which links the supersession
chain explicitly.

---

### `find_person`

Locate a person by display name or alias. Call it before creating or linking
anything about a person, so the work attaches to the canonical record instead
of a duplicate.

| Argument | Type | Default | Notes |
|---|---|---|---|
| `name` | string | — | Display name or alias, e.g. `Alex` |

Returns `{ok, people[], total}`. No match is an empty list, not an error.
For the primary user, no-argument `get_person` is cheaper.

---

### `get_provider`

A provider entity — a company or service the user deals with — and its current
facts. Accepts a canonical `provider_...` ID or a name.

| Argument | Type | Default | Notes |
|---|---|---|---|
| `name_or_id` | string | — | `provider_abc_electric` or `ABC Electric` |

A unique name match returns `{ok, provider}` with the full entity detail;
several matches return `{ok, providers[], total}` so the model asks which one
rather than guessing.

This is **not** provider *configuration*. API keys, model choices, and
credentials are managed by the user in the Console and are never reachable
here.

---

### `get_related_entities`

The one-hop neighbourhood of an entity: what it is connected to, and how. This
is the tool for a relationship question — "who handles our electricity?",
"what is linked to the Land Rover?".

| Argument | Type | Default | Notes |
|---|---|---|---|
| `entity_id` | string | — | `person_gene`, `provider_abc_electric`, … |

Returns `{ok, neighborhood: {nodes[], edges[]}}`. It reports current
*structure*; `search_memory` recalls past events and notes.

---

### `get_entity_history`

What the record can say about how an entity changed.

| Argument | Type | Default | Notes |
|---|---|---|---|
| `entity_id` | string | — | |

Returns `{ok, entity_id, memories[], covers[]}`. World entity facts are
current-only in Phase 3, so the history is the memory record referencing the
entity, closed versions included. `covers` states that scope in words — an
empty list means "nothing recorded", never "nothing happened". The durable
audit log arrives in Phase 4.

---

### `create_waiting_item`

Record that a task is blocked on someone else — a person, organization, or
service that owes a response (BUILD_SPEC section 54).

Call this right after making the request that created the wait (a message
sent, a voicemail left, a form submitted), not before. This records intent
only: it sends nothing and books nothing, and it does **not** move the task's
own state — call `update_task` separately if the task should move to
`WAITING_EXTERNAL`.

| Argument | Type | Default | Notes |
|---|---|---|---|
| `task_id` | string | — | The task this wait blocks |
| `subject` | string | — | What is being waited on, e.g. "Availability quote from ABC Electric" |
| `waiting_on_entity_id` | string? | — | Canonical entity ID; look it up with `find_person`/`get_provider` first |
| `expected_by` | string? | — | RFC 3339, if known |
| `max_followups` | int | `3` | 0–10. Follow-ups beyond this escalate to the user instead of continuing |

```json
{
  "ok": true,
  "waiting_item": {
    "id": "waiting_01j...",
    "task_id": "task_01j...",
    "subject": "Availability quote from ABC Electric",
    "waiting_on_entity_id": "provider_abc_electric",
    "waiting_since": "2026-08-17T16:00:00Z",
    "expected_by": null,
    "next_action_at": "2026-08-18T16:00:00Z",
    "max_followups": 3,
    "status": "waiting"
  }
}
```

---

### `update_task`

Change an existing task's title, description, priority, due date, owner, or
`current_action` note, and/or move it to a new state. Only the fields set are
changed. Not for creating a task — use `create_task`.

| Argument | Type | Default | Notes |
|---|---|---|---|
| `task_id` | string | — | The task to update |
| `title` | string? | — | |
| `description` | string? | — | |
| `state` | enum? | — | Target state; validated by the state machine |
| `priority` | enum? | — | |
| `due_at` | string? | — | RFC 3339 |
| `owner_entity_id` | string? | — | |
| `current_action` | string? | — | e.g. "left voicemail, awaiting callback" |
| `verification_evidence` | string? | — | Confirmation ID / booking reference. Required to move `VERIFYING` → `COMPLETED` on a `verification_required` task |

State changes go through the same table `list_tasks`'s tasks obey (BUILD_SPEC
section 14). An illegal transition — `CAPTURED` straight to `COMPLETED` — is
rejected with `invalid_transition` and nothing is written. Completing a
`verification_required` task without evidence, or from any state but
`VERIFYING`, fails with `verification_required` (section 53).

```json
{
  "ok": true,
  "task": {
    "id": "task_01j...",
    "title": "Call dentist",
    "state": "WAITING_EXTERNAL",
    "priority": "medium",
    "due_at": null,
    "verification_state": "not_required",
    "current_action": "left voicemail, awaiting callback"
  }
}
```

---

## Task states

```
CAPTURED  PLANNED  READY  EXECUTING  WAITING_EXTERNAL
NEEDS_APPROVAL  VERIFYING  COMPLETED  BLOCKED  FAILED  CANCELLED
```

`update_task` drives the transition; `list_tasks` and `create_task` are the
other two tools that touch task state, and the Console's HTTP API exposes the
same machine for the human path.

---

## What is deliberately absent

There is no `run_cypher`, `create_node`, `set_property`, `do_action`,
`browser_action`, or `execute_anything`.

Agents work in human and domain concepts. A raw graph write cannot encode
authorization, state-machine validity, approval requirements, idempotency,
external execution, verification, or audit provenance — and LifeOps Core can. A
generic action tool would move the decision about what is safe from server-side
policy into a model's judgement, which is exactly the wrong place for it.

---

## Phase 7-9 tools

Shipped after the detailed documentation above was written; each follows the
same conventions (structured `{ok: false}` errors, capability checks in
LifeOpsCore, approval gates per BUILD_SPEC section 56). Definitive
descriptions are the tool docstrings in `core/lifeops/mcp/server.py`.

| Area | Tools |
|---|---|
| World reads | `find_person`, `get_provider`, `get_related_entities`, `get_entity_history` |
| World writes (section 51) | `record_provider`, `record_asset` |
| Calendar (Phase 7) | `read_calendar`, `check_calendar_availability`, `create_calendar_hold`, `book_appointment`*, `cancel_appointment`* |
| Email (Phase 7) | `search_email`, `read_email_thread`, `send_email`* |
| Service requests (Phase 8) | `create_service_request`, `get_service_request`, `place_phone_call`*, `request_quote`*, `book_service_request`* |
| Shopping (Phase 9) | `search_shopping`, `create_shopping_list`, `build_grocery_cart`*, `apply_substitution`, `submit_grocery_order`* |
| Self-configuration (Phase 11) | `request_code_change` — files a section-74 Code Change Request for a coding agent; changes nothing itself |

Tools marked * prepare an Action in the outbox; anything with real
consequence still waits for a human's approval in the Console before it
executes (sections 56-58).

Still absent on purpose: `prepare_payment` / `commit_payment` have no MCP
tool — `FINANCIAL_PAYMENT` is Console-only, stricter than the spec requires
(see CLAUDE.md), so no model holds a path to a payment. Approving, executing,
and independently verifying actions are also Console/HTTP operations, never
agent tools.
