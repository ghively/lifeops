# Knowledge OS — End-to-End Suite Report

🟡 **Suite has not been run yet on this branch.** This file is regenerated
on every run of `e2e/scripts/run-suite.sh`. Until the first run, no
results are available.

## How to populate this report

```bash
# 1. Bring up the stack:
#    - Backend at http://localhost:8000 (or set E2E_BACKEND_URL)
#    - Frontend at http://localhost:5173 (or set E2E_FRONTEND_URL)
#    - Qdrant on the configured port

# 2. Run the suite (always exits 0):
cd e2e
bash scripts/run-suite.sh

# 3. This file will be overwritten with the real results.
```

## What this file will contain after a real run

- A "What Needs to Be Fixed" punch list — every failing test, with file
  path, error message, and links to screenshots / traces / videos.
- A per-spec pass/fail/skip breakdown.
- A list of skipped tests with the reasons they were skipped (feature
  gated, precondition unmet, etc.).
- Total duration and the Playwright exit code.

## Spec coverage (60 tests across 13 files)

| Group | Files | Coverage |
|---|---|---|
| Anonymous surface | `00-anonymous/` | Login, register, reset-password, protected-route bounce, /health |
| Navigation | `10-navigation/` | Every primary route loads; sidebar links navigate |
| Outliner | `20-outliner/` | Editor surface, typing, Enter behavior |
| Tasks | `30-tasks/` | List, create affordance, create flow |
| Files | `40-files/` | Upload affordance, file upload |
| Search | `50-search/` | Input, query submit |
| Agents | `60-agents/` | List, create, agent affordances |
| Agent chat | `61-agent-chat/` | Chat surface, message input wiring |
| Settings | `70-settings/` | Settings controls, theme toggle |
| Logs | `80-logs/` | Log viewer |
| API | `90-api/` | /health, OpenAPI, every read endpoint, 401 enforcement, agent_id traversal regression |
| Cross-cutting | `95-cross/` | Per-page browser console errors / failed requests |

---

_Run the suite to replace this placeholder with real results._
