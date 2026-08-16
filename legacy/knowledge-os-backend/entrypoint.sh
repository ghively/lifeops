#!/bin/bash
set -e

# Fix volume permissions for non-root user
chown -R appuser:appuser /app/data 2>/dev/null || true

# Run database migrations as the application user (skip with KOS_SKIP_MIGRATIONS=1).
if [ "${KOS_SKIP_MIGRATIONS:-0}" != "1" ]; then
    echo "[entrypoint] Running alembic migrations..."
    if ! gosu appuser alembic upgrade head; then
        echo "[entrypoint] alembic upgrade failed" >&2
        exit 1
    fi
fi

# Execute as non-root user
exec gosu appuser "$@"
