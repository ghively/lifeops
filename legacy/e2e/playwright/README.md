# End-to-End Suite

Comprehensive Playwright suite for Knowledge OS. Designed to be runnable
unattended by an agent (or CI) — produces a single Markdown report that
summarizes what's working and what needs to be fixed.

## TL;DR for an agent

```bash
# 1. Bring up the backend + frontend (separate terminal or container).
#    Backend on http://localhost:8000, frontend on http://localhost:5173.

# 2. Run the suite. Always exits 0; the report tells you what happened.
cd e2e
bash scripts/run-suite.sh

# 3. Read the report.
cat REPORT.md
```

## What the suite covers

| Spec group | What it exercises |
|---|---|
| `00-anonymous/` | Login page, register flow, reset-password, protected-route bounce, 404 handling |
| `10-navigation/` | Every primary route loads; sidebar links navigate |
| `20-outliner/` | Block editor surface, typing, Enter behavior |
| `30-tasks/` | Tasks page renders, create-task affordance, list area |
| `40-files/` | Files page, upload affordance, small-file upload |
| `50-search/` | Search input, query submission |
| `60-agents/` | Agents page, create flow, agent listing |
| `61-agent-chat/` | Agent chat surface, message input wiring (does not call the LLM) |
| `70-settings/` | Settings page, theme/profile controls |
| `80-logs/` | Logs page, content area |
| `90-api/` | Backend `/health`, OpenAPI, every read endpoint, auth-rejection, agent_id traversal regression |
| `95-cross/` | Per-page browser console / pageerror / failed-request coverage |

Each spec is **independent** — one failure does not cascade. Tests use
permissive selectors (role, placeholder, regex) so cosmetic UI changes
don't cause false negatives.

## Configuration

Environment variables (all optional):

| Var | Default | Purpose |
|---|---|---|
| `E2E_FRONTEND_URL` | `http://localhost:5173` | Where the frontend serves the SPA |
| `E2E_BACKEND_URL`  | `http://localhost:8000` | Where the FastAPI backend lives |
| `E2E_TEST_EMAIL`   | `e2e@knowledge-os.local` | Login for the test user |
| `E2E_TEST_USERNAME`| `e2etester` | Username for the test user |
| `E2E_TEST_PASSWORD`| `e2eTestPass!23` | Password for the test user |

Override any of them when invoking the runner — e.g. for a Docker stack
running on different ports:

```bash
E2E_FRONTEND_URL=http://localhost:3010 \
E2E_BACKEND_URL=http://localhost:8010 \
bash scripts/run-suite.sh
```

## What gets written back to the repo

- `e2e/REPORT.md` — human-readable summary; **the canonical artifact for "what's broken"**
- `e2e/playwright-report/` — HTML report with traces and screenshots (git-ignored)
- `e2e/test-results/` — per-test artifacts (git-ignored)

`REPORT.md` is intentionally checked in so the latest run is always visible
in the repo.

## How CLAUDE reads this

`CLAUDE.md` instructs Claude that, whenever the user asks about e2e
results, what is broken, or what needs to be fixed, it should read
`e2e/REPORT.md` rather than re-running the suite or guessing.

## Local development

```bash
cd e2e
npm install
npx playwright install --with-deps chromium

# Run a single spec while iterating:
npx playwright test specs/30-tasks/tasks.spec.ts --headed

# Open the HTML report:
npx playwright show-report playwright-report
```
