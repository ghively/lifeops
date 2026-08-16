#!/usr/bin/env bash
# Build NornicDB from source and install it for LifeOps.
#
# Upstream ships Docker images and macOS packages. On a Linux host without
# Docker, building the Go binary is the shortest path to a running database,
# and it avoids adding a container runtime to satisfy one dependency
# (BUILD_SPEC section 105).
#
#   ./scripts/build-nornicdb.sh [version]
set -euo pipefail

VERSION="${1:-v1.2.2}"
GO_VERSION="${GO_VERSION:-1.26.6}"

WORK_DIR="${LIFEOPS_BUILD_DIR:-${TMPDIR:-/tmp}/lifeops-build}"
INSTALL_DIR="${LIFEOPS_LIB_DIR:-$HOME/.local/lib/lifeops}"
TARGET="$INSTALL_DIR/nornicdb"

mkdir -p "$WORK_DIR" "$INSTALL_DIR"

# --- Go toolchain -----------------------------------------------------------
# NornicDB requires Go >= 1.26. A system Go that is older would fail deep in the
# build, so it is checked up front.
if command -v go >/dev/null 2>&1 && \
   [[ "$(go env GOVERSION 2>/dev/null)" > "go1.26" ]]; then
  GO_BIN="$(command -v go)"
else
  GO_ROOT="$WORK_DIR/go"
  if [[ ! -x "$GO_ROOT/bin/go" ]]; then
    echo "Downloading Go $GO_VERSION..."
    curl -fsSL -o "$WORK_DIR/go.tar.gz" \
      "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz"
    tar -C "$WORK_DIR" -xzf "$WORK_DIR/go.tar.gz"
  fi
  GO_BIN="$GO_ROOT/bin/go"
fi
echo "Using $("$GO_BIN" version)"

# --- source -----------------------------------------------------------------
SRC_DIR="$WORK_DIR/NornicDB"
if [[ -d "$SRC_DIR/.git" ]]; then
  git -C "$SRC_DIR" fetch --depth 1 origin "$VERSION"
  git -C "$SRC_DIR" checkout -q FETCH_HEAD
else
  git clone --depth 1 --branch "$VERSION" \
    https://github.com/orneryd/NornicDB.git "$SRC_DIR"
fi

# --- build ------------------------------------------------------------------
# Tags match upstream's CPU image (docker/Dockerfile.amd64-cpu):
#   noui        LifeOps Console is the only interface LifeOps offers.
#   nolocalllm  No bundled llama.cpp. Embeddings, when Phase 2 needs them,
#               come from a configured provider rather than from the database
#               process.
echo "Building NornicDB $VERSION..."
(
  cd "$SRC_DIR"
  export GOPATH="$WORK_DIR/gopath" GOCACHE="$WORK_DIR/gocache"
  "$GO_BIN" mod download
  CGO_ENABLED=1 "$GO_BIN" build -tags "noui,nolocalllm" -o "$TARGET" ./cmd/nornicdb
)

chmod +x "$TARGET"
echo "Installed $("$TARGET" version) to $TARGET"
echo "Start it with: ./scripts/nornicdb.sh start"
