---
name: lifeops-shopping-manager
description: Run a grocery or shopping errand through LifeOps's narrow shopping tools — search, build a cart, handle substitutions, and get checkout approved — never by browsing or reasoning over a live store page directly.
version: 0.1.0
author: LifeOps
license: MIT
metadata:
  hermes:
    tags: [lifeops, shopping, browser]
    requires_toolsets: [lifeops]
    requires_tools:
      - search_shopping
      - create_shopping_list
      - build_grocery_cart
      - apply_substitution
      - submit_grocery_order
    related_skills:
      - lifeops-personal-core
      - lifeops-waiting-for-manager
---

# Purpose

Get groceries or a shopping list actually bought through LifeOps's site-adapter
browser worker (BUILD_SPEC section 98), without ever putting a live store
page's content — or a payment decision — directly in front of this skill's own
reasoning. Every step here is a named LifeOps operation with a fixed,
structured result; there is no "look at the page and decide" step, on purpose.

# Trigger

The user asks for something to be bought or a shopping list to be run — "order
the usual groceries," "add milk and eggs to the list and check out," "see if
the pharmacy has X in stock."

# Relevant LifeOps State

- Which store `search_shopping`/`create_shopping_list` should target — ask if
  the user hasn't said, rather than guessing a store LifeOps has no adapter
  for.
- Whether a shopping list already exists for this errand
  (`lifeops://entity/{id}` for a list this skill already created, or the
  household's world state) before opening a duplicate one.

# Allowed Tools

`search_shopping`, `create_shopping_list`, `build_grocery_cart`,
`apply_substitution`, `submit_grocery_order`. Nothing here ever calls a
browser, a site, or a payment method directly — those live behind the tools,
in the site adapter and the outbox, not in this skill.

# Procedure

1. **Search first if the exact items aren't already known**
   (`search_shopping`), so the list is built from what a store actually
   carries rather than a name Hermes invented. This step is read-only and
   never touches a cart.
2. **Open the list** (`create_shopping_list`) with the items and the target
   `store`. This only records intent — nothing is reserved or bought yet.
3. **Build the cart** (`build_grocery_cart`). This is reversible and commits
   nothing (BUILD_SPEC section 56: R1), so it runs immediately with no
   approval — but it can still fail or come back with items the store
   couldn't fulfill. Never tell the user anything was purchased at this step.
4. **Handle unavailable items through `apply_substitution`**, one named item
   at a time, with a `reason` — never by silently dropping an item or
   inventing a replacement the human never saw. If checkout is already
   awaiting approval when a substitution lands, the approval no longer
   covers the new cart (section 57) and a fresh one is required — that is
   expected, not a bug to work around.
5. **Submit for checkout** (`submit_grocery_order`) only once the cart is
   built and, if the household expects it, the user has confirmed the
   contents. This only *prepares* an Action; it does not place the order.
   Checkout is always approval-gated (BUILD_SPEC section 70: exact total,
   exact merchant, shown before a human approves) — the Console is where
   that approval happens, not this skill.
6. **Never invent a site adapter or fall back to raw browsing.** If
   `search_shopping`/`build_grocery_cart` fail because no site automation
   exists for the requested store, that is the honest answer — report it and
   suggest a store LifeOps can actually drive, rather than trying to browse
   the site directly from this skill's own reasoning.

# Approval Boundary

`build_grocery_cart` needs no approval — a cart is reversible and commits
nothing. `submit_grocery_order` always requires Console approval before it
executes, with no exception for a "usual" or "small" order (BUILD_SPEC
section 70). This skill has no path to approve its own checkout, and none
should ever be added — that is exactly the model-approves-itself gap
`APPROVE_ACTION` being Console-only exists to close.

# Failure Handling

A failed `build_grocery_cart` (no site adapter, or the store's automation
failed outright) ends this run at "could not build a cart" — report it and
stop, rather than retrying blindly or trying an unapproved workaround. A
declined or expired checkout approval leaves the cart intact
(`cancel_submission`'s state, not a lost list): the list can be resubmitted
once the user says to, but this skill does not resubmit on its own.

# Waiting/Follow-Up Behavior

A checkout awaiting Console approval is exactly `lifeops-waiting-for-manager`'s
trigger — record it so the household can see what is pending rather than
leaving the list silently in `submitting`.

# Verification

Neither `build_grocery_cart` nor `submit_grocery_order` is this skill's own
verification step — LifeOps independently re-checks each executed Action
against the store before marking a cart built or an order verified (BUILD_SPEC
section 6: an accepted request is a claim, not evidence). This skill has no
tool to force or skip that check; it only means never telling the user
something was bought, or a cart is ready, from having called the tool alone —
read the returned Action's status, and treat anything short of a verified cart
or order as not yet real.

# Completion Criteria

The shopping list reflects LifeOps's own state — `verified` once the order is
independently confirmed placed, or a recorded wait if it is not — never "the
user was told it's ordered" without LifeOps itself showing that state.
