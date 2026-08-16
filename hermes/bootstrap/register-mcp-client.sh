#!/usr/bin/env bash
# Register LifeOps MCP with a client, using that client's own identity.
#
#   ./hermes/bootstrap/register-mcp-client.sh hermes-personal
#   ./hermes/bootstrap/register-mcp-client.sh claude-code
#
# Prints the launch configuration rather than editing a client's config file in
# place: every MCP client stores this differently, and silently rewriting a
# user's assistant configuration is not a thing a build script should do.
set -euo pipefail

CLIENT_ID="${1:-}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LIFEOPS_HOME="${LIFEOPS_HOME:-$HOME/.local/share/lifeops}"
ENV_FILE="$LIFEOPS_HOME/nornicdb.env"

VALID=(hermes-personal claude-code interactive-mcp lifeops-console)

if [[ -z "$CLIENT_ID" ]] || ! printf '%s\n' "${VALID[@]}" | grep -qx "$CLIENT_ID"; then
  echo "usage: $0 <client-id>" >&2
  echo "known client identities: ${VALID[*]}" >&2
  echo >&2
  echo "Each identity carries its own capabilities. See SECURITY.md." >&2
  exit 2
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "NornicDB is not set up yet. Run ./scripts/nornicdb.sh start first." >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$ENV_FILE"

PYTHON="$REPO_ROOT/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"

cat <<JSON
{
  "mcpServers": {
    "lifeops": {
      "command": "$PYTHON",
      "args": ["-m", "lifeops.mcp.server", "--client", "$CLIENT_ID"],
      "cwd": "$REPO_ROOT",
      "env": {
        "LIFEOPS_NORNIC_URI": "bolt://127.0.0.1:7687",
        "LIFEOPS_NORNIC_USER": "$LIFEOPS_NORNIC_USER",
        "LIFEOPS_NORNIC_PASSWORD": "$LIFEOPS_NORNIC_PASSWORD",
        "LIFEOPS_LOG_LEVEL": "WARNING"
      }
    }
  }
}
JSON

cat >&2 <<'NOTE'

The block above contains the NornicDB password. It is printed so you can paste
it into your client's configuration; do not commit it.

For Claude Code specifically:

  claude mcp add-json lifeops "$(./hermes/bootstrap/register-mcp-client.sh claude-code | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["mcpServers"]["lifeops"]))')"
NOTE
