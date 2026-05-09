# Legacy in-tree Playwright tests

This folder predates the canonical e2e suite at the **repo root** in
[`/e2e/`](../../e2e/). The canonical suite is the one wired up by
`.github/workflows/ci.yml` and described in
[`/CLAUDE.md`](../../CLAUDE.md) as the source of truth for "what's
broken."

## What lives here

- `auth.spec.ts`, `app-features.spec.ts`, `integration-health.spec.ts` —
  earlier specs targeting `localhost:3010` / `:8010` (the docker-compose
  ports). Useful for smoke testing the Docker stack specifically.
- `global-setup.ts` — registers a test user via the API, then logs in via
  the browser and saves storage state.
- `e2e-cron-runner.sh` — one-off shell wrapper used during the original
  manual test sweep.
- `debug-react310.mjs` — a one-off debug script for a specific React 18.x
  edge case.

## Status

⚠️ **Maintenance mode.** New end-to-end tests should be added to
[`/e2e/specs/`](../../e2e/specs/), not here. The new suite covers every
page and every read-side endpoint, and produces
[`/e2e/REPORT.md`](../../e2e/REPORT.md) automatically.

This folder is kept around because:
1. The Docker-compose-targeted ports (3010 / 8010) make it useful for
   verifying production-style image builds.
2. Removing it would silently invalidate any external runner (cron job,
   manual bookmark) that still calls into it.

If you have no consumers, feel free to delete this folder in a follow-up
PR. If you keep it, prefer porting any new coverage to `/e2e/`.
