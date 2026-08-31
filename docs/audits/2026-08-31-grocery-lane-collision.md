# The other shopping system: `grocery-build` collides with LifeOps

**Date:** 2026-08-31 · **Status:** findings only, no behavioural changes
**Trigger:** the user reports Hermes "swapping back and forth" and repeatedly
attempting grocery shopping unbidden.
**Counterpart:** `ghively/grocery-build` ->
`docs/audits/2026-08-31-cross-system-contamination.md`

---

## 1. What this repository does not know

`ghively/grocery-build` contains a second, complete grocery-shopping system,
loaded into the same Hermes agent on the deployment host as
`hermes-personal`'s 52 tools. Neither repo mentions the other — `grep -ril
grocery-build .` here returns nothing, and the reverse grep there returns
nothing.

|                    | LifeOps                                                                       | `grocery-build`                                                               |
| ------------------ | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| Hermes skill       | `lifeops-shopping-manager`                                                    | `grocery-deal-playbook`, `grocery-browser-lane`                               |
| Doctrine           | "**never** by browsing or reasoning over a live store page directly"          | attended lanes; read the visible DOM, click normal controls                   |
| Mechanism          | `search_shopping`, `create_shopping_list`, `build_grocery_cart`, `submit_grocery_order` | `browser_exec` over CDP; a second CDP transport in-repo               |
| Stores             | **Amazon, Instacart** (`browser/sites/__init__.py:SITE_ADAPTERS`)             | Kroger, Walmart, Publix — **plus `amazon`**                                   |
| Checkout           | approval-gated Action; Console-only approval; `submit_order` raises           | STOP before checkout; human clicks                                            |
| Scheduler          | `cron_job` / `routine_template` via `propose_self_change`, `due_routines`     | Hermes' native cron (`7f6a2acf57fd`, weekly)                                  |

Both skills' `description:` fields match the same plain-English request. The
household shops at Kroger. So "order the groceries" routes by coin flip and
**neither branch can complete**:

- **-> LifeOps**: `build_grocery_cart(store="kroger")` -> `browser/real.py:246`
  `store not in _SITE_ADAPTERS` -> `_no_site_adapter_error("kroger")`. The
  skill's step 6 then correctly reports the gap and suggests "a store LifeOps
  can actually drive" — Amazon or Instacart, which is not where this household
  shops.
- **-> `grocery-build`**: `browser_exec` on Kroger -> a live soft-throttle or a
  pace-hook block -> its boundary says STOP, preserve evidence, never retry.

Next request, coin flip again. **That alternation is the reported swapping.**

LifeOps is behaving correctly at every step here. The failure is that nothing
in either repository states which system owns which store, so the agent has no
basis to choose.

---

## 2. Findings for this repository

### A. A CDP endpoint would attach LifeOps to the other lane's browser — **P1, latent**

`core/lifeops/browser/real.py:174,189` calls
`playwright.chromium.connect_over_cdp(self._endpoint)`, and
`core/lifeops/config/provider_registry.py:362` gives that field the
placeholder `ws://127.0.0.1:9222`.

On the deployment host those ports are already spoken for.
`grocery-build`'s ADR-0005 documents 9222 as a *local datacenter* Chrome
(Akamai-denied; the source of a false-block misdiagnosis on 2026-08-30) and
9223 as an SSH tunnel to a residential headed Chrome carrying the household's
logged-in retailer sessions.

Setting `endpoint` to either value points LifeOps' Playwright at a browser
another system owns and paces. The consequences are all outside anything this
repo can see: a violated "one browser session at a time" rule, an unpaced
retailer, and shared cookies in a browser LifeOps did not profile — which
undercuts `separate_contexts` (BUILD_SPEC section 66) at the transport layer,
below where `_open_context`'s per-store profile isolation operates.

The provider is disabled today, which is the only thing preventing this. The
placeholder should not name a port that is live on the host.

### B. LifeOps' shopping path is unpaced against live retailers — **P1**

`grocery-build` deployed a Hermes `pre_tool_call` hook on 2026-08-30
(`retailer-pace-hook.sh`) after rapid searches soft-throttled Kroger. It is a
**host-wide** hook, not a repo-local one — but it does not cover LifeOps:

- It reads `.tool_input.code` and passes immediately when that is empty. A
  LifeOps MCP call (`build_grocery_cart`) carries no `code` field, so **every
  LifeOps shopping call bypasses it.**
- Its domain matcher is `kroger|walmart|publix|aldi|costco|target\.com` —
  **neither `amazon` nor `instacart`**, which are precisely LifeOps' two
  adapters.

