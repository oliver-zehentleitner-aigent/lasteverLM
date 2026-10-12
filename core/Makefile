# Same targets in every lasteverLM repository. Core is a library: `run`
# has nothing to start and says so, `build` produces the wheel.
VENV ?= .venv

.PHONY: install check lint types test run build

# Creates .venv and installs the library with its dev extras; idempotent,
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
	@echo "lasteverlm-core is a library; nothing to run. Services import it."

build:
	uv build
