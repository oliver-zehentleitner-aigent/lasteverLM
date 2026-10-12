# Contributing

`infra/` is one directory of the lasteverLM repository. Read the root
`AGENTS.md` and `docs/architecture.md` first; the rules there apply here.

## Workflow

- Branch from `main`, name the branch `agent-<letter>/<topic>` (or `<name>/<topic>` for people).
- One pull request per topic against `oliver-zehentleitner/lasteverLM`, `main` as base. The maintainer merges.
- A handful of meaningful commits per feature. Commit messages in English, imperative mood.
- Every change that another service depends on (ports, secret names, chart values, schema) is an interface change: update the root `docs/architecture.md` in the same pull request and tell the owner of the affected service.

## Checks before a pull request

```sh
make check    # tofu fmt + validate, helm lint + template, shell syntax, unit tests, ktw-lint
```

- Schema changes are a new file `db/migrations/NNNN_<topic>.sql`, never an edit of an applied one.
- Secrets never enter the repository, not in manifests, not in examples, not in tests.
- Record the reasoning behind a non-obvious choice in `context/` (Keep the Why); the `CHANGELOG.md` records what changed.

## Keep the Why

Before editing anything in `context/`, load the Keep the Why skill as
described in `AGENTS.md`. The `.keep-the-why` file is its configuration.
