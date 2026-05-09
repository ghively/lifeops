#!/usr/bin/env bash
# One-command e2e runner.
#
# Assumes the backend is reachable at $E2E_BACKEND_URL (default
# http://localhost:8000) and the frontend at $E2E_FRONTEND_URL (default
# http://localhost:5173). It will NOT start them — the caller (or a separate
# bring-up script / docker-compose) is responsible for that. This keeps the
# runner safe to invoke inside CI, on a developer's box, or from an agent.
#
# Always exits 0 so the report-generation step always runs and the tail of
# the script can summarize. The exit code of the test phase is preserved in
# $E2E_EXIT_CODE for the reporter.

set -u  # NOT -e: we want to keep going on test failures.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

: "${E2E_FRONTEND_URL:=http://localhost:5173}"
: "${E2E_BACKEND_URL:=http://localhost:8000}"
export E2E_FRONTEND_URL E2E_BACKEND_URL

echo "[e2e] frontend = ${E2E_FRONTEND_URL}"
echo "[e2e] backend  = ${E2E_BACKEND_URL}"

# Install if node_modules is missing.
if [ ! -d node_modules ]; then
  echo "[e2e] installing dependencies..."
  npm ci --prefer-offline --no-audit --fund=false || npm install --no-audit --fund=false
fi

# Make sure the chromium build is present.
if ! npx --no-install playwright --version >/dev/null 2>&1; then
  npm install --no-save @playwright/test
fi
npx playwright install --with-deps chromium 2>&1 | tail -3 || true

# Wait briefly for the stack to come up. Bounded — the caller controls the
# real lifecycle.
echo "[e2e] checking stack..."
for url in "${E2E_BACKEND_URL}/health" "${E2E_FRONTEND_URL}/"; do
  for _ in $(seq 1 30); do
    if curl -fsS -o /dev/null --max-time 3 "${url}"; then
      echo "[e2e] up: ${url}"
      break
    fi
    sleep 1
  done
done

# Run tests. Capture exit but never abort.
echo "[e2e] running tests..."
set +e
npx playwright test --reporter=list,json,html
E2E_EXIT_CODE=$?
set -e
echo "[e2e] playwright exit=${E2E_EXIT_CODE}"

# Generate the report.
echo "[e2e] generating REPORT.md..."
E2E_EXIT_CODE=${E2E_EXIT_CODE} npx tsx scripts/generate-report.ts

echo "[e2e] done."
exit 0
