.PHONY: venv check lint types test test-postgres run worker build

VENV ?= .venv
PY := $(VENV)/bin/python
IMAGE ?= lasteverlm-rag
TAG ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)

$(VENV)/bin/activate: pyproject.toml ../core/pyproject.toml
	test -d $(VENV) || uv venv $(VENV)
	VIRTUAL_ENV=$(VENV) uv pip install -e ../core -e '.[dev]'
	touch $(VENV)/bin/activate

venv: $(VENV)/bin/activate

check: lint types test

lint: $(VENV)/bin/activate
	$(VENV)/bin/black --check .
	$(VENV)/bin/ruff check .

types: $(VENV)/bin/activate
	$(VENV)/bin/mypy

test: $(VENV)/bin/activate
	$(VENV)/bin/pytest -q

# The SQL paths against a real PostgreSQL with pgvector, in a throwaway
# container; skipped without Docker. Same pattern as core/Makefile.
PG_IMAGE ?= pgvector/pgvector:pg17
PG_PORT ?= 5434
DOCKER ?= sg docker -c
test-postgres: $(VENV)/bin/activate
	@if ! $(DOCKER) "docker info" >/dev/null 2>&1; then echo "test-postgres: skipped, no Docker"; exit 0; fi
	@cid=$$($(DOCKER) "docker run -d --rm -p $(PG_PORT):5432 -e POSTGRES_PASSWORD=x $(PG_IMAGE)"); \
	trap '$(DOCKER) "docker stop $$cid" >/dev/null' EXIT; \
	RAG_TEST_DATABASE_URL=postgresql://postgres:x@127.0.0.1:$(PG_PORT)/postgres \
	$(VENV)/bin/pytest -m postgres tests/test_postgres.py

run: $(VENV)/bin/activate
	$(VENV)/bin/uvicorn lasteverlm_rag.main:app --factory --host 0.0.0.0 --port 8000 --reload

worker: $(VENV)/bin/activate
	$(VENV)/bin/lasteverlm-rag-worker

build:
	docker build -f Dockerfile -t $(IMAGE):$(TAG) ..
