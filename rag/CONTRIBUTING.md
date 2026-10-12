# Contributing

`rag/` is one service of lasteverLM. The API contract and the data
model live in the repository root's `docs/architecture.md`; a change to
either is agreed there first, and the owner of every affected service is
told.

## Setup

```bash
make check    # creates .venv with uv on first run, then ruff, mypy, pytest
```

## Branches, commits, pull requests

- Branches: `agent-<letter>/<topic>` for agent sessions, `<topic>` otherwise.
- Commits: a handful of meaningful commits per feature, imperative subject line, body says why when the diff does not.
- Fork-and-PR: work lands as a pull request from a fork against `main` of the maintainer's repository; the maintainer merges.
- A pull request contains: tests for every piece of logic that can be wrong on its own, the README and CHANGELOG lines for anything it changes, and a `context/` entry where a decision, a rejected alternative or a workaround was made (through the Keep the Why skill, see `AGENTS.md`). Family-wide reasoning goes to the root's `context/`.
- `make check` is green before every pull request.

## Conventions

- Code, comments, commits, docs and `context/` in English.
- Providers (database, inference) stay behind their interface and are faked in tests; no test needs the network.
- Secrets never enter the repository; the service reads them from the environment.
