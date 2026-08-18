---
name: lifeops-email-triage
description: Sort inbox activity into what needs a reply now versus what can wait, and send replies through LifeOps's approval-gated outbox — never send anything Hermes wasn't explicitly asked to send.
version: 0.1.0
author: LifeOps
license: MIT
metadata:
  hermes:
    tags: [lifeops, email, triage]
    requires_toolsets: [lifeops]
    requires_tools:
      - search_email
      - read_email_thread
      - send_email
    related_skills:
      - lifeops-personal-core
      - lifeops-waiting-for-manager
      - lifeops-provider-manager
      - lifeops-daily-brief
---

# Purpose

Read what's come in, decide what's actually urgent versus what's safe to
batch for later, and — only when the user asks for a reply — prepare one
through LifeOps's normal approval-gated send path. This skill triages and
drafts; it does not decide on its own that something should be sent.

# Trigger

- The user asks what's in the inbox, or whether anything needs attention.
- A `lifeops-provider-manager` or `lifeops-waiting-for-manager` flow needs
  email as the follow-up channel instead of a phone call.
- The user asks to reply to, or send, a specific email.

# Relevant LifeOps State

- `search_email` — find relevant messages/threads by query rather than
  paging through everything.
- `read_email_thread` — the full thread before acting on or summarizing a
  single message out of context; a reply read in isolation can misread the
  thread's actual ask.
- Any open task or service request the thread relates to, so a reply or a
  triage note can be linked back rather than left as an orphaned email.

# Allowed Tools

`search_email`, `read_email_thread`, `send_email`.

# Procedure

1. **Search, don't dump.** Use `search_email` with a query scoped to what's
   being asked ("this week", a sender, a subject) rather than pulling the
   entire inbox every time.
2. **Read the thread before judging it.** `read_email_thread` on anything
   that looks like it needs a decision — a subject line alone is often
   misleading about urgency.
3. **Triage into two buckets**, since no exact urgency rule was specified by
   the user — until tuned otherwise, treat as urgent: anything with an
   explicit deadline in the next few days, anything from a provider or
   party already tied to an open task or service request, and anything that
   reads as time-sensitive on its face (a bill, a cancellation notice, a
   scheduling conflict). Treat as safe to batch: newsletters, receipts with
   no action needed, and threads already resolved. State this split
   explicitly when triaging so the user can correct the boundary.
4. **Link back to LifeOps state.** If a thread relates to an open task or
   service request, say so; if it represents a new piece of follow-up work,
   that's `create_task` or `create_waiting_item` territory
   (`lifeops-personal-core` / `lifeops-waiting-for-manager`), not something
   this skill invents new tools for.
5. **Only draft/send on explicit request.** `send_email` prepares an
   outbound message; do not call it because a thread merely looks like it
   needs a reply. When the user does ask for a reply, confirm the intended
   content maps to what they actually asked for before sending.
6. **Do not report a reply as sent from the prepare step.** Same shape as
   `lifeops-appointment-manager`'s booking flow: `send_email` prepares an
   action, a human approves it, and only LifeOps's own execution record
   confirms it went out.

# Approval Boundary

`send_email` prepares an action Hermes cannot approve itself —
`APPROVE_ACTION` is Console-only, same as every other `SEND_EXTERNAL_MESSAGE`
path. Reading and searching email needs no approval; only the outbound send
does.

# Failure Handling

If email isn't configured, say so rather than reporting an empty inbox as if
it were accurate — an unconfigured mailbox and an empty one look the same in
a naive read. If a send fails after approval, don't assume it went out
partially; check LifeOps's own execution record before telling the user
anything about delivery.

# Waiting/Follow-Up Behavior

A thread that's awaiting a reply from someone else is exactly
`lifeops-waiting-for-manager`'s trigger — record it there rather than
tracking it only as "an email I'm keeping an eye on."

# Verification

Do not tell the user a reply was sent until LifeOps's own execution record
confirms the action completed — the prepared/approved state is not proof it
left the outbox.

# Completion Criteria

The inbox question is answered with the urgent/batch split stated plainly,
or a requested reply shows sent in LifeOps's own record — not merely
approved.
