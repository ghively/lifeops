---
name: lifeops-calendar-manager
description: Read the calendar and answer questions about it — what's on it, when's free. Read-only; booking, holding, or cancelling anything is lifeops-appointment-manager's job, not this one's.
version: 0.1.0
author: LifeOps
license: MIT
metadata:
  hermes:
    tags: [lifeops, calendar, read-only]
    requires_toolsets: [lifeops]
    requires_tools:
      - read_calendar
      - check_calendar_availability
    related_skills:
      - lifeops-personal-core
      - lifeops-appointment-manager
      - lifeops-daily-brief
---

# Purpose

Answer questions about the calendar — "what do I have on Thursday," "am I
free next Tuesday afternoon" — without touching it. This skill exists
specifically so a read never gets tangled with a write: everything here is
BUILD_SPEC section 63 steps 1-2 only (read, then free/busy); step 3 onward
(hold, book) belongs to `lifeops-appointment-manager`.

# Trigger

The user asks what's on the calendar, or whether a time is free, without
(yet) asking to book anything.

# Relevant LifeOps State

- `read_calendar` — everything on the calendar in a given window, LifeOps's
  own copy synced from the provider.
- `check_calendar_availability` — free/busy for a window, when the question
  is "am I free" rather than "what's on it."

# Allowed Tools

`read_calendar`, `check_calendar_availability`. Nothing else — if the
conversation turns from "what's free" to "book that time," hand off to
`lifeops-appointment-manager` rather than reaching for a write tool this
skill doesn't have.

# Procedure

1. For "what's on my calendar" questions, `read_calendar` over the
   relevant window and report what's there plainly — subject, time,
   location if set.
2. For "am I free" questions, `check_calendar_availability` over the
   window and answer directly (free / busy / partially free), citing what
   occupies the busy portions if that's useful context.
3. If the user's next request is to hold or book something, say so and
   route to `lifeops-appointment-manager` rather than trying to do it here
   — this skill has no hold/book tool available to it on purpose.

# Approval Boundary

Fully read-only. Nothing here needs approval because nothing here writes
anything.

# Failure Handling

If the calendar provider isn't configured, say that plainly rather than
reporting an empty calendar as if it were accurate — an unconfigured
calendar and an empty one look the same in a naive read, and they are not
the same fact.

# Waiting/Follow-Up Behavior

Not applicable — this skill never creates a commitment that could need
following up on.

# Verification

Not applicable — read-only.

# Completion Criteria

The question about the calendar is answered. If it turns into a booking
request, that request is *handed off*, not completed here.
