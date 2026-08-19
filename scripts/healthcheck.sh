#!/usr/bin/env bash
# Report the health of every LifeOps component.
#
# Exits non-zero if anything required is unhealthy, so it can gate a deploy or
# drive a monitor.
set -uo pipefail

# Deployment settings live in .env (CONFIGURATION.md). Python reads it through
# pydantic-settings; the shell scripts have to be told. Without this, a host
# where Core runs on a non-default port has healthcheck probing 8080 — which on
# a machine with something else there reports OK for the wrong process.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a; . "$REPO_ROOT/.env"; set +a
fi

LIFEOPS_HOME="${LIFEOPS_HOME:-$HOME/.local/share/lifeops}"
CORE_URL="${LIFEOPS_CORE_URL:-http://127.0.0.1:${LIFEOPS_HTTP_PORT:-8080}}"
BOLT_PORT="${LIFEOPS_NORNIC_BOLT_PORT:-7687}"
NORNIC_HTTP_PORT="${LIFEOPS_NORNIC_HTTP_PORT:-7474}"

failed=0

check() {
  local name="$1" ok="$2" detail="${3:-}"
  if [[ "$ok" == "0" ]]; then
    printf '  %-18s OK      %s\n' "$name" "$detail"
  else
    printf '  %-18s FAILED  %s\n' "$name" "$detail"
    failed=1
  fi
}

echo "LifeOps health"
echo

# The HTTP /health endpoint proves an actual NornicDB is answering; the old
# bare TCP connect reported OK for anything listening on the port — a stray
# instance serving different data, or an unrelated service (2026-08-18
# audit, P2). The bolt TCP probe stays as a fallback with an honest label.
if curl -sf --max-time 5 "http://127.0.0.1:$NORNIC_HTTP_PORT/health" >/dev/null 2>&1; then
  check "NornicDB" "0" "http://127.0.0.1:$NORNIC_HTTP_PORT/health"
else
  (exec 3<>"/dev/tcp/127.0.0.1/$BOLT_PORT") 2>/dev/null
  check "NornicDB (port only)" "$?" \
    "127.0.0.1:$BOLT_PORT open — /health did not answer; something listens, unverified"
  exec 3>&- 2>/dev/null || true
fi

core_body="$(curl -sf --max-time 5 "$CORE_URL/health" 2>/dev/null)"
check "LifeOps Core" "$?" "$CORE_URL"

if [[ -n "$core_body" ]]; then
  # Component detail comes from LifeOps itself, so this reflects what the
  # Console shows rather than a second, drifting definition of health.
  component_report="$(curl -sf --max-time 5 "$CORE_URL/api/v1/health" 2>/dev/null | python3 -c '
import json, sys

try:
    components = json.load(sys.stdin).get("components", {})
except Exception:
    sys.exit(1)

unhealthy = 0
for name, value in components.items():
    if isinstance(value, dict):
        detail = value.get("detail", "")
        if value.get("healthy"):
            state = "OK     "
        else:
            state = "FAILED "
            unhealthy = 1
        print("  {:<18} {} {}".format(name, state, detail))
    else:
        print("  {:<18} {}".format(name, value))
sys.exit(unhealthy)
')"
  component_status=$?
  [[ -n "$component_report" ]] && printf '%s\n' "$component_report"
  [[ "$component_status" == "0" ]] || failed=1
fi

if [[ -f "$LIFEOPS_HOME/secrets/master.key" ]]; then
  mode="$(stat -c '%a' "$LIFEOPS_HOME/secrets/master.key")"
  [[ "$mode" == "600" ]]
  check "Secret master key" "$?" "mode $mode (expected 600)"
fi

echo
if [[ "$failed" == "0" ]]; then
  echo "All checks passed."
else
  echo "One or more checks failed." >&2
fi
exit "$failed"
