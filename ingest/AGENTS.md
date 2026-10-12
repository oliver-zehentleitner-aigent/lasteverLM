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
├── main.py          app factory; wires settings, repository, embedder
├── config.py        Settings from the environment
├── auth.py          one token check, demo token or Supabase JWT
├── models.py        API schemas (Notebook, Source)
├── repository.py    all Supabase access (tables and storage); chunking comes from core
├── pipeline.py      store → parse → chunk → embed → insert → status
├── parsing/         pdf, text, url → passages
├── embeddings/      EmbeddingProvider interface and implementations
└── api/             routers: notebooks, sources, health
tests/               unit tests; no network, no Supabase
```

## Keep the Why

This project records the reasoning behind its code with the Keep the Why
skill (https://keepthewhy.com) — the `.keep-the-why` file at the project
root is its config. Before doing anything else in a session, whatever the
first request is about, load the skill: in Claude Code, invoke the
`keep-the-why` skill (Skill tool); in any other agent, read
`.claude/skills/keep-the-why/SKILL.md` and follow it, including the
`references/*.md` files it points to for the situation at hand.
