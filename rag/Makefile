.PHONY: check lint types test run worker build

VENV ?= .venv
PY := $(VENV)/bin/python
IMAGE ?= lasteverlm-rag
TAG ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)

$(VENV)/bin/activate: pyproject.toml
	uv venv $(VENV)
	. $(VENV)/bin/activate && uv pip install -e ".[dev]"

check: lint types test

lint: $(VENV)/bin/activate
	$(VENV)/bin/ruff format --check .
	$(VENV)/bin/ruff check .

types: $(VENV)/bin/activate
	$(VENV)/bin/mypy

test: $(VENV)/bin/activate
	$(VENV)/bin/pytest -q

run: $(VENV)/bin/activate
	$(VENV)/bin/uvicorn lasteverlm_rag.main:app --factory --host 0.0.0.0 --port 8000 --reload

worker: $(VENV)/bin/activate
	$(VENV)/bin/lasteverlm-rag-worker

build:
	docker build -f Dockerfile -t $(IMAGE):$(TAG) ..
