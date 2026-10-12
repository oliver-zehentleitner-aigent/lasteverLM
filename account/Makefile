.PHONY: check lint types test run run-dev build

PYTHON ?= .venv/bin/python
IMAGE  ?= lasteverlm-account
TAG    ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)

check: lint types test

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

types:
	$(PYTHON) -m mypy

test:
	$(PYTHON) -m pytest

# Production entrypoint: PostgreSQL from DATABASE_URL, SMTP from the settings table.
run:
	$(PYTHON) -m uvicorn lasteverlm_account.main:app --host 0.0.0.0 --port 8000

# Development entrypoint: in-memory storage, sign-in links printed to the console,
# a seeded admin and the demo user. No database, no mail server.
run-dev:
	$(PYTHON) -m uvicorn lasteverlm_account.dev:app --host 0.0.0.0 --port 8000

# The repository root is the build context so core/ can be copied into the image.
build:
	docker build -f Dockerfile -t $(IMAGE):$(TAG) ..
