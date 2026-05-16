# Knowledge OS — End-to-End Suite Report

This file is **regenerated on every run** of `e2e/scripts/run-suite.sh`.
It is the canonical source of "what is broken in the running system" — 
when the user asks about e2e failures, what to fix, or what to look at,
this is the file to read.

- **Started:** 2026-05-15T21:34:09.789Z
- **Duration:** 74.5s
- **Total:** 61 | **Passed:** 57 | **Failed:** 0 | **Flaky:** 0 | **Skipped:** 4
- **Playwright exit code:** 0

## What Needs to Be Fixed

🎉 No failing tests. No punch list this run.
## Per-Spec Breakdown

| Spec | Pass | Fail | Skip | File |
|---|---:|---:|---:|---|
| register and authenticate test user | 1 | 0 | 0 | `../global-setup.spec.ts` |
| login page renders email/password fields and CTA | 1 | 0 | 0 | `00-anonymous/auth.spec.ts` |
| protected route bounces to /login when unauthenticated | 1 | 0 | 0 | `00-anonymous/auth.spec.ts` |
| reset password page is reachable from login | 1 | 0 | 0 | `00-anonymous/auth.spec.ts` |
| register flow accepts a new user (or surfaces a clear duplicate error) | 1 | 0 | 0 | `00-anonymous/auth.spec.ts` |
| app shell loads with the expected title | 1 | 0 | 0 | `00-anonymous/landing.spec.ts` |
| backend /health returns healthy | 1 | 0 | 0 | `00-anonymous/landing.spec.ts` |
| unknown protected route does not throw an uncaught error | 1 | 0 | 0 | `00-anonymous/landing.spec.ts` |
| / renders without uncaught errors | 1 | 0 | 0 | `10-navigation/sidebar.spec.ts` |
| /tasks renders without uncaught errors | 1 | 0 | 0 | `10-navigation/sidebar.spec.ts` |
| /files renders without uncaught errors | 1 | 0 | 0 | `10-navigation/sidebar.spec.ts` |
| /agents renders without uncaught errors | 1 | 0 | 0 | `10-navigation/sidebar.spec.ts` |
| /search renders without uncaught errors | 1 | 0 | 0 | `10-navigation/sidebar.spec.ts` |
| /settings renders without uncaught errors | 1 | 0 | 0 | `10-navigation/sidebar.spec.ts` |
| /logs renders without uncaught errors | 1 | 0 | 0 | `10-navigation/sidebar.spec.ts` |
| sidebar links navigate between pages | 1 | 0 | 0 | `10-navigation/sidebar.spec.ts` |
| renders the editor surface | 1 | 0 | 0 | `20-outliner/outliner.spec.ts` |
| typing into a block does not throw | 1 | 0 | 0 | `20-outliner/outliner.spec.ts` |
| Enter creates a new block (best-effort assertion) | 0 | 0 | 1 | `20-outliner/outliner.spec.ts` |
| renders the tasks page without throwing | 1 | 0 | 0 | `30-tasks/tasks.spec.ts` |
| task creation control is reachable | 1 | 0 | 0 | `30-tasks/tasks.spec.ts` |
| can create a task via the UI (best-effort) | 1 | 0 | 0 | `30-tasks/tasks.spec.ts` |
| task list area is rendered | 1 | 0 | 0 | `30-tasks/tasks.spec.ts` |
| renders without throwing | 4 | 0 | 0 | `40-files/files.spec.ts` |
| upload affordance is present | 1 | 0 | 0 | `40-files/files.spec.ts` |
| upload a small text file (best-effort) | 0 | 0 | 1 | `40-files/files.spec.ts` |
| renders the search input | 1 | 0 | 0 | `50-search/search.spec.ts` |
| submitting a query does not throw | 1 | 0 | 0 | `50-search/search.spec.ts` |
| exposes a way to create or open an agent | 1 | 0 | 0 | `60-agents/agents.spec.ts` |
| agent creation flow is reachable (best-effort) | 1 | 0 | 0 | `60-agents/agents.spec.ts` |
| open agents page and follow the first chat link if present | 0 | 0 | 1 | `61-agent-chat/agent-chat.spec.ts` |
| chat input is interactive | 0 | 0 | 1 | `61-agent-chat/agent-chat.spec.ts` |
| exposes at least one setting control (theme/profile/integration) | 1 | 0 | 0 | `70-settings/settings.spec.ts` |
| toggling theme (if present) does not throw | 1 | 0 | 0 | `70-settings/settings.spec.ts` |
| shows log content area | 1 | 0 | 0 | `80-logs/logs.spec.ts` |
| backend /health is up | 1 | 0 | 0 | `90-api/api-health.spec.ts` |
| OpenAPI is exposed | 1 | 0 | 0 | `90-api/api-health.spec.ts` |
| GET /auth/me responds (auth=true) | 1 | 0 | 0 | `90-api/api-health.spec.ts` |
| GET /objects responds (auth=true) | 1 | 0 | 0 | `90-api/api-health.spec.ts` |
| GET /blocks responds (auth=true) | 1 | 0 | 0 | `90-api/api-health.spec.ts` |
| GET /tasks responds (auth=true) | 1 | 0 | 0 | `90-api/api-health.spec.ts` |
| GET /files responds (auth=true) | 1 | 0 | 0 | `90-api/api-health.spec.ts` |
| GET /search?q=hello responds (auth=true) | 1 | 0 | 0 | `90-api/api-health.spec.ts` |
| GET /agents responds (auth=true) | 1 | 0 | 0 | `90-api/api-health.spec.ts` |
| GET /agents/runtime/sessions responds (auth=true) | 1 | 0 | 0 | `90-api/api-health.spec.ts` |
| GET /system/status responds (auth=true) | 1 | 0 | 0 | `90-api/api-health.spec.ts` |
| GET /relations responds (auth=true) | 1 | 0 | 0 | `90-api/api-health.spec.ts` |
| GET /settings responds (auth=true) | 1 | 0 | 0 | `90-api/api-health.spec.ts` |
| GET /webhooks responds (auth=true) | 1 | 0 | 0 | `90-api/api-health.spec.ts` |
| unauthenticated read of protected endpoint returns 401 | 1 | 0 | 0 | `90-api/api-health.spec.ts` |
| agent_id path-traversal is rejected (regression for the audit fix) | 1 | 0 | 0 | `90-api/api-health.spec.ts` |
| / is free of pageerrors and failed requests | 1 | 0 | 0 | `95-cross/console-errors.spec.ts` |
| /tasks is free of pageerrors and failed requests | 1 | 0 | 0 | `95-cross/console-errors.spec.ts` |
| /files is free of pageerrors and failed requests | 1 | 0 | 0 | `95-cross/console-errors.spec.ts` |
| /agents is free of pageerrors and failed requests | 1 | 0 | 0 | `95-cross/console-errors.spec.ts` |
| /search is free of pageerrors and failed requests | 1 | 0 | 0 | `95-cross/console-errors.spec.ts` |
| /settings is free of pageerrors and failed requests | 1 | 0 | 0 | `95-cross/console-errors.spec.ts` |
| /logs is free of pageerrors and failed requests | 1 | 0 | 0 | `95-cross/console-errors.spec.ts` |

## Skipped (feature not present or precondition not met)

- **no reason given**
  - Enter creates a new block (best-effort assertion) → undefined
  - upload a small text file (best-effort) → undefined
  - open agents page and follow the first chat link if present → undefined
  - chat input is interactive → undefined

---

_Regenerate with `cd e2e && bash scripts/run-suite.sh`. Last run: 2026-05-15T21:35:24.957Z._