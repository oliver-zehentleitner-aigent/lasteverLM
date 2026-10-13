# Same targets in every lasteverLM repository.
VENV ?= .venv
PY := $(VENV)/bin/python
IMAGE ?= lasteverlm-ingest
TAG ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)

.PHONY: install check lint types test test-postgres run worker build

# Creates .venv and installs core (by path, it is not on PyPI) and the
# service with its dev extras; idempotent, so `check` can depend on it on
# a fresh checkout and in CI.
install:
	uv venv --allow-existing $(VENV)
	VIRTUAL_ENV=$(VENV) uv pip install -e ../core -e '.[dev]'

lint:
	$(VENV)/bin/ruff check .
	$(VENV)/bin/black --check .

types:
	$(VENV)/bin/mypy

test:
	$(VENV)/bin/pytest

check: install lint types test

# The repository's SQL against a real PostgreSQL with pgvector, in a
# throwaway container; skipped without Docker. Same pattern as core and rag.
PG_IMAGE ?= pgvector/pgvector:pg17
PG_PORT ?= 5435
DOCKER ?= sg docker -c
test-postgres: install
	@if ! $(DOCKER) "docker info" >/dev/null 2>&1; then echo "test-postgres: skipped, no Docker"; exit 0; fi
	@cid=$$($(DOCKER) "docker run -d --rm -p $(PG_PORT):5432 -e POSTGRES_PASSWORD=x $(PG_IMAGE)"); \
	trap '$(DOCKER) "docker stop $$cid" >/dev/null' EXIT; \
	INGEST_TEST_DATABASE_URL=postgresql://postgres:x@127.0.0.1:$(PG_PORT)/postgres \
	$(VENV)/bin/pytest -m postgres tests/test_postgres.py

run:
	$(VENV)/bin/uvicorn --factory lasteverlm_ingest.main:create_app --host 0.0.0.0 --port $${PORT:-8000} --reload

worker:
	$(VENV)/bin/lasteverlm-ingest-worker

build:
	docker build -f Dockerfile -t $(IMAGE):$(TAG) ..
