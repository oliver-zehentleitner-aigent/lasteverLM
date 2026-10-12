# Repository standard

Every repository in the lasteverLM family looks the same, so that a
reader who has seen one knows all of them. This is the checklist; a
pull request that leaves a file below stale is not done.

## Files at the root

| File | Content |
|---|---|
| `README.md` | what the service is, its API prefix, configuration table, how to run it locally, how to test, how it is built and deployed, links to the parent's docs. Badges: CI, ktw-lint, Keep the Why. |
| `CHANGELOG.md` | [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), `[Unreleased]` with `### Added` / `### Changed` / `### Fixed`, one heading per category, entries alphabetical by first word. |
| `CONTRIBUTING.md` | branch naming, commit style, the fork-and-PR flow, what a PR must contain (tests, docs, CHANGELOG line, `context/` where a decision was made). |
| `SECURITY.md` | how to report, what is in scope, the secrets rule. |
| `CODE_OF_CONDUCT.md` | Contributor Covenant. |
| `LICENSE` | MIT. |
| `AGENTS.md` | pointers only: docs, context, conventions, the Keep the Why start section. |
| `.keep-the-why`, `context/` | the why layer, from the first commit, `parent` pointing at this repository. |
| `pyproject.toml` or `package.json` | the one build definition; `uv` for Python, `npm` for web. |
| `Dockerfile` | multi-stage, non-root `USER`, `HEALTHCHECK` not needed (Kubernetes probes `/healthz`). |
| `Makefile` | `make check` (lint, types, tests), `make run`, `make build`; the same targets everywhere. |
| `docs/` | anything longer than a README section: design notes, runbooks. |
| `db/migrations/` | numbered SQL files for the service's own tables (services with tables). |
| `tests/` | unit tests; see below. |

## Tests

- Unit tests for every piece of logic that can be wrong on its own: parsing, chunking, citation mapping, price calculation, token flow, allowlist, voucher atomicity, balance. Not for framework plumbing.
- Providers (database, S3, inference, SMTP) behind their interface and faked in tests; no test needs the network.
- `make check` runs lint (ruff / eslint), types (mypy / tsc) and tests, and is what CI runs. Green before every PR.
- One end-to-end smoke test lives in `lasteverLM-infra`: login with the demo token, create a notebook, upload a text source, wait for ready, ask a question, assert a citation. It runs against a URL given by argument, local or live.

## Workflows (`.github/workflows/`)

| File | Trigger | What |
|---|---|---|
| `ci.yml` | push, pull request | `make check`; for web also `build` |
| `ktw-lint.yml` | push to main, pull request | the Keep the Why structure check |
| `docker.yml` | push to main, tags `v*` | build the image, push it to the registry tagged with the Git SHA and the tag |
| `deploy.yml` | manual (`workflow_dispatch`), infra only | apply the manifests with the given image tags |
| `pages.yml` | push to main | the Keep the Why dashboard export, and for the parent the docs site |

Branch protection on `main` in every repository: pull request required,
CI green. The maintainer merges.

## Versioning and releases

SemVer, tags `v0.1.0` and up per repository, independent of each other.
A tag is cut from `main` after the CHANGELOG's `[Unreleased]` section
became the version section. Core is pinned by tag in the services that
depend on it.

## Documentation stays true

Documentation is part of the change, not a follow-up:

- A changed endpoint, variable, port or path is changed in the README,
  in `docs/architecture.md` of the parent, and in the CHANGELOG in the
  same pull request.
- A decision, a rejected alternative or a workaround goes to `context/`
  of the repository it belongs to; family-wide ones to the parent via
  Agent A.
- The README's "run locally", "test", "build" and "deploy" sections are
  verified by actually running them before a PR, not by reading them.
- Nothing describes a planned state as current. Planned is marked
  planned.
