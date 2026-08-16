# LifeOps MCP API

The portable agent interface. Hermes is the primary consumer; any trusted MCP
client can connect to the same server and operate on the same personal state,
subject to its own permissions.

**Phase 1 exposes five tools and three resources.** The tools are the Phase 0
set (BUILD_SPEC section 49); the resources are the read views of section 48.

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
when. Use it to decide whether to follow up; full waiting items and follow-up
automation arrive in Phase 4.

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

## Task states

```
CAPTURED  PLANNED  READY  EXECUTING  WAITING_EXTERNAL
NEEDS_APPROVAL  VERIFYING  COMPLETED  BLOCKED  FAILED  CANCELLED
```

Phase 0 exposes no transition tool over MCP — `list_tasks` and `create_task`
only. Transitions are available through the Console's HTTP API and arrive on the
MCP surface in Phase 4 alongside waiting items and the due-work worker.

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

## Coming in later phases

| Phase | Additions |
|---|---|
| 2 | `search_memory`, memory write and invalidate |
| 3 | `find_person`, `get_provider`, `get_related_entities`, `get_entity_history` |
| 4 | `update_task`, `create_waiting_item`, `list_waiting_items` |
| 7+ | `send_email`, `book_appointment`, `prepare_payment` / `commit_payment` — each approval-gated per BUILD_SPEC section 56 |
