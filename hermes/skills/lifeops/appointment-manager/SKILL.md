---
name: lifeops-appointment-manager
description: Hold a calendar slot and book it through LifeOps's approval-gated outbox — a hold is never a booking, and nothing is confirmed to the user until LifeOps has independently verified it happened.
version: 0.1.0
author: LifeOps
license: MIT
metadata:
  hermes:
    tags: [lifeops, calendar, appointments]
    requires_toolsets: [lifeops]
    requires_tools:
      - check_calendar_availability
      - create_calendar_hold
      - book_appointment
      - cancel_appointment
    related_skills:
      - lifeops-personal-core
      - lifeops-calendar-manager
      - lifeops-provider-manager
---

# Purpose

Turn "there's a time that works" into an actual, verified appointment —
following BUILD_SPEC section 63's mandatory order exactly: check
availability, hold, book (through approval), verify. Skipping straight to a
hold-as-if-booked, or reporting a booking before it's verified, is the one
mistake this skill exists to prevent.

# Trigger

A time needs to go on the calendar — following up from
`lifeops-provider-manager` once a provider has given availability, or
directly when the user names a time themselves ("book the dentist for
Tuesday at 2").

# Relevant LifeOps State

- `check_calendar_availability` — read before ever proposing or holding a
  time; never assume a slot is open.
- The appointment's own state once held — `HELD` vs `BOOKED` vs
  `CANCELLED` — since only `HELD` can be booked, and a booking action
  refuses anything else.

# Allowed Tools

`check_calendar_availability`, `create_calendar_hold`, `book_appointment`,
`cancel_appointment`.

# Procedure

1. **Check availability first**, always — `check_calendar_availability`
   before proposing or holding anything.
2. **Hold the time** (`create_calendar_hold`). A hold is reversible and
   commits nothing — it is not a booking, and must never be described to
   the user as one. Holds expire; don't sit on one indefinitely before
   booking or the slot may need to be re-held.
3. **Book it** (`book_appointment`, referencing the held appointment's id).
   This only *prepares* an action — BUILD_SPEC sections 57-58 put a human
   approval between preparing and it actually happening. Tell the user
   it's pending approval, not that it's booked.
4. **Do not report success from the booking call.** `book_appointment`
   returns a prepared action, not a confirmed one. The appointment stays
   `HELD` until LifeOps has committed the action, called the calendar
   provider, and independently re-read the calendar to confirm the event
   is really there — only then does it become `BOOKED`. There is no MCP
   tool for checking that verification state directly; if asked, say the
   booking is pending until the Console/Activity shows it verified.
5. **Cancelling** an appointment (`cancel_appointment`) follows the same
   shape — it prepares an action, a human approves it, LifeOps confirms
   the cancellation actually happened before local state changes.

# Approval Boundary

`book_appointment` and `cancel_appointment` both prepare an action Hermes
cannot approve itself — `APPROVE_ACTION` is Console-only. Creating a hold
needs no approval; it's reversible and external-effect-free on LifeOps's
side (though it does place a real hold with the calendar provider, which is
why it's not free of *all* consequence — don't hold times casually).

# Failure Handling

If the calendar provider isn't configured, say so rather than pretending a
hold succeeded. If a hold expires before it's booked, say that plainly and
re-check availability rather than trying to book an expired hold (LifeOps
refuses it anyway).

# Waiting/Follow-Up Behavior

Not typically applicable — booking is usually fast once a human approves.
If an approval sits unaddressed long enough that it's worth a nudge, that's
`lifeops-daily-brief`'s "needs your decision" section surfacing it, not a
WaitingItem (a WaitingItem is for something blocked on someone *outside*
LifeOps, not on the user's own pending approval).

# Verification

This is the one place independent verification is the whole point: never
tell the user "you're booked" from the prepare or execute step alone —
only once LifeOps's own re-read of the calendar confirms the event exists
(section 6: an accepted request is a claim, not a fact).

# Completion Criteria

The appointment shows `BOOKED` (or `CANCELLED`, for a cancellation) in
LifeOps — not merely "approved" or "executed." Report the outcome using
LifeOps's own state, not an assumption about what should have happened by
now.
