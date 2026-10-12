# AGENTS.md

`infra/` is the infrastructure directory of lasteverLM: Vultr
resources, the Helm chart, the migration runner, the deploy procedure
and the repository's workflows. No application code. Owner in the agent
fleet: Agent B. The repository root holds the architecture, the API
contract and the family-wide rules; read the root `AGENTS.md` and
`docs/architecture.md` before changing anything here.

- What is where and how to deploy: `README.md`, `docs/operations.md`
- Why it is built this way: `context/index.md`
- Contribution rules: `CONTRIBUTING.md`
- If `AGENTS.local.md` exists in this checkout, read that too: personal notes, not committed

## Rules specific to this repository

- Secrets never enter the repository. The `Makefile` reads them from the environment and creates Kubernetes Secrets; `build/` and `*.env` are ignored.
- Schema changes are new numbered files in `db/migrations/`; an applied migration is never edited.
- Anything a service depends on (ports, secret and ConfigMap names, worker commands, the schema) is an interface: it changes in the root `docs/architecture.md` first.
- The workflows in `../.github/workflows/` are owned here; nothing else outside `infra/` is.
- `make check` before every pull request.

## Keep the Why

This project records the reasoning behind its code with the Keep the Why
skill (https://keepthewhy.com) — the `.keep-the-why` file at the project
root is its config. Before doing anything else in a session, whatever the
first request is about, load the skill: in Claude Code, invoke the
`keep-the-why` skill (Skill tool); in any other agent, read
`.claude/skills/keep-the-why/SKILL.md` and follow it, including the
`references/*.md` files it points to for the situation at hand.
