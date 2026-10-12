# Contributing

`web/` is one service of the lasteverLM repository. Read the
[architecture](../docs/architecture.md) and the [UI spec](../docs/ui.md)
first; the API this frontend talks to is defined there, and a change to
that contract is changed there in the same pull request, with the owner
of every affected service told. The
[repository standard](../docs/repository-standard.md) applies.

## Workflow

- Fork, branch from `main`, named `<owner>/<topic>` (the family's agents use `agent-e/<topic>`).
- Open a pull request against `main`. The maintainer reviews and merges; CI must be green.
- Commits: a handful of meaningful ones per feature, each building and passing `make check`. Imperative subject, body says why.

## What a pull request contains

- The change, with unit tests for every piece of logic that can be wrong on its own (`src/lib/`), not for framework plumbing.
- Documentation in the same PR: README sections that changed, `docs/` where something is longer than a README section, a `CHANGELOG.md` line under `[Unreleased]` (alphabetical by first word within its category).
- A `context/` entry where a decision was made, an alternative rejected or a workaround accepted, maintained with [Keep the Why](https://keepthewhy.com). Family-wide reasoning goes to the root `context/` via Agent A.
- The README's run, test and build sections verified by running them, not by reading them.

## What goes where

- `src/api/`: one module per API prefix. Types mirror the contract; do not widen them to what a backend happens to return. Nothing else calls `fetch`.
- `src/lib/`: pure functions, unit-tested. Anything that can be tested without a DOM belongs here.
- `src/components/`: React only. `components/outputs/` holds one renderer per document kind, dispatched in `OutputContent.tsx`.

## Style

- TypeScript strict, no `any`. Plain CSS with the variables in `src/styles.css`; no UI framework.
- Errors are shown, never swallowed. If a request fails, the user sees the API's message.
- Content from the model (Markdown, quiz text, table cells) is untrusted: render it through React, or sanitize before `dangerouslySetInnerHTML`.
- English everywhere: code, comments, commits, docs, UI.
