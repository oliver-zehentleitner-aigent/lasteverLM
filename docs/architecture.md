# Architecture

Status: v1, the contract the services are built against. A change to a
contract below is a pull request here first, and the owner of every
affected service is told.

## Overview

Everything runs on one cloud account. Four application services and one
static frontend on a managed Kubernetes cluster, one managed PostgreSQL
with pgvector, one object storage bucket, one inference API for the
language model and the embeddings.

```text
browser ── web (static SPA) ────────────┐
                                        ▼
                         ingress-nginx (TLS, path routing)
                 │                │                │
          /api/account      /api/ingest        /api/rag
                 ▼                ▼                ▼
             account           ingest            rag
                 │                │                │
                 └────── Vultr Managed PostgreSQL + pgvector ──────┘
                                  │                │
                         Vultr Object Storage   Vultr Serverless Inference
                         (uploads, S3 API)      (OpenAI-compatible API)
```

| Part | Repository | Owner | Role |
|---|---|---|---|
| core | `lasteverLM-core` | Agent A | Python library: models, settings, auth, provider interfaces, usage accounting. Imported by account, ingest, rag. No service. |
| account | `lasteverLM-account` | Agent F | magic-link login, allowed domains, vouchers, credit balance, admin panel backend, visitor log |
| ingest | `lasteverLM-ingest` | Agent C | notebooks and sources: upload, parse, chunk, embed, store |
| rag | `lasteverLM-rag` | Agent D | retrieval, answer generation, citations, message history |
| web | `lasteverLM-web` | Agent E | three-pane frontend, login, credits, admin panel |
| infra | `lasteverLM-infra` | Agent B | cluster, ingress, manifests, migrations runner, secrets handling |

Rules that hold everywhere:

- **Services share the database, never each other's APIs.** The schema is the contract between them. There are no service-to-service HTTP calls.
- **Every stage is an interface with one implementation.** New source kinds, chunkers, embedding or LLM providers, retrievers are added as modules, never by editing callers.
- **Configuration from the environment only.** A service fails at startup when a required value is missing. Secrets never enter a repository.
- **Every model call is accounted.** One `usage` row per LLM or embedding call, priced at write time. Zero balance means 402.

## Platform (Vultr)

| Need | Service | Notes |
|---|---|---|
| Cluster | Vultr Kubernetes Engine | one namespace `lasteverlm`, ingress-nginx, cert-manager with Let's Encrypt |
| Database, vectors | Vultr Managed PostgreSQL | extension is named `vector`: `CREATE EXTENSION IF NOT EXISTS vector;` |
| Uploads | Vultr Object Storage | S3-compatible, one bucket, accessed with boto3 |
| LLM, embeddings | Vultr Serverless Inference | OpenAI-compatible, base URL `https://api.vultrinference.com/v1`, used through the OpenAI SDK so any compatible provider can replace it |
| Mail | external SMTP | configured in the admin panel, stored in the database; not a Vultr service |

## Data model (PostgreSQL)

All ids are `uuid`. All timestamps are `timestamptz default now()`.
Migrations are numbered SQL files, each service keeps the ones for its
own tables in `db/migrations/`, and infra applies all of them in one
`make migrate`. Plain SQL, no ORM-specific migration tooling.

```sql
-- account
users        (id, email unique, is_admin bool, created_at, last_login_at)
magic_links  (id, user_email, token_hash, expires_at, used_at, created_at)
vouchers     (id, code_hash unique, amount_cents, created_by, redeemed_by, redeemed_at, created_at)
ledger       (id, user_id, amount_cents, reason, voucher_id, created_at)      -- credits only, positive
settings     (key primary key, value jsonb, updated_at)                       -- smtp, allowed_domains
login_log    (id, user_id, at)
visit_log    (id, at, path, user_id null, ip_hash, ua_family)                 -- no raw IP, 30 days

-- ingest
notebooks    (id, owner uuid, title, created_at)
sources      (id, notebook_id, name, kind, storage_path, status, error, created_at)
chunks       (id, source_id, notebook_id, idx, page, text, embedding vector(1536))

-- rag
messages     (id, notebook_id, role, content, citations jsonb, created_at)

-- shared (owned by core's migration, applied first)
usage        (id, user_id, notebook_id null, service, kind, model,
              tokens_in, tokens_out, cost_cents, created_at)
```

