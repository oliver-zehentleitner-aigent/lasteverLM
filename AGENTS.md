# AGENTS.md

lasteverLM is a NotebookLM-style assistant: upload documents, ask
questions, get cited answers. This repository is the parent of the
lasteverLM family. It holds the architecture, the family-wide reasoning
and the coordination files. The code lives in the service repositories:

| Repository | Owner | Scope |
|---|---|---|
| `lasteverLM` (this one) | Agent A | architecture, API contract, family-wide `context/`, task board, review |
| `lasteverLM-infra` | Agent B | Vultr Kubernetes cluster, manifests, ingress, secrets handling, database migrations |
| `lasteverLM-ingest` | Agent C | upload, parsing, chunking, embeddings, notebook and source endpoints |
| `lasteverLM-rag` | Agent D | retrieval, LLM call with citations, ask and message endpoints |
| `lasteverLM-web` | Agent E | three-pane frontend: sources, chat, notes |

- How the system fits together: `docs/architecture.md` (read it before writing code against another service)
- Why it is built this way: `context/index.md`
- What is open and who does what: `TASKS.md`
- If `AGENTS.local.md` exists in this checkout, read that too: personal notes, not committed

## How we work

- Up to five agent sessions run at the same time on one machine. Agent A reviews and manages together with the maintainer. Agents B to E write code, one repository each.
- Every agent works in its own checkout. Never edit another agent's working tree.
- All agents push through one shared GitHub account that holds forks. Branches are named `agent-<letter>/<topic>`. Work lands as a pull request from the fork against the maintainer's repository, `main` as base. The maintainer merges, nobody else.
- Direct messages between sessions are for interface changes and blockers only. Status goes through Git.
- Whoever changes an interface another service depends on updates `docs/architecture.md` in a pull request here and tells the owner of the affected service.
- Family-wide reasoning (anything that is not one service's own concern) is handed to Agent A and recorded in this repository's `context/`. Each service repository keeps its own `context/` for its own decisions.
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
