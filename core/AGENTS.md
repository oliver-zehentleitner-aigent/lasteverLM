# AGENTS.md

`core/` is the shared Python library of lasteverLM, owned by Agent G. The
account, ingest and rag services import it. The family's architecture,
API contract, task board and the rules for working across directories
live at the repository root: read `../AGENTS.md` and
`../docs/architecture.md` before changing anything exported here,
because three services depend on it.

- Why this library is built the way it is: `context/index.md`
- How a service uses it: `README.md`, `docs/README.md`
- Family-wide reasoning (anything not only this library's concern) is handed to Agent A, not recorded here.
- Language: code, comments, commits, docs and `context/` in English.
- Core reads nothing on import and holds no secret. The `from_env` loaders are called by the services at startup and fail loud.

## Layout

```text
src/lasteverlm_core/
├── __init__.py      the public surface, re-exported
├── models.py        API models of the contract, kind/status literals, DEMO_USER_ID
├── settings.py      ConfigError, env helpers, InferenceSettings, load_model_prices
├── auth.py          current_user, issue_jwt, verify_jwt, AuthSettings
├── pricing.py       ModelPrice, parse_model_prices, cost_cents, require_prices
├── usage.py         record_usage, balance_cents (+ async), SQL constants
├── chunking.py      Passage, Chunk, TokenWindowChunker (420/50 regex tokens) shared by ingest and rag
├── ratelimit.py     rules, ASGI middleware, PostgreSQL and memory stores, purge, lift_ban
├── storage.py       S3Storage (put, get, delete, presigned GET), S3Settings, object_key
└── providers/       Embedder, LLM, TextToSpeech interfaces; OpenAI-compatible implementations
db/migrations/       usage (+ tts kind); access_log, ip_blocks, ip_bans
tests/               unit tests against fakes; no database, no network
```

## Keep the Why

This project records the reasoning behind its code with the Keep the Why
skill (https://keepthewhy.com) — the `.keep-the-why` file at the project
root is its config. Before doing anything else in a session, whatever the
first request is about, load the skill: in Claude Code, invoke the
`keep-the-why` skill (Skill tool); in any other agent, read
`.claude/skills/keep-the-why/SKILL.md` and follow it, including the
`references/*.md` files it points to for the situation at hand.
