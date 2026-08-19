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

# How is the database being run? The PID file only knows about instances this
# repository's script started. A systemd-managed deployment has no PID file,
# so the original check concluded "not running" and copied the data directory
# hot, mid-write — the exact inconsistency the stop exists to prevent, found
# on the first systemd deployment (2026-08-19 audit). Detection is by
# manager, and an instance held by something this script cannot stop is a
# refusal, not a hot copy.
manager="none"
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  manager="script"
elif systemctl --user is-active --quiet lifeops-nornicdb 2>/dev/null; then
  manager="systemd"
elif (exec 3<>"/dev/tcp/127.0.0.1/${LIFEOPS_NORNIC_BOLT_PORT:-7687}") 2>/dev/null; then
  exec 3>&-
  echo "Something is serving Bolt on port ${LIFEOPS_NORNIC_BOLT_PORT:-7687}, but it is" >&2
  echo "neither this repository's script nor the lifeops-nornicdb systemd unit." >&2
  echo "Refusing to copy the data directory out from under a running database" >&2
  echo "this script cannot stop. Stop it yourself, then re-run the backup." >&2
  exit 1
fi

# Stop NornicDB before copying its data directory, so the copy is not taken
# mid-write (OPERATIONS.md). Restarted below on exit, however it is managed.
case "$manager" in
  script)
    echo "Stopping NornicDB (script-managed) for a consistent copy..."
    LIFEOPS_HOME="$LIFEOPS_HOME" LIFEOPS_NORNIC_DATA_DIR="$DATA_DIR" "$NORNIC_CTL" stop
    ;;
  systemd)
    echo "Stopping lifeops-nornicdb (systemd-managed) for a consistent copy..."
    # Stopping the database also stops lifeops-core (Requires=), and starting
    # the database again does not bring core back — systemd dependencies
    # propagate stops, not starts. Both are restarted below.
    systemctl --user stop lifeops-nornicdb
    ;;
esac

restart_if_needed() {
  case "$manager" in
    script)
      echo "Restarting NornicDB..."
      LIFEOPS_HOME="$LIFEOPS_HOME" LIFEOPS_NORNIC_DATA_DIR="$DATA_DIR" "$NORNIC_CTL" start
      ;;
    systemd)
      echo "Restarting lifeops-nornicdb and lifeops-core..."
      systemctl --user start lifeops-nornicdb lifeops-core
      ;;
  esac
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
