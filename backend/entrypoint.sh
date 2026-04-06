#!/bin/bash
set -e

# Fix volume permissions for non-root user
chown -R appuser:appuser /app/data 2>/dev/null || true

# Execute as non-root user
exec gosu appuser "$@"
