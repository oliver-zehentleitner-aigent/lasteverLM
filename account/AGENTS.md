# AGENTS.md

`account/` is the account service of lasteverLM, owned by Agent F. The
architecture, API contract, task board and the rules for working across
services live at the repository root: read `../AGENTS.md` and
`../docs/architecture.md` before changing an endpoint or a table, because
the web frontend calls this API and ingest and rag read `users` and write
`usage`.

- Why this service is built the way it is: `context/index.md`
- How to run, configure and deploy it: `docs/`
- Family-wide reasoning (anything not only this service's concern) is handed to Agent A for the root `context/`, not recorded here.
- Language: code, comments, commits, docs and `context/` in English.
- Secrets never enter the repository. The service reads them from the environment and fails at startup when one is missing.

## Layout

```text
account/
src/lasteverlm_account/
├── main.py                app factory; wires settings, repository, mailer; error format
├── dev.py                 `make run-dev`: the API on in-memory storage, links on the console
├── config.py              Settings from the environment (SMTP_* and AUTH_ALLOWED_DOMAINS are seeds only)
├── contracts.py           local mirror of lasteverLM-core: User, JWT issue/verify, demo token
├── models.py              API schemas
├── service.py             business rules: login, allowlist, credits, admin, visits
├── repository.py          storage interface and records
├── repository_postgres.py PostgreSQL (psycopg 3, plain SQL)
├── repository_memory.py   in-memory, for tests and local runs
├── mail.py                SMTP mailer, config from the settings table
├── privacy.py             visitor hashing, daily salt, user-agent family, client IP
└── api/                   routers: auth, account (me, redeem, visits), admin, deps
db/migrations/             numbered SQL, applied by infra's make migrate after core's
Makefile                   check (ruff, mypy, pytest), run, run-dev, build (context: repository root)
tests/                     unit tests on the memory repository; test_postgres.py needs TEST_DATABASE_URL
```

## Keep the Why

This project records the reasoning behind its code with the Keep the Why
skill (https://keepthewhy.com) — the `.keep-the-why` file at the project
root is its config. Before doing anything else in a session, whatever the
first request is about, load the skill: in Claude Code, invoke the
`keep-the-why` skill (Skill tool); in any other agent, read
`.claude/skills/keep-the-why/SKILL.md` and follow it, including the
`references/*.md` files it points to for the situation at hand.
