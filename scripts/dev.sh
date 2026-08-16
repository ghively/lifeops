#!/usr/bin/env bash
# Bring up the whole LifeOps stack for development.
#
#   ./scripts/dev.sh          start everything
#   ./scripts/dev.sh stop     stop everything
#   ./scripts/dev.sh status   show what is running
#
# No provider credential is needed. LifeOps boots with every provider
# disabled, and the user configures real values in the Console afterwards
# (BUILD_SPEC section 104).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIFEOPS_HOME="${LIFEOPS_HOME:-$HOME/.local/share/lifeops}"
LOG_DIR="$LIFEOPS_HOME/logs"
CORE_PID="$LIFEOPS_HOME/lifeops-core.pid"
CONSOLE_PID="$LIFEOPS_HOME/lifeops-console.pid"

CORE_PORT="${LIFEOPS_HTTP_PORT:-8080}"
CONSOLE_PORT="${LIFEOPS_CONSOLE_PORT:-5173}"

mkdir -p "$LOG_DIR"

PYTHON="$REPO_ROOT/.venv/bin/python"

alive() { [[ -f "$1" ]] && kill -0 "$(cat "$1")" 2>/dev/null; }

port_busy() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && { exec 3>&-; return 0; }
  return 1
}

start() {
  if [[ ! -x "$PYTHON" ]]; then
    echo "Python environment missing. Run: make setup" >&2
    exit 1
  fi

  "$REPO_ROOT/scripts/nornicdb.sh" start

  # LifeOps reads the NornicDB credential from the file the database script
  # generated. It is never committed and never typed by a human.
  # shellcheck disable=SC1091
  set -a; source "$LIFEOPS_HOME/nornicdb.env"; set +a

  if alive "$CORE_PID"; then
    echo "LifeOps Core already running (pid $(cat "$CORE_PID"))"
  elif port_busy "$CORE_PORT"; then
    # Something we did not start holds the port. Launching anyway would leave a
    # process that cannot bind and a status line that lies about it.
    echo "Port $CORE_PORT is already in use by a process this script did not" >&2
    echo "start. Stop it, or set LIFEOPS_HTTP_PORT." >&2
    exit 1
  else
    # `cd X && nohup Y &` backgrounds the whole compound, so $! would be the
    # subshell rather than the server. Launch from a subshell that execs, so
    # the recorded PID is the process itself.
    (
      cd "$REPO_ROOT" || exit 1
      exec "$PYTHON" -m lifeops.main --port "$CORE_PORT" \
        >> "$LOG_DIR/lifeops-core.log" 2>&1
    ) &
    echo $! > "$CORE_PID"

    for _ in $(seq 1 40); do
      curl -sf "http://127.0.0.1:$CORE_PORT/health" >/dev/null 2>&1 && break
      sleep 0.5
    done
    if alive "$CORE_PID" && curl -sf "http://127.0.0.1:$CORE_PORT/health" >/dev/null 2>&1; then
      echo "LifeOps Core started (pid $(cat "$CORE_PID")) — http://127.0.0.1:$CORE_PORT"
    else
      rm -f "$CORE_PID"
      echo "LifeOps Core failed to start. See $LOG_DIR/lifeops-core.log" >&2
      exit 1
    fi
  fi

  if alive "$CONSOLE_PID"; then
    echo "LifeOps Console already running (pid $(cat "$CONSOLE_PID"))"
  elif port_busy "$CONSOLE_PORT"; then
    echo "Port $CONSOLE_PORT is already in use. Stop it, or set LIFEOPS_CONSOLE_PORT." >&2
    exit 1
  else
    (
      cd "$REPO_ROOT/console" || exit 1
      export VITE_LIFEOPS_PORT="$CORE_PORT"
      exec npm run dev -- --port "$CONSOLE_PORT" \
        >> "$LOG_DIR/lifeops-console.log" 2>&1
    ) &
    echo $! > "$CONSOLE_PID"
    echo "LifeOps Console starting (pid $(cat "$CONSOLE_PID")) — http://127.0.0.1:$CONSOLE_PORT"
  fi
}

stop() {
  for pidfile in "$CONSOLE_PID" "$CORE_PID"; do
    if alive "$pidfile"; then
      pkill -P "$(cat "$pidfile")" 2>/dev/null || true
      kill "$(cat "$pidfile")" 2>/dev/null || true
    fi
    rm -f "$pidfile"
  done
  "$REPO_ROOT/scripts/nornicdb.sh" stop
  echo "Stopped"
}

status() {
  "$REPO_ROOT/scripts/nornicdb.sh" status || true
  alive "$CORE_PID" && echo "LifeOps Core: running (pid $(cat "$CORE_PID"))" \
    || echo "LifeOps Core: stopped"
  alive "$CONSOLE_PID" && echo "LifeOps Console: running (pid $(cat "$CONSOLE_PID"))" \
    || echo "LifeOps Console: stopped"
}

case "${1:-start}" in
  start)  start ;;
  stop)   stop ;;
  status) status ;;
  restart) stop; start ;;
  *) echo "usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
