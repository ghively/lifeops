#!/bin/bash
# e2e-cron-runner.sh — Run Playwright E2E tests from cron and report results
# Usage: ./e2e-cron-runner.sh [integration|all]
#   integration = only integration health tests (fast, ~2 min)
#   all = full test suite including auth and app features (~5 min)

set -euo pipefail

REPO_DIR="/Users/ghively/.openclaw/workspace-knowledge-os/repo"
REPORT_DIR="$REPO_DIR/frontend/e2e/reports"
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
REPORT_FILE="$REPORT_DIR/$TIMESTAMP.json"
SUMMARY_FILE="$REPORT_DIR/latest-summary.txt"

mkdir -p "$REPORT_DIR"

cd "$REPO_DIR/frontend"

# Check if Docker containers are running
if ! docker compose -f "$REPO_DIR/docker-compose.yml" ps --format '{{.Name}}' | grep -q 'backend'; then
    echo "❌ CRITICAL: Backend container is not running"
    echo "$TIMESTAMP | FAIL | Containers down" >> "$SUMMARY_FILE"
    exit 1
fi

echo "=== E2E Test Run: $TIMESTAMP ==="

if [ "${1:-integration}" = "integration" ]; then
    echo "Running integration health tests only..."
    npx playwright test --project=chromium-integration \
        --reporter=json \
        --output="$REPORT_DIR" \
        2>&1 | tee "$REPORT_DIR/$TIMESTAMP-integration.log"
else
    echo "Running full test suite..."
    npx playwright test \
        --reporter=json \
        --output="$REPORT_DIR" \
        2>&1 | tee "$REPORT_DIR/$TIMESTAMP-full.log"
fi

EXIT_CODE=$?

# Parse results and write summary
if [ -f "test-results.json" ]; then
    PASSED=$(python3 -c "import json; d=json.load(open('test-results.json')); print(d.get('stats',{}).get('expected',0) - d.get('stats',{}).get('unexpected',0))" 2>/dev/null || echo "?")
    FAILED=$(python3 -c "import json; d=json.load(open('test-results.json')); print(d.get('stats',{}).get('unexpected',0))" 2>/dev/null || echo "?")
    TOTAL=$(python3 -c "import json; d=json.load(open('test-results.json')); print(d.get('stats',{}).get('expected',0))" 2>/dev/null || echo "?")
else
    PASSED="?"
    FAILED="?"
    TOTAL="?"
fi

SUMMARY="$TIMESTAMP | exit=$EXIT_CODE | ${PASSED}/${TOTAL} passed | ${FAILED} failed"
echo "$SUMMARY" >> "$SUMMARY_FILE"
echo "=== Result: $SUMMARY ==="

# If any tests failed, print details
if [ "$EXIT_CODE" -ne 0 ]; then
    echo ""
    echo "FAILED TESTS:"
    if [ -f "test-results.json" ]; then
        python3 -c "
import json
d = json.load(open('test-results.json'))
for suite in d.get('suites', []):
    for spec in suite.get('specs', []):
        for test in spec.get('tests', []):
            if test.get('status', []) == ['expected', 'failed']:
                print(f'  ❌ {spec[\"title\"]}')
" 2>/dev/null || echo "  (could not parse results)"
    fi
fi

exit $EXIT_CODE
