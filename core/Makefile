# Same targets in every lasteverLM repository. Core is a library: `run`
# has nothing to start and says so, `build` produces the wheel.
VENV ?= .venv

.PHONY: venv check lint types test run build

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
	@echo "lasteverlm-core is a library; nothing to run. Services import it."

build:
	uv build