- `sources.kind`: `pdf` | `text` | `url` | `image` (the last two are later loaders, the column is ready).
- `sources.status`: `processing` | `ready` | `failed`.
- `chunks.embedding` dimension follows `EMBEDDING_DIMENSION`; the migration takes it as a parameter, default 1536.
- `usage.kind`: `llm` | `embedding`. `usage.service`: `ingest` | `rag`.
- **Balance** = `sum(ledger.amount_cents) - sum(usage.cost_cents)` per user. Usage rows are the debit; there is no second ledger write.
- Storage object path: `<notebook_id>/<source_id>/<name>`.

## Credits and accounting

- Prices per model live in config (`MODEL_PRICES`, JSON, cents per million tokens, in and out), with defaults in core. The writer of a usage row prices it: `cost_cents = ceil(tokens_in * price_in + tokens_out * price_out)`.
- Core provides `record_usage(conn, user_id, notebook_id, service, kind, model, tokens_in, tokens_out)` and `balance_cents(conn, user_id)`. Services call these, never write `usage` by hand.
- A voucher is a single-use code; redeeming it writes one positive ledger row. Default amount 1000 cents.
- Before any model call a service checks `balance_cents > 0`, otherwise 402 `{"error": "credit exhausted"}`.

## Authentication

- Bearer token on every request. Two schemes, resolved by one function in core, `current_user(authorization) -> User`:
  - JWT, HS256 with `AUTH_JWT_SECRET`, `sub` = user id, 7 days, issued by account after a magic link.
  - `DEMO_TOKEN` from config, resolves to the demo user `00000000-0000-4000-8000-000000000001`, seeded by account's migration with email `demo@localhost` and an initial ledger credit. Exists for development and recorded demos; unset in production.
- Magic link: `POST /api/account/auth/request-link` always answers 202; the mail carries `<PUBLIC_BASE_URL>/auth/callback?token=...`; the frontend exchanges the token at `GET /api/account/auth/callback?token=...` for `{jwt, user}`. Tokens are stored hashed, single use, 15 minutes.
- Allowed e-mail domains live in `settings` (key `allowed_domains`), seeded once from `AUTH_ALLOWED_DOMAINS`, edited in the admin panel. Not in any repository.
- `is_admin`: the first user ever created, plus addresses in `ADMIN_EMAILS`.

## API contract v1

JSON in and out unless stated. Errors: `{"error": "<message>"}` with 4xx/5xx. 401 unauthenticated, 402 credit exhausted, 403 not admin, 404 not yours or missing.

### account, prefix `/api/account`

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/auth/request-link` | `{"email"}` | 202 |
| GET | `/auth/callback?token=` | | `{"jwt", "user": User}` |
| GET | `/me` | | `User` |
| POST | `/vouchers/redeem` | `{"code"}` | `User` |
| POST | `/visits` | `{"path"}` | 204 |
| GET | `/admin/users` | | `[AdminUser]` |
| GET | `/admin/logins?limit=` | | `[{"user_id","email","at"}]` |
| GET | `/admin/visits?days=` | | `[{"day","path","visits","unique"}]` |
| GET, PUT | `/admin/settings/smtp` | `Smtp` (password write-only) | `Smtp` without password |
| POST | `/admin/settings/smtp/test` | | 202 |
| GET, PUT | `/admin/settings/domains` | `{"allowed_domains": []}` | same |
| POST | `/admin/vouchers` | `{"amount_cents", "count"}` | `{"codes": []}` once |
| GET | `/healthz` | | `{"status": "ok"}` |

```json
User:      {"id", "email", "is_admin", "balance_cents", "created_at"}
AdminUser: {"id", "email", "is_admin", "created_at", "last_login_at", "balance_cents", "usage_cents"}
Smtp:      {"host", "port", "username", "password", "from_address", "starttls"}
```

### ingest, prefix `/api/ingest`

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/notebooks` | | `[Notebook]` |
| POST | `/notebooks` | `{"title"}` | `Notebook` |
| DELETE | `/notebooks/{id}` | | 204 |
| GET | `/notebooks/{id}/sources` | | `[Source]` |
| POST | `/notebooks/{id}/sources` | multipart `file`, or `{"url"}` | `Source` with `status: "processing"` |
| DELETE | `/sources/{id}` | | 204 |
| GET | `/healthz` | | `{"status": "ok"}` |

