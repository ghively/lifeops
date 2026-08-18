---
name: lifeops-daily-brief
description: Compose a short daily brief from LifeOps state — due/overdue tasks, what's waiting on someone else, pending approvals, today's calendar, and anything owed. Triggered on a schedule or on request ("what's my day look like").
version: 0.1.0
author: LifeOps
license: MIT
metadata:
  hermes:
    tags: [lifeops, brief, scheduled]
    requires_toolsets: [lifeops]
    requires_tools:
      - list_appointments
      - list_bills
      - get_bill
    related_skills:
      - lifeops-personal-core
      - lifeops-weekly-review
      - lifeops-waiting-for-manager
    blueprint:
      schedule: "Not fixed here — set the actual time via a LifeOps Routine
        (the Routines screen, or create_service_request-style workflow
        templates) once the user tells you when they want it. Default to
        asking rather than guessing a time."
---

# Purpose

One short, honest summary of what the day actually holds — not a status
report of everything in LifeOps, just what's relevant to *today*: due,
overdue, waiting on someone else, waiting on the user's own decision, on
the calendar, or coming due financially.

# Trigger

- A scheduled routine (time is the user's choice — see below; do not assume
  a time, ask once and treat the answer as a preference to remember).
- On request: "what's my day look like", "morning brief", "what's up today".

# Relevant LifeOps State

Read the aggregate resources first — they exist precisely so this skill
doesn't reimplement their queries:

- `lifeops://today` — open tasks, the due/overdue subset, current
  preferences.
- `lifeops://waiting` — tasks blocked on someone outside LifeOps.
- `lifeops://approvals` — anything sitting on the user's own decision (a
  prepared booking, an email, a checkout) — these are the one thing
  *only* the user can clear, so they belong at the top of a brief, not
  buried.

Then fill in what those resources don't cover:

- `list_appointments` (status filter: held or booked) for what's actually
  on the calendar today — cross-reference `start_at` against today's date.
- `list_bills` (status: due, overdue) for anything owed — never state an
  amount from memory; always re-read it, since amounts are the one thing a
  brief must get exactly right.

# Allowed Tools

`list_appointments`, `list_bills`, `get_bill`, plus everything
`lifeops-personal-core` already grants (the resources above are read
through the MCP resource interface, not tool calls, but draw on the same
underlying reads).

# Procedure

1. Pull `lifeops://today`, `lifeops://waiting`, and `lifeops://approvals`.
2. Pull `list_appointments`, filtered to today's window client-side (the
   tool itself has no date filter — read broadly, then narrow).
3. Pull `list_bills` filtered to `due`/`overdue`.
4. Compose in this order, and skip a section entirely if it's empty rather
   than saying "nothing here" for every category — an honest brief is
   short on a quiet day:
   1. **Needs your decision** — pending approvals, named plainly (what it
      is, not just "1 approval pending").
   2. **Due or overdue today** — tasks past their `due_at`.
   3. **On the calendar today** — appointments, with time and subject.
   4. **Owed** — due/overdue bills, with the exact amount as LifeOps holds
      it (a validated string, never rounded or reformatted).
   5. **Waiting on someone else** — a one-line count/summary, not the full
      list; `lifeops-waiting-for-manager` owns following up on these, this
      skill just surfaces that they exist.
5. If literally nothing is due, waiting, or owed, say that plainly — a
   quiet day is a real answer, not a reason to pad the brief with
   everything open regardless of urgency.

# Approval Boundary

Read-only. This skill prepares nothing and books nothing — see
`lifeops-personal-core` for the boundary every skill shares.

# Failure Handling

If a read fails (e.g. calendar not configured), say which section is
missing and why, and still deliver the rest of the brief — one provider
being unconfigured must not silently blank out an otherwise-working brief.

# Waiting/Follow-Up Behavior

None initiated here — this skill only surfaces what
`lifeops-waiting-for-manager` is already tracking.

# Verification

Not applicable — no external action taken.

# Completion Criteria

The brief is delivered. Nothing is recorded back into LifeOps as a result
of running this skill — it is a read, not a write.
