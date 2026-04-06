#!/usr/bin/env bash
# Dependency vulnerability scanning (H57)
# Usage: ./scripts/check-deps.sh
# Requires: pip-audit (pip install pip-audit)

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REQ_FILE="$REPO_DIR/backend/requirements.txt"

if ! command -v pip-audit &>/dev/null; then
    echo "pip-audit not found. Install with: pip install pip-audit"
    exit 1
fi

echo "Scanning $REQ_FILE for known vulnerabilities..."
pip-audit -r "$REQ_FILE" --progress-spinner off
echo "Vulnerability scan complete."