Nothing in `browser/real.py` or the site adapters imposes an inter-request
delay of its own. LifeOps' browser worker is therefore the *only* automation
on that host with no pace discipline at all, driving the one store both
systems touch.

### C. Amazon is claimed by two systems — **P1**

`SITE_ADAPTERS["amazon"]` here; `surfaces.amazon` in `grocery-build`'s
`config/attended-surfaces.yaml`. Two automations, two browser profiles, one
household Amazon account, no coordination and no shared pacing. This is the
concrete case where the abstract boundary problem has already materialised.

### D. There are two schedulers from the agent's seat — **P2**

`CLAUDE.md` records, accurately for this repo, that Hermes self-configuration
was wired "without inventing a second scheduler (section 55)" — routine,
cron_job, and reminder all fold into `WorkflowTemplate`. From the agent's
side that is only half the picture: Hermes already has its own native cron,
which is what runs the weekly grocery sweep, and `core/lifeops/mcp/server.py`
(`propose_self_change` kinds at :2071, `due_routines` at :2187) now gives the
same agent a second place to file a recurring job. Nothing arbitrates between
them, and a grocery routine could be written into either.

The claim in `CLAUDE.md` is true as scoped and should stay — it wants one
clause noting that the host has another scheduler LifeOps does not own.

### E. `CLAUDE.md`'s absolute voice reaches beyond this repo — **P2**

This file speaks in unqualified imperatives — *"NornicDB is the only
application database."*, *"Hermes is the assistant. Do not build a second
agent, a voice agent, or an agent runtime."* Within LifeOps that is exactly
right. But `grocery-build` has no `CLAUDE.md` and no `AGENTS.md` at all, so
when both trees are open to one agent these are the only repository rules in
scope, and they read as global. "Do not build a second agent" in particular
sits awkwardly next to a sibling repo whose entire design is an operator lane
driving a browser.

Scoping the preamble ("these rules govern this repository") costs one line and
removes the ambiguity.

### F. The skill's fallback advice is a dead end for this household — **P3**

`lifeops-shopping-manager` step 6 says to "suggest a store LifeOps can
actually drive" when no adapter exists. That is the right instinct and the
right honesty, but on this deployment it resolves to Amazon or Instacart for a
household that shops at Kroger — so the honest answer is also a non-answer,
every time, and the agent's next move is to try the other system. Naming the
handoff explicitly turns a dead end into a routing rule.

---

## 3. Recommendations

Items 1-2 are small and self-contained; 3 onward want a decision first.

1. **Change the browser `endpoint` placeholder** off `ws://127.0.0.1:9222`,
   and note beside the field — in `CONFIGURATION.md` and the provider
   definition — that on this host 9222/9223 belong to another system's Chrome
   and must not be used. Cheapest possible fix for the sharpest latent
   failure. *(A)*
2. **Scope `CLAUDE.md`'s opening imperatives to this repository** with one
   clause. *(E)*
3. **Declare the store boundary in the skill.** Amend
   `lifeops-shopping-manager`'s `description` and step 6: LifeOps owns Amazon
   and Instacart; the `grocery-build` attended lane owns Kroger, Walmart, and
   Publix; when the requested store is one of the latter, hand off rather than
   report a missing adapter. Mirrored in the other skill, this single change is
   what stops the coin flip. *(section 1, F)*
4. **Decide who owns Amazon**, then make the loser's config say so. If LifeOps
   keeps it, `grocery-build`'s pace hook should still cover `amazon` —
   the hook is per-host, not per-repo. *(C)*
5. **Give the browser worker its own inter-request pacing**, independent of any
   host hook. A site adapter that can be told "search" in a loop should not
   depend on an external shell hook — which it cannot trigger anyway — to
   avoid looking like a bot. This is a real gap in `browser/real.py`, not only
   a coordination problem. *(B)*
6. **Add one clause to `CLAUDE.md`'s self-configuration paragraph** noting that
   Hermes' native cron exists alongside `WorkflowTemplate`, so the
   "no second scheduler" claim is not read as covering the host. *(D)*

## 4. What is not wrong here

`_no_site_adapter_error` is correct behaviour, not a bug — LifeOps genuinely
has no Kroger adapter and says so rather than improvising. The narrow-tools
doctrine ("no look at the page and decide step, on purpose"), the Console-only
approval boundary, and `submit_order` deliberately refusing an unrun checkout
flow are all sound, and none of them caused this. What LifeOps lacks is any
statement of where its authority over "shopping" ends — and one live
configuration field that would let its browser reach into another system's
session.
