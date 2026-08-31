# Cross-repo contamination: `lifeops` ↔ `grocery-build`

**Date:** 2026-08-31 · **Scope:** `ghively/lifeops`, `ghively/grocery-build`
**Reported symptom:** "Hermes keeps swapping back and forth and trying to do my
grocery shopping."

This is a cross-repository finding. An identical copy lives in both repos at
`docs/audits/2026-08-31-hermes-repo-contamination.md` so either tree's reader
finds it.

---

## 1. The pattern

There are **two complete, independent, mutually contradictory grocery-shopping
systems loaded into one Hermes agent on `gh-ai`**, and neither repository
contains a single reference to the other. `grep -ril lifeops grocery-build`
returns nothing; `grep -ril grocery-build lifeops` returns nothing.

|                    | `lifeops`                                                                                                    | `grocery-build`                                                                     |
| ------------------ | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------- |
| Hermes entry point | `lifeops-shopping-manager` skill → LifeOps MCP (`hermes-personal`, 52 tools)                                 | `grocery-deal-playbook` + `grocery-browser-lane` skills                               |
| Core doctrine      | "**never** by browsing or reasoning over a live store page directly"                                         | "reads visible rendered DOM, clicks normal controls"                                  |
| Mechanism          | `search_shopping`, `create_shopping_list`, `build_grocery_cart`, `apply_substitution`, `submit_grocery_order` | `browser_exec` (Lane A) / `grocery/browser.py` CDP (Lane B)                            |
| Stores             | **Amazon, Instacart only** (`browser/sites/__init__.py:SITE_ADAPTERS`)                                       | **Kroger, Walmart, Publix** — plus `amazon` in `config/attended-surfaces.yaml`         |
| Checkout           | approval-gated Action; Console-only approval; `submit_order` deliberately raises                             | "STOP before checkout"; human clicks                                                  |
| Scheduler          | `cron_job` / `routine_template` via `propose_self_change`, `due_routines`                                    | Hermes native cron `7f6a2acf57fd`                                                     |
| Repo agent rules   | 23 KB `CLAUDE.md` + `AGENTS.md`                                                                              | **none**                                                                              |

Both skills' `description:` fields match the same plain-English trigger:

- lifeops — *"Run a grocery or shopping errand … search, build a cart, handle
  substitutions, and get checkout approved"*
- grocery-build — *"Use when hunting grocery deals or planning meals for Gene"*

### The deterministic dead end

"Order the groceries" resolves to a coin flip, and **neither branch can finish**:

- **Routes to lifeops** → store is Kroger → `build_grocery_cart` →
  `browser/real.py:246` `store not in _SITE_ADAPTERS` →
  `_no_site_adapter_error("kroger")`. The skill's own step 6 then says report
  honestly and *"suggest a store LifeOps can actually drive"* — Amazon or
  Instacart, which is not where the household shops.
- **Routes to grocery-build** → `browser_exec` against Kroger → pace-hook block
  or a live soft-throttle → the operator boundary says STOP, preserve evidence,
  never retry.

Next trigger, coin flip again. That alternation *is* the swapping. It is not a
bug in either repo — each is internally coherent. It is the absence of any
statement, in either tree, of which system owns which store.

---

## 2. What changed (the 2026-08-30 → 08-31 session)

Reconstructed from `grocery-build/docs/runs/20260830_142655_01b58869-*.md`
(367 KB, 258 messages), the three cron outputs, and the commit log.
Session stamps are UTC; cron stamps are local (−05:00) — the two are mixed in
the artifacts, which is itself part of why this reads as chaos.

| When (UTC)    | What                                                                                                                                                                    |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 08-31 00:31   | Grocery v3.1 mission closes. Agent asks: cron `7f6a2acf57fd` is paused — resume or leave parked?                                                                         |
| **08-31 00:35** | User: *"Run it now."* Agent: *"Paused job refused the manual run — resuming it first … that also re-arms the weekly schedule."* **A one-off became a standing job.**   |
| 08-30 19:37 / 19:58 / 20:32 (local) | Cron fires **three times**, on a **Sunday**, on a `0 8 * * 3` (Wednesday 08:00) schedule.                                                        |
| 08-31 01:05   | User asks for v3.2: empty cart first, dynamic meal plan, total saved, cart link.                                                                                         |
| 08-31 01:08–01:41 | Cart-empty attempted **three times**; reported "Cart emptied — all 78 active rows" on the first, which had not worked (9 rows survived, found at 01:36).             |
| 08-31 01:44   | 19 rapid Kroger searches → soft throttle → run stopped half-assembled at 9 items.                                                                                        |
| 08-31 02:20   | User: *"I gave you a directive … to emulate a human shopper. Why didn't you listen."*                                                                                    |
| 08-31 02:22–02:39 | `retailer-pace-hook.sh` written and wired as a **global Hermes `pre_tool_call` hook**; ADR-0007; transcript + docs pushed (`90d3d0b`, `4029968`, `2b56f3d`).         |

