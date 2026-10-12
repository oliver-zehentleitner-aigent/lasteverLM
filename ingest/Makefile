# Same targets in every lasteverLM repository.
VENV ?= .venv
PY := $(VENV)/bin/python
IMAGE ?= lasteverlm-ingest
TAG ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)

.PHONY: venv check lint types test run worker build

venv:
	uv venv $(VENV)
	VIRTUAL_ENV=$(VENV) uv pip install -e '.[dev]'

lint:
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .

types:
	$(VENV)/bin/mypy

test:
	$(VENV)/bin/pytest

check: lint types test

run:
	$(VENV)/bin/uvicorn --factory lasteverlm_ingest.main:create_app --host 0.0.0.0 --port $${PORT:-8000} --reload

worker:
	$(VENV)/bin/lasteverlm-ingest-worker

build:
	docker build -f Dockerfile -t $(IMAGE):$(TAG) ..
