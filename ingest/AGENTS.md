# AGENTS.md

lasteverLM-ingest is the ingest service of the lasteverLM family. It is
owned by Agent C. The family's architecture, API contract, task board and
the rules for working across repositories live in the parent repository:
https://github.com/oliver-zehentleitner/lasteverLM — read its `AGENTS.md`
and `docs/architecture.md` before changing an endpoint or the data this
service writes, because the rag service reads it.

- Why this service is built the way it is: `context/index.md`
- How to run, configure and deploy it: `docs/`
- Family-wide reasoning (anything not only this service's concern) is handed to Agent A, not recorded here.
- Language: code, comments, commits, docs and `context/` in English.
- Secrets never enter the repository. The service reads them from the environment and fails at startup when one is missing.

## Layout

```text
src/lasteverlm_ingest/
├── main.py          app factory; wires settings, repository, storage, providers, rate limit
├── config.py        Settings from the environment (shared parts via core)
├── auth.py          bearer-token dependency on core's current_user (account JWT or demo token)
├── repository.py    all PostgreSQL access (notebooks, sources, chunks, queue claim, usage via core)
├── storage.py       object storage for uploads (S3-compatible, boto3)
├── worker.py        claim loop and pipeline: load → parse → chunk → embed → summarize → ready
├── summarizer.py    one-paragraph summary per source on core's LLM interface
├── loaders/         pdf, text → passages; registry open for url and image
└── api/             routers: notebooks, sources, health
db/migrations/       notebooks, sources, chunks (plain SQL for psql)
tests/               unit tests against in-memory fakes; no network, no database, no bucket
```

Models, token resolution, chunking, usage accounting, model prices, the
provider implementations and the rate-limit middleware come from `core/`.

## Keep the Why

This project records the reasoning behind its code with the Keep the Why
skill (https://keepthewhy.com) — the `.keep-the-why` file at the project
root is its config. Before doing anything else in a session, whatever the
first request is about, load the skill: in Claude Code, invoke the
`keep-the-why` skill (Skill tool); in any other agent, read
`.claude/skills/keep-the-why/SKILL.md` and follow it, including the
`references/*.md` files it points to for the situation at hand.
