# AGENTS.md

lasteverLM is a NotebookLM-style assistant: upload documents, ask
questions, get cited answers, turn sources into documents. This is one
repository for the whole system. The root is the umbrella: architecture,
family-wide reasoning, task board, workflows. Each directory below is a
service with its own `context/`:

| Directory | Owner | Scope |
|---|---|---|
| `/` (root) | Agent A | architecture, API contract, family-wide `context/`, task board, review and merge until the prototype |
| `core/` | Agent G | shared Python library: models, settings, auth resolution, rate-limit middleware, usage accounting, provider interfaces |
| `account/` | Agent F | magic-link login, allowed domains, vouchers, credit balance, admin panel backend, visitor and access logs, blocks and bans |
| `infra/` | Agent B | Vultr cluster, Helm chart, ingress, migrations runner, deploy automation, smoke test, the workflows in `.github/` |
| `ingest/` | Agent C | upload, parsing, chunking, embeddings, source summaries, notebook and source endpoints, ingest worker |
| `rag/` | Agent D | retrieval, cited answers, message history, generated outputs, sharing, rag worker |
| `web/` | Agent E | wizard, two-column notebook view, viewer, login, credits, admin panel |

- How the system fits together: `docs/architecture.md` (read it before writing code against another service)
- How the interface works: `docs/ui.md`
- What every repository must contain and keep current: `docs/repository-standard.md`
- Why it is built this way: `context/index.md`
- What is open and who does what: `TASKS.md`
- If `AGENTS.local.md` exists in this checkout, read that too: personal notes, not committed

## How we work

- Seven agent sessions run at the same time on one machine. Agent A manages, reviews and merges and writes no code. Agents B to G write code, one repository each.
- Every agent works in its own clone of the fork and touches only its own directory. Files outside it (root files, `.github/`) change through their owner: root files through Agent A, workflows through Agent B.
- All agents push through one shared GitHub account that holds forks. Commits are authored per agent: `git config user.name "OZ-AGENT_<letter>"` and `git config user.email "agent-<letter>@aigent.zehentleitner.co"`, set per repository, never globally. Branches are named `agent-<letter>/<topic>`. Work lands as a pull request from the fork against the maintainer's repository, `main` as base. Until the first prototype is accepted, Agent A reviews every pull request and merges it; after that the maintainer merges.
- Commit hygiene: a handful of meaningful commits per feature, one pull request per repository and milestone. Clean up before opening the PR.
- Before starting work and before opening a pull request: fetch `main`, read the root `context/index.md` and the `context/index.md` of every directory your service depends on and the topics you touch. Every repository keeps its own `context/` under Keep the Why from the first commit.
- Direct messages between sessions are for interface changes and blockers only. Status goes through Git.
- Whoever changes an interface another service depends on updates `docs/architecture.md` in a pull request here and tells the owner of the affected service.
- Family-wide reasoning (anything that is not one service's own concern) is handed to Agent A and recorded in the root `context/`. Each service directory keeps its own `context/` for its own decisions; the skill routes by the `children` block in the root `.keep-the-why`.
- Documentation is part of the change: README, CHANGELOG, `docs/` and `context/` are updated in the same pull request as the code they describe, and the run/test/build/deploy sections are verified by running them. See `docs/repository-standard.md`.
- Language: code, comments, commits, docs and `context/` in English.
- Secrets never enter a repository. Services read them from the environment; the cluster gets them as Kubernetes Secrets.

## Keep the Why

This project records the reasoning behind its code with the Keep the Why
skill (https://keepthewhy.com) — the `.keep-the-why` file at the project
root is its config. Before doing anything else in a session, whatever the
first request is about, load the skill: in Claude Code, invoke the
`keep-the-why` skill (Skill tool); in any other agent, read
`.claude/skills/keep-the-why/SKILL.md` and follow it, including the
`references/*.md` files it points to for the situation at hand.
