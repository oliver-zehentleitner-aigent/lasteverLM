# Same targets in every lasteverLM repository. Core is a library: `run`
# has nothing to start and says so, `build` produces the wheel.
VENV ?= .venv

.PHONY: install check lint types test test-postgres run build

# Creates .venv and installs the library with its dev extras; idempotent,
# so `check` can depend on it on a fresh checkout and in CI.
install:
	uv sync --all-extras

lint:
	$(VENV)/bin/ruff check .
	$(VENV)/bin/black --check .

types:
	$(VENV)/bin/mypy

test:
	$(VENV)/bin/pytest

check: install lint types test

# The SQL paths (usage, rate-limit store, purge) against a throwaway
# pgvector container; skipped when Docker is not available. Not part of
# `check`: CI has no Docker socket in the python job.
PG_IMAGE ?= pgvector/pgvector:pg17
PG_PORT ?= 5433
DOCKER ?= sg docker -c
test-postgres: install
	@if ! $(DOCKER) "docker info" >/dev/null 2>&1; then echo "test-postgres: skipped, no Docker"; exit 0; fi
	@cid=$$($(DOCKER) "docker run -d --rm -p $(PG_PORT):5432 -e POSTGRES_PASSWORD=x $(PG_IMAGE)"); \
	trap '$(DOCKER) "docker stop $$cid" >/dev/null' EXIT; \
	CORE_TEST_DATABASE_URL=postgresql://postgres:x@127.0.0.1:$(PG_PORT)/postgres \
	$(VENV)/bin/pytest -m postgres tests/test_postgres.py

run:
	@echo "lasteverlm-core is a library; nothing to run. Services import it."

build:
	uv build
