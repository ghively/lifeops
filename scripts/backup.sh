#!/usr/bin/env bash
# Back up LifeOps state: the NornicDB data directory, non-secret
# configuration, the encrypted secret store, and nornicdb.env (BUILD_SPEC
# section 79).
#
# nornicdb.env matters as much as the data directory: NornicDB's admin
# password is fixed at data-directory initialisation (CLAUDE.md), so a
# restored database with a mismatched or missing env file cannot
# authenticate even though the data itself is intact.
#
# The secret master key is copied into its own subtree, clearly separated
# from everything else in the backup, because OPERATIONS.md requires it be
# kept on a different medium than the rest — a single compromised copy of
# this whole directory should not, by itself, decrypt the secret store. Move
# secret-master-key/ elsewhere immediately after running this script; do not
# leave it beside the rest of the backup at rest.
#
#   ./scripts/backup.sh [destination-dir]
#
# Defaults to backing up $LIFEOPS_HOME (see nornicdb.sh); pass
# LIFEOPS_HOME=/some/other/dir to back up a different deployment, which is how
# the restore-round-trip test exercises this script against a disposable
# state directory instead of the user's real one.
set -euo pipefail

LIFEOPS_HOME="${LIFEOPS_HOME:-$HOME/.local/share/lifeops}"
DATA_DIR="${LIFEOPS_NORNIC_DATA_DIR:-$LIFEOPS_HOME/nornicdb-data}"
CONFIG_DIR="$LIFEOPS_HOME/config"
SECRETS_DIR="$LIFEOPS_HOME/secrets"
ENV_FILE="$LIFEOPS_HOME/nornicdb.env"
PID_FILE="$LIFEOPS_HOME/nornicdb.pid"

DEST="${1:-$LIFEOPS_HOME/backups/$(date -u +%Y%m%dT%H%M%SZ)}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NORNIC_CTL="$SCRIPT_DIR/nornicdb.sh"

if [[ -e "$DEST" ]]; then
  echo "Destination already exists: $DEST" >&2
  exit 1
fi
mkdir -p "$DEST"

was_running=0
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  was_running=1
fi

# Stop NornicDB before copying its data directory, so the copy is not taken
# mid-write (OPERATIONS.md). Restarted below on exit, if it was running.
if [[ "$was_running" -eq 1 ]]; then
  echo "Stopping NornicDB for a consistent copy..."
  LIFEOPS_HOME="$LIFEOPS_HOME" LIFEOPS_NORNIC_DATA_DIR="$DATA_DIR" "$NORNIC_CTL" stop
fi

restart_if_needed() {
  if [[ "$was_running" -eq 1 ]]; then
    echo "Restarting NornicDB..."
    LIFEOPS_HOME="$LIFEOPS_HOME" LIFEOPS_NORNIC_DATA_DIR="$DATA_DIR" "$NORNIC_CTL" start
  fi
}
trap restart_if_needed EXIT

if [[ -d "$DATA_DIR" ]]; then
  cp -a "$DATA_DIR" "$DEST/nornicdb-data"
else
  echo "No NornicDB data directory at $DATA_DIR; skipping." >&2
fi

if [[ -f "$ENV_FILE" ]]; then
  cp -a "$ENV_FILE" "$DEST/nornicdb.env"
else
  echo "No nornicdb.env at $ENV_FILE; a restored database will not authenticate." >&2
fi

if [[ -d "$CONFIG_DIR" ]]; then
  cp -a "$CONFIG_DIR" "$DEST/config"
fi

if [[ -d "$SECRETS_DIR" ]]; then
  mkdir -p "$DEST/secrets" "$DEST/secret-master-key"
  chmod 700 "$DEST/secrets" "$DEST/secret-master-key"
  if [[ -f "$SECRETS_DIR/secrets.json" ]]; then
    cp -a "$SECRETS_DIR/secrets.json" "$DEST/secrets/secrets.json"
  fi
  if [[ -f "$SECRETS_DIR/master.key" ]]; then
    cp -a "$SECRETS_DIR/master.key" "$DEST/secret-master-key/master.key"
    echo "WARNING: secret-master-key/master.key decrypts secrets/secrets.json." >&2
    echo "Move it to separate, secure storage now (BUILD_SPEC section 79's" >&2
    echo "\"back up separately\" rule); do not leave it beside this backup." >&2
  fi
fi

cat > "$DEST/manifest.json" <<JSON
{
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "source_home": "$LIFEOPS_HOME",
  "source_data_dir": "$DATA_DIR",
  "includes": {
    "nornicdb_data": $([[ -d "$DEST/nornicdb-data" ]] && echo true || echo false),
    "nornicdb_env": $([[ -f "$DEST/nornicdb.env" ]] && echo true || echo false),
    "config": $([[ -d "$DEST/config" ]] && echo true || echo false),
    "secrets": $([[ -f "$DEST/secrets/secrets.json" ]] && echo true || echo false),
    "secret_master_key": $([[ -f "$DEST/secret-master-key/master.key" ]] && echo true || echo false)
  }
}
JSON

echo "Backup written to $DEST"
