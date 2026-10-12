# Contributing

`core/` is the shared library of the lasteverLM repository. The rules for
working across the family — one agent or person per directory, branch
naming, pull requests from a fork, who merges — are in the root
[AGENTS.md](https://github.com/oliver-zehentleitner/lasteverLM/blob/main/AGENTS.md).

## Changes to what the services import

Everything exported from `lasteverlm_core` is used by account, ingest or
rag, and the `usage`, `access_log`, `ip_blocks` and `ip_bans` tables are
read by account. A change to a signature, a model field or a table is a
pull request against the family's
[architecture document](https://github.com/oliver-zehentleitner/lasteverLM/blob/main/docs/architecture.md)
first, and the owner of every affected service is told. A migration
that has been applied is never edited; a change is a new numbered file.

## Before opening a pull request

```bash
make check
```

ruff (lint and format), mypy in strict mode and pytest must pass. New
logic comes with tests; the tests run without a database, network or
inference key (see `tests/conftest.py` for the fake connections).

## What goes where

- `CHANGELOG.md` — what changed, under `[Unreleased]`, Keep a Changelog format.
- `context/` — why it changed: decisions, rejected alternatives, constraints. Written with the Keep the Why skill (see `AGENTS.md`), not by hand; each entry in its own commit.
- `docs/` — how to use the library from a service.
- Reasoning that concerns more than this library goes to the root `context/`, not here.

## Style

Python 3.12+, type hints everywhere, `ruff` for linting and formatting,
`mypy --strict` clean. Core depends on as little as possible: Pydantic,
PyJWT, the OpenAI SDK and anyio. No database driver: the PostgreSQL
helpers take the caller's psycopg connection and type it structurally.
Every provider is an interface with one implementation; another provider
is a new module, never an edit to its callers.
