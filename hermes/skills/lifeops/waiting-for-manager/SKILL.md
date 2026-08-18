---
name: lifeops-waiting-for-manager
description: Record when a task becomes blocked on someone outside LifeOps, and check what's overdue for a nudge. LifeOps's own due-work worker owns the follow-up cadence and escalation — this skill creates and reads waiting items, it does not reimplement the backoff logic.
version: 0.1.0
author: LifeOps
license: MIT
metadata:
  hermes:
    tags: [lifeops, waiting, follow-up]
    requires_toolsets: [lifeops]
    requires_tools:
      - create_waiting_item
      - list_waiting_items
      - update_task
    related_skills:
      - lifeops-personal-core
      - lifeops-provider-manager
      - lifeops-daily-brief
---

# Purpose

Nothing that's blocked on another person should just live in conversation
memory, where it's forgotten the moment the session ends. This skill is the
one place a task's "waiting on someone else" state gets recorded as a
durable WaitingItem, and the one place Hermes checks what's gone quiet long
enough to deserve another nudge.

# Trigger

- A task becomes blocked on an external party — a provider hasn't
  responded, an email is awaiting a reply, a call ended with "we'll get
  back to you."
- Periodically (or when `lifeops-daily-brief`/`lifeops-weekly-review`
  surfaces one), check `list_waiting_items` for anything that looks overdue
  for a follow-up.

# Relevant LifeOps State

- `list_waiting_items` — every currently-open WaitingItem: what's being
  waited on, who from, since when, how many follow-ups have already
  happened.
- The task each waiting item belongs to (`task_id`), if more context is
  needed than the waiting item itself carries.

# Allowed Tools

`create_waiting_item`, `list_waiting_items`, `update_task`. Actually
*performing* a follow-up contact (a call or email) uses
`lifeops-provider-manager`'s or `lifeops-email-triage`'s tools — this skill
owns recording that something is blocked, not the contact itself.

# Procedure

1. **Recording a new wait.** When a task becomes blocked on someone
   outside LifeOps, call `create_waiting_item` with the task id, a clear
   subject, who it's waiting on (a provider entity id if one exists), and
   an `expected_by` if the provider gave one. Do this immediately when the
   block happens — not at the next brief, since the waiting-since timestamp
   should reflect reality.
2. **Checking what's overdue.** Call `list_waiting_items` and look at
   `next_action_at`/`followup_count` against `max_followups`. LifeOps's
   due-work worker already advances these server-side on a widening
   backoff (BUILD_SPEC section 54) — this skill does not recompute that
   cadence, it reads what LifeOps has already decided is due.
3. **Acting on an overdue item.** There is no MCP tool that "logs a
   follow-up" by itself — the actual follow-up *is* taking the next real
   action (calling again via `lifeops-provider-manager`, emailing again via
   `lifeops-email-triage`). Do the real contact; LifeOps's own audit trail
   records that it happened.
4. **Escalation and resolution are Console acts**, not something this
   skill does. An item that's exhausted its follow-ups, or that's now
   unblocked, gets resolved by the user (or an approved action) — not by
   Hermes silently deciding it's done.

# Approval Boundary

Creating and reading waiting items needs no approval — it's record-keeping,
not an external commitment. The follow-up *contact itself* (a call, an
email) carries whatever approval boundary that action type already has
(see `lifeops-provider-manager`/`lifeops-email-triage`); this skill doesn't
change that.

# Failure Handling

If `create_waiting_item` fails, say so and keep the task's actual state in
mind for the rest of the conversation — don't let a failed write become a
task LifeOps and Hermes disagree about.

# Waiting/Follow-Up Behavior

This skill *is* the waiting/follow-up behavior for every other LifeOps
skill — see the Procedure above. It escalates nothing on its own; LifeOps's
due-work worker handles escalation timing, and resolution is the user's
call.

# Verification

Not applicable to recording a wait. A follow-up contact's own verification
(did the call connect, was the email sent) is owned by whichever skill made
that contact.

# Completion Criteria

A wait is recorded, or an overdue one has been acted on with a real
follow-up contact. This skill has no "resolved" state of its own to reach —
resolution happens in the Console.
