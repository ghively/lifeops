#!/usr/bin/env bash
# Manage a local NornicDB instance.
#
# NornicDB is the single application/world-model database (BUILD_SPEC section 2).
# It binds to 127.0.0.1 only: LifeOps holds the user's personal world, and that
# does not belong on a listening interface.
#
#   ./scripts/nornicdb.sh start|stop|restart|status|logs
set -euo pipefail

LIFEOPS_HOME="${LIFEOPS_HOME:-$HOME/.local/share/lifeops}"
NORNIC_BIN="${NORNIC_BIN:-$HOME/.local/lib/lifeops/nornicdb}"
DATA_DIR="${LIFEOPS_NORNIC_DATA_DIR:-$LIFEOPS_HOME/nornicdb-data}"
LOG_FILE="$LIFEOPS_HOME/logs/nornicdb.log"
PID_FILE="$LIFEOPS_HOME/nornicdb.pid"
ENV_FILE="$LIFEOPS_HOME/nornicdb.env"

HTTP_PORT="${LIFEOPS_NORNIC_HTTP_PORT:-7474}"
BOLT_PORT="${LIFEOPS_NORNIC_BOLT_PORT:-7687}"

mkdir -p "$LIFEOPS_HOME/logs" "$DATA_DIR"

if [[ ! -x "$NORNIC_BIN" ]]; then
  echo "NornicDB binary not found at $NORNIC_BIN" >&2
  echo "Run ./scripts/build-nornicdb.sh first." >&2
  exit 1
fi

# The admin password is generated once and stored 0600 outside the repository.
# The user is never asked for it, and it is never committed (BUILD_SPEC 5, 24).
#
# NornicDB writes the admin credential into the data directory the first time
# it initialises. --admin-password therefore only takes effect on a fresh
# data directory; pointing a new env file at an existing one fails to
# authenticate. To reset it, remove the data directory (destructive) or change
# the password through NornicDB's admin API.
if [[ ! -f "$ENV_FILE" ]]; then
  umask 077
  printf 'LIFEOPS_NORNIC_USER=admin\nLIFEOPS_NORNIC_PASSWORD=%s\n' \
    "$(head -c 32 /dev/urandom | base64 | tr -d '/+=' | head -c 40)" > "$ENV_FILE"
  echo "Generated NornicDB credentials at $ENV_FILE"
fi
# shellcheck disable=SC1090
source "$ENV_FILE"

is_running() {
  [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

# A stray instance from a previous run would hold the port and silently serve a
# different data directory, which is a confusing way to lose data.
assert_port_free() {
  if (exec 3<>"/dev/tcp/127.0.0.1/$BOLT_PORT") 2>/dev/null; then
    exec 3>&-
    echo "Something is already listening on Bolt port $BOLT_PORT." >&2
    echo "Stop it first, or set LIFEOPS_NORNIC_BOLT_PORT." >&2
    return 1
  fi
  return 0
}

wait_for_bolt() {
  for _ in $(seq 1 60); do
    if (exec 3<>"/dev/tcp/127.0.0.1/$BOLT_PORT") 2>/dev/null; then
      exec 3>&-
      return 0
    fi
    sleep 0.5
  done
  echo "NornicDB did not open Bolt on port $BOLT_PORT; see $LOG_FILE" >&2
  return 1
}

start() {
  if is_running; then
    echo "NornicDB is already running (pid $(cat "$PID_FILE"))"
    return 0
  fi
  assert_port_free
  # --headless: LifeOps Console is the only UI (BUILD_SPEC section 9).
  # Embeddings stay off in Phase 0: there is nothing to embed until Phase 2,
  # and loading a model would be infrastructure for a problem that does not
  # exist yet (section 105).
  nohup "$NORNIC_BIN" serve \
    --data-dir "$DATA_DIR" \
    --address 127.0.0.1 \
    --http-port "$HTTP_PORT" \
    --bolt-port "$BOLT_PORT" \
    --headless \
    --admin-password "$LIFEOPS_NORNIC_PASSWORD" \
    >> "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  wait_for_bolt
  echo "NornicDB started (pid $(cat "$PID_FILE")) — bolt://127.0.0.1:$BOLT_PORT"
}

stop() {
  if ! is_running; then
    echo "NornicDB is not running"
    rm -f "$PID_FILE"
    return 0
  fi
  local pid
  pid="$(cat "$PID_FILE")"
  kill "$pid"
  for _ in $(seq 1 60); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.5
  done
  # SIGKILL only after a graceful window: an unclean stop is exactly the
  # scenario the persistence tests are meant to survive, not to cause.
  kill -0 "$pid" 2>/dev/null && kill -9 "$pid"
  rm -f "$PID_FILE"
  echo "NornicDB stopped"
}

case "${1:-status}" in
  start)   start ;;
  stop)    stop ;;
  restart) stop; start ;;
  status)
    if is_running; then
      echo "running (pid $(cat "$PID_FILE")) — bolt://127.0.0.1:$BOLT_PORT"
    else
      echo "stopped"
      exit 1
    fi
    ;;
  logs)    tail -n "${2:-50}" "$LOG_FILE" ;;
  *)
    echo "usage: $0 {start|stop|restart|status|logs}" >&2
    exit 2
    ;;
esac
