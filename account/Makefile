# Same targets in every lasteverLM repository.
VENV ?= .venv
IMAGE ?= lasteverlm-account
TAG ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)

.PHONY: install check lint types test run run-dev build

# Creates .venv and installs the service with its dev extras and ../core (a path
# source in pyproject); idempotent, so `check` can depend on it on a fresh checkout and in CI.
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

# Production entrypoint: PostgreSQL from DATABASE_URL, SMTP from the settings table.
run:
	$(VENV)/bin/uvicorn --factory lasteverlm_account.main:create_app --host 0.0.0.0 --port $${PORT:-8000}

# Development entrypoint: in-memory storage, sign-in links printed to the console,
# a seeded admin and the demo user. No database, no mail server.
run-dev:
	$(VENV)/bin/uvicorn lasteverlm_account.dev:app --host 0.0.0.0 --port $${PORT:-8000} --reload

# The repository root is the build context so core/ can be copied into the image.
build:
	docker build -f Dockerfile -t $(IMAGE):$(TAG) ..
