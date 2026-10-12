# Contributing

lasteverLM is one repository with one directory per service. The root
holds the architecture, the family-wide reasoning and the task board.
`AGENTS.md` has the working conventions; this file is the short form for
a human contributor.

## A change

1. Branch from `main`: `<who>/<topic>`.
2. Touch one directory. A change that crosses directories is a change to
   the contract in `docs/architecture.md` first.
3. `make check` in that directory must be green: lint, types, tests.
4. Documentation is part of the change: README, CHANGELOG under
   `[Unreleased]`, and `context/` for every decision, rejected
   alternative or workaround. A `context/` entry is committed right after
   it is written, in its own commit.
5. Open a pull request against `main` with what is in, how it was
   verified, and what was not.

## Commits

Imperative, plain English, prefixed with the directory:
`ingest: claim sources with SKIP LOCKED`. A handful of meaningful commits
per feature; `context/` entries are the exception and get one each.

## Reasoning

Before changing something that looks odd, read the `context/` of that
directory and of the root. If the reason is there, it was argued once
already. If it is not, add it when you find out.

## Security

See [`SECURITY.md`](SECURITY.md). Secrets never enter the repository.