```json
Notebook: {"id", "title", "created_at"}
Source:   {"id", "notebook_id", "name", "kind", "status", "error", "created_at"}
```

Processing runs after the upload response: store the file, parse,
chunk (about 800 tokens, 100 overlap), embed, insert chunks, set
`ready` or `failed` with `error`. The pipeline is the `worker`
entrypoint of the ingest package; in v1 it runs in-process as a
background task, later as its own pod with no code change. No queue in
v1; the frontend polls `GET /sources`.

### rag, prefix `/api/rag`

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/notebooks/{id}/ask` | `{"question"}` | `Answer` |
| GET | `/notebooks/{id}/messages` | | `[Message]` |
| GET | `/healthz` | | `{"status": "ok"}` |

```json
Answer:   {"message_id", "answer", "citations": [Citation]}
Citation: {"n", "source_id", "source_name", "chunk_id", "page", "quote"}
Message:  {"id", "role", "content", "citations", "created_at"}
```

Citations are built by rag, not by the provider: retrieved chunks go
numbered into the prompt, the model answers with `[n]` markers, rag maps
every marker back to its chunk and drops markers that point at nothing.
Retrieval: top-k (8) by cosine similarity over `chunks`, filtered by
`notebook_id` and sources with status `ready`; a similarity floor from
config. If nothing passes the floor, the answer says that the sources do
not cover the question and `citations` is empty. The service never
answers from model knowledge alone.

## Configuration

| Variable | Used by |
|---|---|
| `DATABASE_URL` | account, ingest, rag |
| `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` | ingest |
| `INFERENCE_BASE_URL`, `INFERENCE_API_KEY` | ingest, rag |
| `LLM_MODEL`, `SIMILARITY_FLOOR` | rag |
| `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION` | ingest, rag (identical on both) |
| `MODEL_PRICES` | ingest, rag (JSON; defaults in core) |
| `AUTH_JWT_SECRET` | account (issues), ingest, rag (verify) |
| `DEMO_TOKEN` | all services; unset in production |
| `PUBLIC_BASE_URL`, `AUTH_ALLOWED_DOMAINS`, `ADMIN_EMAILS`, `SMTP_*` (seed only) | account |
| `API_BASE_URL` | web (build time) |

## Deployment

One namespace `lasteverlm` on a Vultr Kubernetes cluster. One
Deployment and one ClusterIP Service per application service plus web,
ingress-nginx with TLS in front, path routing per the prefixes above
and `/` to web. Images are built per repository and tagged with the Git
SHA. Secrets are created from the environment by `make secrets` and
never committed. `make migrate` applies every service's migrations in
order: core, account, ingest, rag.

## Extension points, by design

| Later feature | Where it goes | What stays untouched |
|---|---|---|
| URL and image sources | one more `SourceLoader` in ingest | API, schema, rag, web beyond a kind label |
| another LLM or embedding provider | one more provider module in core, selected by config | every service |
| hybrid retrieval (full text + vector) | one more `Retriever` in rag | ingest, web |
| separate ingest worker pod | a second Deployment of the same image with the `worker` entrypoint | ingest code |
| password or OAuth login | one more auth scheme in account and core's `current_user` | ingest, rag, web beyond the login page |
