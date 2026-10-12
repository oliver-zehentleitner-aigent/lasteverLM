# Contributing

This repository is one service of the lasteverLM family. The rules for
working across the family — one agent or person per repository, branch
naming, pull requests from a fork against this repository, who merges —
are in the parent's
[AGENTS.md](https://github.com/oliver-zehentleitner/lasteverLM/blob/main/AGENTS.md).

## Changes to the API or the schema

The ingest endpoints and the `notebooks`, `sources` and `chunks` tables
are read by other services. A change to either is a pull request against
the family's
[architecture document](https://github.com/oliver-zehentleitner/lasteverLM/blob/main/docs/architecture.md)
first; the implementation here follows once that is merged.

## Before opening a pull request

```bash
ruff check . && ruff format --check .
mypy
pytest
```

All three must pass. New logic comes with tests; the tests run without a
database, a bucket or network access (see `tests/fakes.py`).

## What goes where

- `CHANGELOG.md` — what changed, under `[Unreleased]`, Keep a Changelog format.
- `context/` — why it changed: decisions, rejected alternatives, constraints. Written with the Keep the Why skill (see `AGENTS.md`), not by hand.
- `docs/` — how to run, configure and operate the service.
- Reasoning that concerns more than this service goes to the parent repository, not here.

## Style

Python 3.12+, type hints everywhere, `ruff` for linting and formatting,
`mypy` clean. Every stage of the pipeline is an interface with one
implementation; a new source kind, chunker, embedder or storage is a new
module, never an edit to its callers.
