# AGENTS.md

`web/` is the frontend of lasteverLM, a NotebookLM-style assistant: upload
documents, ask questions, get cited answers and generated documents. The
architecture, the API contract, the UI spec and the family-wide reasoning
live at the repository root.

- What this service does and how to run it: `README.md`, `docs/`
- Why it is built this way: `context/index.md`
- The API contract it talks to: `../docs/architecture.md`; the screens: `../docs/ui.md` (read both before touching `src/api/` or the layout)
- If `AGENTS.local.md` exists in this checkout, read that too: personal notes, not committed

## How we work

- Owned by Agent E. Branches are named `agent-e/<topic>`; work lands as a pull request from the fork against the maintainer's repository, `main` as base. The maintainer merges, nobody else.
- The frontend talks only to the three API prefixes `/api/account`, `/api/ingest` and `/api/rag`. Nothing but `src/api/` calls `fetch`.
- An interface change another service depends on is changed in `../docs/architecture.md` in the same pull request, and the owner of the affected service is told.
- Family-wide reasoning goes to Agent A and the root `context/`; this directory's `context/` holds the frontend's own decisions.
- Language: code, comments, commits, docs, UI and `context/` in English.
- Secrets never enter the repository. The only configuration is `API_BASE_URL` at build time.

## Keep the Why

This directory records the reasoning behind its code with the Keep the Why
skill (https://keepthewhy.com) — the `.keep-the-why` file here is its
config, with the repository root as parent. Before doing anything else in
a session, whatever the first request is about, load the skill: in Claude
Code, invoke the `keep-the-why` skill (Skill tool); in any other agent,
read the skill's `SKILL.md` and follow it, including the `references/*.md`
files it points to for the situation at hand.
