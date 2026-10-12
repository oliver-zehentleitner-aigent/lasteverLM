# Contributing

`account/` is one service directory of the lasteverLM repository. The
rules for working across services, the API contract, the repository
standard and the task board are at the repository root: read
`../AGENTS.md`, `../docs/architecture.md` and
`../docs/repository-standard.md` first. Touch only this directory; root
files and `.github/` change through their owners.

## Flow

1. Fork, or branch if you have push access. Branches are named
   `<who>/<topic>`; agent sessions use `agent-<letter>/<topic>`.
2. Make a handful of meaningful commits per feature. Subject in the
   imperative, under 72 characters, a body that says why when the diff
   does not.
3. Open one pull request against `main` of the maintainer's repository.
   Agent A reviews and merges until the first prototype is accepted, the
   maintainer afterwards.

A pull request is complete when it contains, in the same change:

- the code and its unit tests (`make check` green);
- a line under `[Unreleased]` in `CHANGELOG.md`, alphabetical by first word within its category;
- the README and `docs/` updated wherever an endpoint, variable, port or path changed, with the run, test and build sections verified by actually running them;
- a `context/` entry for every decision, rejected alternative or workaround that the code cannot explain on its own ([Keep the Why](https://keepthewhy.com)); family-wide reasoning goes to the parent through Agent A instead;
- a change to the root `docs/architecture.md` first, when an endpoint, a response shape or a table another service reads changes.

Secrets never enter the repository, not in code, tests, fixtures or
examples.

## Development

```bash
cd account
uv venv && uv pip install -e '.[dev]'
make check          # ruff check, ruff format --check, mypy, pytest
make run-dev        # the API on in-memory storage, links on the console
```

The unit tests fake every provider (database, SMTP) behind its interface
and need no network. `tests/test_postgres.py` runs when
`TEST_DATABASE_URL` points at an empty, disposable database.

## Migrations

New tables or columns go into a new numbered file in `db/migrations/`,
`NNNN_<topic>.sql`, plain PostgreSQL, safe to apply twice
(`create table if not exists`, `on conflict do nothing`), and able to
run inside one transaction. Never edit a file that has been applied
somewhere. `infra/` applies all services' migrations in order.