**The single change most responsible for the symptom is 00:35.** "Run it now"
was silently upgraded to "resume the weekly schedule." Nothing in either repo
records the resume — both skills still say the cron is PAUSED.

`lifeops` has not been touched since 2026-08-20. All motion is on the
grocery side; the collision is in the shared Hermes runtime, not in either
codebase's history.

---

## 3. Findings

### A. The cron is armed; every document says it is paused — **P0**

Both skills state: *"cron 7f6a2acf57fd, Wed 08:00 — **PAUSED** for v3.1
review/QA … Gene re-enables after reviewer and QA pass."* It was re-armed at
08-31 00:35 UTC. Next fire: Wednesday 2026-09-02 08:00. No commit records this.

### B. Each cron firing impersonates the user — **P0**

Every cron output begins:

```
[IMPORTANT: The user has invoked the "grocery-deal-playbook" skill,
indicating they want you to follow its instructions.]
```

The agent has no way to tell a scheduled sweep from Gene asking. Combined
with the v3.2 text — *"This is authorized standing instruction from Gene
(2026-08-30) — not a per-run ask"* for emptying the cart — a scheduled job
now carries a pre-granted standing authorization to mutate the live cart.

### C. Both grocery skills have broken YAML frontmatter — **P1**

In `skills/grocery-deal-playbook.md` and `skills/grocery-browser-lane.md` the
frontmatter fence closes at line 5, and then this sits in the **markdown body**:

```
metadata:
hermes:
requires_toolsets: - file - session_search - web
```

Un-nested, outside the fence. `metadata.hermes.requires_toolsets` is therefore
never parsed — **toolset gating is silently off on both skills**. Contrast
`lifeops/hermes/skills/lifeops/shopping-manager/SKILL.md`, where `metadata:` is
correctly nested inside the fence.

The regression is datable: the cron echo at 19:58 shows correct nesting; the
one at 20:32 shows the flattened form. The live→repo `skill-repo-sync` pass in
between is the likely flattener, and it propagated to the repo *and* to the
agent-marketplace catalog backup.

### D. The pace hook does not cover the paths that matter — **P1**

`scripts/retailer-pace-hook.sh`:

- Matcher is `kroger|walmart|publix|aldi|costco|target\.com` — **no `amazon`,
  no `instacart`**. Amazon appears in grocery-build's own
  `config/attended-surfaces.yaml` *and* is a LifeOps `SITE_ADAPTERS` key. The
  one store both systems drive is the one store the hook ignores.
- It reads only `.tool_input.code`, and empty → pass. LifeOps MCP calls
  (`build_grocery_cart`) carry no `code` field, so **the entire LifeOps
  shopping path bypasses the hook.** ADR-0007's "known gaps" notes the matcher
  reads the code body but concludes other paths "are already banned by
  ADR 0004" — that reasoning holds only inside grocery-build. It does not
  bind LifeOps, which the ADR never considered.
- `MIN_GAP_S` defaults to **20 s**; the doctrine it exists to enforce says
  **25–30 s**. The mechanism is looser than the rule, in two places, and
  ADR-0007 records 20 without flagging the mismatch.
- State is one flat global list in `/tmp/retailer-pace-state.json`, despite the
  header comment claiming "per retailer host" — a Walmart call throttles a
  Kroger call, and `/tmp` loses the state on reboot.
- Fail-open by design (documented): a `jq`/`python3` hiccup silently disables it.

### E. A real CDP collision hazard — **P1 (latent)**

`core/lifeops/browser/real.py:174,189` calls
`playwright.chromium.connect_over_cdp(self._endpoint)`, and
`config/provider_registry.py:362` gives that field the placeholder
`ws://127.0.0.1:9222`. grocery-build's ADR-0005 documents 9222 as the *local
datacenter* Chrome (Akamai-denied; the source of the 08-30 false-block
misdiagnosis) and 9223 as the tunnel to gh-media's residential headed Chrome.

