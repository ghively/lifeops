SHELL := /bin/bash
PYTHON := .venv/bin/python
PIP := .venv/bin/pip
PYTEST := .venv/bin/pytest
LIFEOPS_HOME ?= $(HOME)/.local/share/lifeops
NORNIC_ENV := $(LIFEOPS_HOME)/nornicdb.env

# Tests that touch NornicDB need its generated credential. It lives outside the
# repository and is never committed.
WITH_NORNIC = set -a; [ -f $(NORNIC_ENV) ] && . $(NORNIC_ENV); set +a;

# How the restart tests bounce the database. The script is right when the
# script started it, but a deployment where systemd owns the process has no
# PID file for the script to find — it then reports "not running", refuses
# because something already holds Bolt, and six passing tests turn red for a
# reason that has nothing to do with the code. Overridable so the deployment
# says how its own database restarts:
#
#   make test LIFEOPS_NORNIC_RESTART_CMD="systemctl --user restart lifeops-nornicdb"
LIFEOPS_NORNIC_RESTART_CMD ?= $(PWD)/scripts/nornicdb.sh restart

.DEFAULT_GOAL := help
.PHONY: help setup setup-core setup-console nornic-build nornic-start nornic-stop \
        dev stop status health test test-fast test-integration test-e2e \
        console-test console-lint console-build lint typecheck check clean

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# --- setup -------------------------------------------------------------------

setup: setup-core setup-console  ## Install everything

setup-core:  ## Create the Python environment and install LifeOps Core
	@test -d .venv || python3 -m venv .venv || \
	  (python3 -m venv --without-pip .venv && \
	   curl -sSL https://bootstrap.pypa.io/get-pip.py | .venv/bin/python)
	@$(PIP) install -q -e ".[dev]"
	@# Playwright ships the Python package but not the browser binary, and
	@# tests/unit/test_browser.py launches a real persistent context to prove
	@# BUILD_SPEC section 98's separate-context isolation. Without this a
	@# fresh clone fails three tests for a reason that looks like a code bug.
	@# Best-effort: a machine with no network still gets a working core.
	@$(PYTHON) -m playwright install chromium >/dev/null 2>&1 || \
	  echo "  (playwright chromium not installed — browser tests will skip or fail)"
	@echo "LifeOps Core installed."

setup-console:  ## Install Console dependencies
	@cd console && npm install --silent
	@echo "LifeOps Console installed."

nornic-build:  ## Build NornicDB from source
	@./scripts/build-nornicdb.sh

# --- running -----------------------------------------------------------------

nornic-start:  ## Start NornicDB
	@./scripts/nornicdb.sh start

nornic-stop:  ## Stop NornicDB
	@./scripts/nornicdb.sh stop

dev:  ## Start NornicDB, LifeOps Core, and the Console
	@./scripts/dev.sh start

stop:  ## Stop the whole stack
	@./scripts/dev.sh stop

status:  ## Show what is running
	@./scripts/dev.sh status

health:  ## Report component health
	@./scripts/healthcheck.sh

# --- tests -------------------------------------------------------------------

test-fast:  ## Unit, policy, spec, integration, and chaos tests (no database)
	@$(PYTEST) tests/unit tests/policy tests/spec tests/integration tests/chaos -q

test-integration:  ## Repository tests against a live NornicDB
	@$(WITH_NORNIC) $(PYTEST) tests/persistence -q

test-e2e:  ## Phase 0 exit test
	@$(WITH_NORNIC) LIFEOPS_NORNIC_RESTART_CMD="$(LIFEOPS_NORNIC_RESTART_CMD)" \
	  $(PYTEST) tests/e2e -q

test:  ## Every Python test
	@$(WITH_NORNIC) LIFEOPS_NORNIC_RESTART_CMD="$(LIFEOPS_NORNIC_RESTART_CMD)" \
	  $(PYTEST) -q

console-test:  ## Console unit tests
	@cd console && npm test

console-lint:  ## Lint the Console (react-hooks rules catch real bugs)
	@cd console && npm run lint

console-build:  ## Type-check and build the Console
	@cd console && npm run build

# --- quality -----------------------------------------------------------------

lint:  ## Lint Python
	@.venv/bin/ruff check core tests

typecheck:  ## Type-check Python
	@.venv/bin/mypy

check: lint typecheck test console-lint console-test console-build  ## The full local gate (CI runs the same suites, plus repo-hygiene asserts)

clean:  ## Remove build artefacts (never touches LifeOps state or secrets)
	@rm -rf console/dist console/node_modules/.vite .pytest_cache
	@find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned. LifeOps state in $(LIFEOPS_HOME) is untouched."
