---
name: lifeops-provider-manager
description: Find or record a provider, open a service request, and contact the provider by phone with a constrained objective — never able to authorize a charge or repair work, no matter what's said on the call.
version: 0.1.0
author: LifeOps
license: MIT
metadata:
  hermes:
    tags: [lifeops, providers, telephony]
    requires_toolsets: [lifeops]
    requires_tools:
      - find_provider
      - get_provider
      - record_provider
      - create_service_request
      - get_service_request
      - place_phone_call
      - request_quote
      - book_service_request
    related_skills:
      - lifeops-personal-core
      - lifeops-waiting-for-manager
      - lifeops-appointment-manager
---

# Purpose

Get a real-world job done through a provider — an electrician, an insurer, a
garage — following BUILD_SPEC section 101's shape: find or record the
provider, open a service request, contact them with a narrow, constrained
objective, and let the outcome (connected or not, what was learned) drive
what happens next.

# Trigger

The user names something that needs an outside provider — "call the
electrician about the outlet," "find out if the garage can look at the car
this week," "get a quote for the water heater."

# Relevant LifeOps State

- `find_provider` — check whether a matching provider already exists before
  recording a new one; recording a duplicate splits the provider's history
  across two records.
- `get_service_request` — the current state of any service request already
  open for this job, before opening a second one for the same thing.

# Allowed Tools

`find_provider`, `get_provider`, `record_provider`, `create_service_request`,
`get_service_request`, `place_phone_call`, `request_quote`,
`book_service_request`.

# Procedure

1. **Find or record the provider.** `find_provider` first. Only
   `record_provider` if nothing matches — and even then, only with facts
   actually known (a phone number, a trade), never invented ones.
2. **Open the service request** (`create_service_request`) if one doesn't
   already exist for this job — identify the relevant asset first if there
   is one (the outlet, the water heater), per section 101 step 1.
3. **Contact the provider** with `place_phone_call`, giving it a specific,
   narrow objective (e.g. `"schedule_electrician"`) and exactly the facts
   to collect (`["availability", "diagnostic_fee"]` — only what's actually
   needed, since the call's structured result only returns what was asked
   for).
4. **The call's authority is fixed, not something this skill can widen.**
   `place_phone_call` builds its objective through
   `build_call_objective`/`build_objective`, which has no parameter for
   authorizing a charge or repair work — there is no way to make a call
   that can agree to spend money or approve work, on this call or any
   other. If a provider needs a yes on cost or repairs during the call,
   the answer is "let me get back to you," and that becomes a follow-up
   (`lifeops-waiting-for-manager`), not something this call can settle.
5. **Act on the structured result** (`connected`, `objective_met`,
   `availability`, `diagnostic_fee`) — not on the transcript. If the call
   didn't connect or didn't get an answer, this is exactly
   `lifeops-waiting-for-manager`'s trigger.
6. **Booking** (`book_service_request` / scheduling an appointment) hands
   off to `lifeops-appointment-manager` once a time is actually agreed —
   this skill's job ends at "we know what's available," not at "it's
   booked."

# Approval Boundary

Placing the call itself needs no approval (`PLACE_PHONE_CALL` is R2,
policy-controlled, not gated — Hermes places it on its own, per section
101). Nothing that follows from the call — booking a slot, paying a
diagnostic fee — can be approved by this skill or by anything said on the
call; booking routes through `lifeops-appointment-manager`'s
approval-gated flow, and payment is Console-only, always.

# Failure Handling

If telephony isn't configured, or the call doesn't connect, don't retry
blindly — record the block via `lifeops-waiting-for-manager` and consider
whether email (`lifeops-email-triage`) reaches this provider instead. A
call that connects but can't be held as a real conversation (no ASR/TTS
available yet in this deployment) is the same outcome as one that didn't
connect: nothing was learned, so treat it as needing a follow-up, not as
a completed contact.

# Waiting/Follow-Up Behavior

A call that didn't connect, or connected without a usable answer
(`follow_up_required`), goes straight to `lifeops-waiting-for-manager` —
see BUILD_SPEC section 101 step 8. Don't leave the service request
sitting silently in "contacting provider" with nothing tracking it.

# Verification

The call's own structured result (`CallResult`) is itself the record of
what happened — section 69's "do not rely only on transcript." No separate
verification step exists for a phone call the way booking has one; what
the provider said on the call is evidence to act on, at the authority
limits above, not proof of anything beyond what they said.

# Completion Criteria

The provider is contacted and the outcome (an answer, or a recorded wait)
is reflected in LifeOps — never "the user was told it's handled" without
LifeOps itself showing that state.