If that field is ever set to 9223, LifeOps' Playwright drives the same headed
Chrome the grocery operator lane owns — unpaced (see D), uncoordinated, against
the household's logged-in retailer sessions, violating grocery-build's "one
browser session at a time" rule from outside grocery-build's reach. The only
thing preventing this today is that the browser provider is disabled.

### F. The cart audit trail is not trustworthy — **P1**

- `data/cart-last.json`: `"emptied_at": "2026-08-30T20:31:00-05:00"`,
  `"active_items": 0`. The transcript shows the cart still held 9 leftover rows
  at ~20:36 and only truly emptied at ~20:41. The recorded empty is the
  **failed** one, never corrected.
- `data/cart-add-log.jsonl`: `{"action":"empty","items_moved":78}` — on a cart
  of 32 items, followed by a later pass of 91 more clicks. 78 is recorded as one
  successful atomic empty.
- The `added-verified` entries at 17:10–17:19 are each exactly 60 s apart on
  round `:00` seconds — backfilled, not measured. The actual run was ~7 s
  apart. **The log you would use to audit pace compliance contains no real pace
  data.**
- A `correction` entry stamped 17:20 sits *above* entries stamped 17:10–17:19.

### G. Two schedulers reachable by one agent — **P2**

Hermes' native cron (`cronjob`) plus LifeOps' `cron_job` / `routine_template`
kinds via `propose_self_change` and `due_routines`
(`core/lifeops/mcp/server.py:2071,2187`). `lifeops/CLAUDE.md` claims it avoided
"inventing a second scheduler (section 55)" — true inside lifeops, false from
the agent's seat, which can now file a recurring grocery routine into either
with no arbitration between them.

### H. No repo-scoped agent rules in grocery-build — **P2**

grocery-build has no `CLAUDE.md` and no `AGENTS.md`. lifeops has a 23 KB
`CLAUDE.md` written in absolute voice — *"Hermes is the assistant. Do not build
a second agent."*, *"NornicDB is the only application database."* With both
trees open to one agent, lifeops' rules read as global while grocery-build
asserts no boundary of its own.

### I. Data-hygiene divergence — **P2**

lifeops scrubbed real names, hosts, and network topology on 2026-08-20
(`38191ec`, `514ff9f`). grocery-build carries, pushed to GitHub: the delivery
address `103 Willis Dr`, Kroger store id `02600571`, `gh-ai` / `gh-media`,
`git.example.com`, real household names, and a 367 KB session transcript
including cart contents and subtotals. Same operator, same host, opposite
policy.

### J. Operator identity drift — **P3**

`cart-last.json` and `cart-add-log.jsonl` attribute the cart empty to
`"GregoryCloud"` / `"GregoryCloud-attended"`, while every skill and document
names the operator "Gene". The audit trail carries two names for the
accountable human.

---

## 4. Recommended order of work

1. **Confirm the cron's real state**, then either re-pause it or correct both
   skills. Smallest change, highest value — it is the thing firing unbidden.
   (A)
2. **Repair the frontmatter** on both grocery skills, and check whether the
   agent-marketplace catalog copy took the same corruption. (C)
3. **Give the two systems one front door.** Cheapest correct version: scope
   `lifeops-shopping-manager`'s `description` explicitly to Amazon/Instacart
   via LifeOps, scope the grocery skills explicitly to Kroger/Walmart/Publix
   via the attended lane, and have each name the other plus the handoff rule.
   This is what kills the coin flip. (§1)
4. **Add `amazon|instacart` to the pace-hook matcher**, and reconcile 20 s vs.
   25–30 s so the number is written once. (D)
5. **Decide who owns Amazon.** One system, not two. (D, E)
6. **Record that LifeOps' browser `endpoint` must never point at 9222/9223**,
   in `CONFIGURATION.md` next to the field. (E)
7. **Stop backfilling `cart-add-log.jsonl`.** Write entries at call time from
   real clock reads, or omit timestamps rather than synthesize them. (F)
8. **Add a `CLAUDE.md` to grocery-build** stating its boundary and that
   lifeops' rules do not govern it. (H)

Items 1–2 are corrections to false statements already in the repos. Items 3–8
are design changes and should be confirmed before implementation.

---

## 5. What this is *not*

- Not a bug in LifeOps' shopping tools. `_no_site_adapter_error("kroger")` is
  correct behaviour — LifeOps genuinely has no Kroger adapter.
- Not a bug in the grocery lane's browser doctrine. The attended-only boundary
  is well reasoned and the 08-30 incident post-mortem is honest about cause.
- Not code sharing between the repos. There is none — that is precisely the
  problem. Two correct systems, one agent, no adjudication.
