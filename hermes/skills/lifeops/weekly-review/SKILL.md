---
name: lifeops-weekly-review
description: A longer, reflective pass over the week just finished and the week ahead — completed work, tasks going stale, long-running waiting items, and what's on the calendar next. Triggered weekly on a schedule or on request.
version: 0.1.0
author: LifeOps
license: MIT
metadata:
  hermes:
    tags: [lifeops, review, scheduled]
    requires_toolsets: [lifeops]
    requires_tools:
      - list_tasks
      - list_appointments
      - list_bills
    related_skills:
      - lifeops-personal-core
      - lifeops-daily-brief
      - lifeops-waiting-for-manager
    blueprint:
      schedule: "Weekly, day/time is the user's choice — ask once, remember
        the answer as a preference, do not assume a default."
---

# Purpose

`lifeops-daily-brief` answers "what does today hold"; this answers "how is
the week actually going" — a slower pass that surfaces what a daily brief's
narrow window would miss: tasks that have been open a while without
movement, waiting items that have gone quiet longer than they should have,
and what the coming week looks like before it arrives.

# Trigger

- A weekly scheduled routine (day/time set by the user, not assumed).
- On request: "weekly review", "how's the week looking", "what am I behind
  on".

# Relevant LifeOps State

- `list_tasks` across all open states, not just due/overdue — this is the
  one skill that should look at the *whole* open task list, since its job
  is exactly to catch what a narrower due-date filter misses.
- `lifeops://waiting` for everything currently blocked on someone else.
- `list_appointments` for the coming week, not just today.
- `list_bills` (`due`, `scheduled`) for what's coming up financially, not
  only what's already overdue.

# Allowed Tools

`list_tasks`, `list_appointments`, `list_bills`, plus
`lifeops-personal-core`'s baseline.

# Procedure

1. Pull the full open task list (`list_tasks`, no state filter beyond
   excluding terminal states).
2. Identify tasks with no recent movement — LifeOps tracks `updated_at` on
   every task; anything untouched noticeably longer than the rest is worth
   naming specifically, not just counting.
3. Pull `lifeops://waiting` and flag any item whose `waiting_since` is old
   relative to its own follow-up cadence — the due-work worker already
   escalates these server-side (BUILD_SPEC section 54's widening backoff),
   so this skill is surfacing them for the user's awareness, not replacing
   that mechanism.
4. Pull the coming week's appointments and upcoming/scheduled bills.
5. Compose as a short retrospective-plus-lookahead, not a repeat of the
   daily brief's format:
   1. **Stuck** — tasks and waiting items with no recent movement, named
      specifically.
   2. **Coming up** — the week ahead's appointments and bills.
   3. **Anything worth deciding now** — e.g. a task that's been stuck long
      enough that it may no longer be worth pursuing; surface it as a
      question ("is this still something you want done?"), never silently
      close it — closing a task is the user's call, not this skill's.

# Approval Boundary

Read-only, same as `lifeops-daily-brief`. If a stuck task turns out to be
one the user wants abandoned, use `update_task` to transition it —
`update_task` is a normal capability Hermes holds, not something needing
Console approval, since cancelling your own task carries no external
commitment.

# Failure Handling

Same as `lifeops-daily-brief`: report a missing section by name rather than
failing the whole review over one unconfigured provider.

# Waiting/Follow-Up Behavior

Surfaces stale waiting items; does not itself log a follow-up — that stays
`lifeops-waiting-for-manager`'s job, called separately if the review
surfaces one that needs an immediate nudge.

# Verification

Not applicable — read-only, except for the rare `update_task` the user
explicitly asks for while reviewing, which needs no separate verification
step (task state changes are local, not an external commitment).

# Completion Criteria

The review is delivered. Any task state change made during it was an
explicit response to something the user said in the moment, not something
this skill decided on its own.
