# AGENTS.md

`rag/` is the rag service of lasteverLM: retrieval over one notebook's
chunks, answers with citations, the message history, the generated
documents and the worker that produces them. The architecture, the API
contract and the data model live in the repository root
(`docs/architecture.md`); read it before changing an endpoint or a query.

- How to build and test: `CONTRIBUTING.md`
- Why this service is built the way it is: `context/index.md` (family-wide reasoning is in the root's `context/`)
- What changed: `CHANGELOG.md`

## Working here

- One checkout per agent; branches `agent-<letter>/<topic>`; pull requests against `main` of the maintainer's repository, the maintainer merges.
- A change to an interface another service depends on is agreed in the root's `docs/architecture.md` first.
- Code, comments, commits, docs and `context/` in English. Secrets come from the environment only.
- `ruff`, `mypy` and `pytest` must pass before a pull request.

## Keep the Why

This project records the reasoning behind its code with the Keep the Why
skill (https://keepthewhy.com) — the `.keep-the-why` file at the project
root is its config. Before doing anything else in a session, whatever the
first request is about, load the skill: in Claude Code, invoke the
`keep-the-why` skill (Skill tool); in any other agent, read
`.claude/skills/keep-the-why/SKILL.md` and follow it, including the
`references/*.md` files it points to for the situation at hand.
