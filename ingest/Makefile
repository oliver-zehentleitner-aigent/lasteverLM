# Same targets in every lasteverLM repository.
VENV ?= .venv
PY := $(VENV)/bin/python
IMAGE ?= lasteverlm-ingest
TAG ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)

.PHONY: install check lint types test run worker build

# Creates .venv and installs the service with its dev extras; idempotent,
# so `check` can depend on it on a fresh checkout and in CI.
install:
	uv sync --all-extras

lint:
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .

types:
	$(VENV)/bin/mypy

test:
	$(VENV)/bin/pytest

check: install lint types test

run:
	$(VENV)/bin/uvicorn --factory lasteverlm_ingest.main:create_app --host 0.0.0.0 --port $${PORT:-8000} --reload

worker:
	$(VENV)/bin/lasteverlm-ingest-worker

build:
	docker build -f Dockerfile -t $(IMAGE):$(TAG) ..
