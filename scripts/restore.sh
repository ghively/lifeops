#!/usr/bin/env bash
# Restore a backup made by scripts/backup.sh into a LifeOps state directory
# (BUILD_SPEC sections 79-80).
#
# The destination is a required, explicit argument — there is no default and
# it is never inferred from LIFEOPS_HOME — so a restore can never land on a
# real deployment by accident. Point it at a temporary directory to test a
# backup; point it at a fresh $LIFEOPS_HOME only when you actually mean to
# replace what is there.
#
#   ./scripts/restore.sh <backup-dir> <destination-home> [--force]
#
# After restoring, start NornicDB against the destination with:
#   LIFEOPS_HOME=<destination-home> ./scripts/nornicdb.sh start
set -euo pipefail

SRC="${1:?usage: $0 <backup-dir> <destination-home> [--force]}"
DEST_HOME="${2:?usage: $0 <backup-dir> <destination-home> [--force]}"
FORCE="${3:-}"

if [[ ! -d "$SRC" ]]; then
  echo "No such backup directory: $SRC" >&2
  exit 1
fi

if [[ -e "$DEST_HOME" ]] && [[ -n "$(ls -A "$DEST_HOME" 2>/dev/null)" ]] && [[ "$FORCE" != "--force" ]]; then
  echo "$DEST_HOME already exists and is not empty." >&2
  echo "Pass --force as the third argument to restore into it anyway." >&2
  exit 1
fi

mkdir -p "$DEST_HOME"

if [[ -d "$SRC/nornicdb-data" ]]; then
  rm -rf "$DEST_HOME/nornicdb-data"
  cp -a "$SRC/nornicdb-data" "$DEST_HOME/nornicdb-data"
else
  echo "Backup has no nornicdb-data; the restored database will start empty." >&2
fi

if [[ -f "$SRC/nornicdb.env" ]]; then
  cp -a "$SRC/nornicdb.env" "$DEST_HOME/nornicdb.env"
  chmod 600 "$DEST_HOME/nornicdb.env"
else
  echo "WARNING: backup has no nornicdb.env. The restored database will not" >&2
  echo "authenticate until its admin credential is recovered — NornicDB fixes" >&2
  echo "the password at data-directory initialisation, so this cannot be" >&2
  echo "regenerated after the fact (see CLAUDE.md, OPERATIONS.md)." >&2
fi

if [[ -d "$SRC/config" ]]; then
  rm -rf "$DEST_HOME/config"
  cp -a "$SRC/config" "$DEST_HOME/config"
fi

mkdir -p "$DEST_HOME/secrets"
chmod 700 "$DEST_HOME/secrets"

if [[ -f "$SRC/secrets/secrets.json" ]]; then
  cp -a "$SRC/secrets/secrets.json" "$DEST_HOME/secrets/secrets.json"
  chmod 600 "$DEST_HOME/secrets/secrets.json"
fi

# The master key normally travels on separate media (BUILD_SPEC section 79);
# accept it from backup.sh's separated subtree, or from alongside the vault
# for a restore that intentionally reunites the two.
if [[ -f "$SRC/secret-master-key/master.key" ]]; then
  cp -a "$SRC/secret-master-key/master.key" "$DEST_HOME/secrets/master.key"
  chmod 600 "$DEST_HOME/secrets/master.key"
elif [[ -f "$SRC/secrets/master.key" ]]; then
  cp -a "$SRC/secrets/master.key" "$DEST_HOME/secrets/master.key"
  chmod 600 "$DEST_HOME/secrets/master.key"
elif [[ -f "$SRC/secrets/secrets.json" ]]; then
  echo "WARNING: no secret master key found in this backup. Restore it from" >&2
  echo "its separate medium to $DEST_HOME/secrets/master.key, or the secret" >&2
  echo "store cannot decrypt anything in secrets.json." >&2
fi

echo "Restored into $DEST_HOME"
echo "Start NornicDB against it with: LIFEOPS_HOME=$DEST_HOME ./scripts/nornicdb.sh start"
