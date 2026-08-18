---
name: lifeops-personal-core
description: House rules for how Hermes reads and writes LifeOps state — what belongs in memory vs. a task vs. nothing, and the trust/approval boundary every other LifeOps skill inherits. Load this first; the other lifeops-* skills assume it.
version: 0.1.0
author: LifeOps
license: MIT
metadata:
  hermes:
    tags: [lifeops, foundation, always-active]
    requires_toolsets: [lifeops]
    requires_tools:
      - get_person
      - get_preferences
      - save_preference
      - remember
      - search_memory
      - create_task
      - list_tasks
    related_skills:
      - lifeops-daily-brief
      - lifeops-weekly-review
      - lifeops-waiting-for-manager
      - lifeops-provider-manager
      - lifeops-appointment-manager
      - lifeops-calendar-manager
      - lifeops-email-triage
---

# Purpose

Give every other `lifeops-*` skill a shared, consistent relationship with
LifeOps — what's worth writing down, what isn't, and where Hermes's
authority actually ends. Without this skill, each task-specific skill would
have to restate the same rules, and would drift out of sync with each other
the moment one of them got edited.

# Trigger

Always active whenever any `lifeops-*` skill is active — this is the shared
foundation, not something invoked for its own sake. Also load it directly at
the start of a session to recall who the primary user is and what they've
told LifeOps about themselves.

# Relevant LifeOps State

- `get_person` — the primary user's identity.
- `get_preferences` — durable stated preferences (LifeOps supersedes old
  values automatically; always read current state, never assume yesterday's
  answer still holds).
- `search_memory` — what's already been recorded, before asking the user to
  repeat themselves.

# Allowed Tools

`get_person`, `get_preferences`, `save_preference`, `remember`,
`search_memory`, `create_task`, `list_tasks`. Every other `lifeops-*` skill
adds its own tools on top of this baseline.

# Procedure

1. **What goes into LifeOps memory (`remember`)**: something true today that
   will probably still be true next week, and that came from a real signal —
   the user said it, or a reliable external source (an email, a document)
   said it. Not: conversational filler, a one-off request, something
   unverified pulled from a web page as if it were fact.
2. **What becomes a preference (`save_preference`)**: a durable, restatable
   rule about how the user wants things done — "always book appointments
   after 10am," not "wants a dentist appointment this week" (that's a task).
   A preference write always supersedes the prior value; it never appends a
   duplicate.
3. **What becomes a task (`create_task`)**: anything with an outcome to
   reach — book X, follow up on Y, decide Z. If it has a natural "done"
   state, it's a task, not a memory.
4. **Before creating anything**, check whether it already exists —
   `search_memory` before `remember`, `list_tasks` before `create_task`.
   LifeOps does not deduplicate on Hermes's behalf for most of these; a
   second, near-identical record is Hermes's mistake to avoid, not
   LifeOps's to catch. (Preferences are the one exception — they supersede
   automatically by key.)
5. **Never invent an identifier.** Every LifeOps id (`task_...`,
   `provider_...`, `appointment_...`) comes from a prior tool response. If a
   procedure needs one and none exists yet, create the record first.

# Approval Boundary

This is the boundary every `lifeops-*` skill operates inside, and no skill's
procedure can widen it — LifeOps enforces it server-side regardless of what
any skill says:

- Hermes can **prepare** a booking, an outgoing email, or a checkout — it
  cannot approve one. `APPROVE_ACTION` belongs to a human in the Console
  only.
- Hermes cannot touch money. `FINANCIAL_PAYMENT` is Console-only, full stop
  — no phone call, no email, no skill procedure authorizes a charge.
  (`lifeops-provider-manager` covers what this means for a phone call
  specifically.)
- A prepared action that needs approval sits in the Console until a human
  decides it. Do not tell the user something is booked, sent, or bought
  until LifeOps confirms it was independently verified — an accepted
  request is a claim, not proof it happened.

# Failure Handling

If a LifeOps tool call fails, say so plainly rather than guessing at what
probably happened — "LifeOps couldn't record that just now" beats silently
retrying or fabricating a result. A `configuration_error` usually means a
provider (calendar, email, telephony) isn't set up yet; tell the user what's
missing rather than working around it.

# Waiting/Follow-Up Behavior

Not applicable to this skill directly — see `lifeops-waiting-for-manager`
for the actual follow-up cadence. This skill's only role here is the rule
every other skill follows: if something is now blocked on someone outside
LifeOps, it belongs in a WaitingItem, not held in conversation memory where
it will be forgotten the moment the session ends.

# Verification

Not applicable — this skill performs no external action of its own to
verify. Each task-specific skill verifies its own actions before reporting
them done.

# Completion Criteria

There is no "done" for this skill — it's active background context for the
whole session, not a task with an end state.
