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
sources      (id, notebook_id, name, kind, storage_path, status, error, summary text null, created_at)
chunks       (id, source_id, notebook_id, idx, page, text, embedding vector(1536))

-- rag
messages     (id, notebook_id, role, content, citations jsonb, created_at)
outputs      (id, notebook_id, kind, title, content jsonb, status, error, share_token text null unique, created_at)

-- shared (owned by core's migration, applied first)
usage        (id, user_id, notebook_id null, service, kind, model,
              tokens_in, tokens_out, cost_cents, created_at)
```

- `sources.kind`: `pdf` | `text` | `url` | `image` | `generated` (`url` and `image` are later loaders, the column is ready; `generated` is a finished output indexed as a source by rag, see Outputs).
- `sources.status`: `processing` | `ready` | `failed`.
- `sources.summary`: one summary per source, written by ingest at the end of processing, used by the output generators.
- `outputs.kind`: `report` | `quiz` | `table` | `mindmap` | `infographic` | `audio`. `outputs.status`: `waiting` (sources still processing) | `processing` | `ready` | `failed`.
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

Status codes: `POST /notebooks` 201, `POST /notebooks/{id}/sources` 202, `DELETE` 204, `{"url"}` 501 until the url loader exists.

Processing runs after the upload response: store the file, parse,
chunk (about 800 tokens, 100 overlap), embed, insert chunks, set
`ready` or `failed` with `error`. The pipeline is the `worker`
entrypoint of the ingest package; in v1 it runs in-process as a
background task, later as its own pod with no code change. No queue in
v1; the frontend polls `GET /sources`.

### rag, prefix `/api/rag`

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/notebooks/{id}/ask` | `{"question", "scope": {"output_id"}?}` | `Answer` |
| GET | `/notebooks/{id}/messages` | | `[Message]` |
| POST | `/notebooks/{id}/outputs` | `{"kind"}` | 202 `Output` with status `waiting` or `processing` |
| GET | `/notebooks/{id}/outputs` | | `[Output]` |
| GET | `/outputs/{id}` | | `Output` |
| DELETE | `/outputs/{id}` | | 204 |
| POST | `/outputs/{id}/share` | | `{"share_token"}` |
| DELETE | `/outputs/{id}/share` | | 204 |
| GET | `/shared/{token}` | no auth | `Output` without ids, read-only |
| GET | `/healthz` | | `{"status": "ok"}` |

```json
Answer:   {"message_id", "answer", "citations": [Citation]}
Citation: {"n", "source_id", "source_name", "source_kind", "chunk_id", "page", "quote"}
Message:  {"id", "role", "content", "citations", "created_at"}
Output:   {"id", "notebook_id", "kind", "title", "content", "status", "error", "share_token", "created_at"}
```

`scope.output_id` restricts retrieval to the chunks of one generated
document ("ask about this"). `source_kind` lets the frontend render a
citation into a PDF differently from one into a generated report.

Citations are built by rag, not by the provider: retrieved chunks go
numbered into the prompt, the model answers with `[n]` markers, rag maps
every marker back to its chunk and drops markers that point at nothing.
Retrieval: top-k (8) by cosine similarity over `chunks`, filtered by
`notebook_id` and sources with status `ready`; a similarity floor from
config. If nothing passes the floor, the answer says that the sources do
not cover the question and `citations` is empty. The service never
answers from model knowledge alone.

## Outputs (generated documents)

An output is a document generated from a notebook's sources: a report,
a quiz, a data table, a mind map, an infographic, or an audio version.
The rag service owns them. One interface, `OutputGenerator`, one module
per kind, each with a prompt, an output schema and a renderer in web.

| Kind | `content` | Rendered as |
|---|---|---|
| `report` | `{"markdown"}` | Markdown document |
| `quiz` | `{"questions": [{"question", "options", "answer", "explanation"}]}` | interactive quiz with reveal |
| `table` | `{"columns": [], "rows": [[]]}` | sortable table, CSV export |
| `mindmap` | `{"root": {"label", "children": []}}` | markmap in the browser |
| `infographic` | `{"headline", "facts": [{"label", "value"}], "sections": [{"title", "text"}]}` | card grid |
| `audio` | `{"url"}` | audio player; only if the inference platform offers text-to-speech, otherwise the module stays prepared |

How a generator gets its input: every source carries a `summary`
written by ingest; the generator takes all summaries of the notebook
plus the top-k chunks for its own focus query. That keeps large
notebooks inside the context window.

Lifecycle: `POST /outputs` creates the row with status `waiting` when
any source of the notebook is still processing, otherwise `processing`;
a background task waits for the sources, generates, writes `ready` or
`failed`. Every generation writes a `usage` row. When an output is
ready, rag chunks and embeds its text as a source of kind `generated`
in the same notebook, so the chat can answer questions about generated
documents and cite them. Deleting an output deletes that source.

Sharing: `POST /outputs/{id}/share` sets a random `share_token`; the
page `/s/<token>` in web renders `GET /api/rag/shared/<token>` without
login, read-only, and records a visit. `DELETE .../share` revokes it.
Printing is a print stylesheet on the viewer; the browser produces the
PDF. Audio, mind map and infographic are not printed as images; the
report and the table are the printable kinds.

## Model prices

`MODEL_PRICES` is JSON: `{"<model>": {"in": <cents per million tokens>, "out": <cents per million tokens>}}`;
`cost_cents = ceil((tokens_in * in + tokens_out * out) / 1e6)`. Core
ships defaults for the models on the platform; a service refuses to
start when its configured model has no price (fail loud). Until the
defaults exist, every deployment sets `MODEL_PRICES`.

## Configuration

| Variable | Used by |
|---|---|
| `DATABASE_URL` | account, ingest, rag |
| `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` | ingest |
| `INFERENCE_BASE_URL`, `INFERENCE_API_KEY` | ingest, rag |
| `LLM_MODEL` | ingest (source summaries), rag |
| `SIMILARITY_FLOOR`, `TTS_MODEL` (optional) | rag |
| `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION` | ingest, rag (identical on both) |
| `MODEL_PRICES` | ingest, rag (JSON; defaults in core) |
| `AUTH_JWT_SECRET` | account (issues), ingest, rag (verify) |
| `DEMO_TOKEN` | all services; unset in production |
| `PUBLIC_BASE_URL`, `AUTH_ALLOWED_DOMAINS`, `ADMIN_EMAILS`, `SMTP_*` (seed only) | account |
| `API_BASE_URL` | web (build time) |

## Runtime contract

- Images `<registry>/lasteverlm-<service>:<git-sha>` for account, ingest, rag, web. The registry host is a variable in manifests and build workflows (decision pending: Vultr Container Registry or ghcr.io).
- API services listen on 8000 and answer `GET /healthz` with `{"status": "ok"}` at the root (what Kubernetes probes) and under their prefix (what the ingress exposes); web serves on 8080, `GET /` is 200. Services receive the full request path including their prefix.
- Containers run as non-root (`runAsNonRoot: true`); every Dockerfile sets a `USER`.
- Configuration: ConfigMap `lasteverlm-config` (PUBLIC_BASE_URL, S3_ENDPOINT, S3_BUCKET, INFERENCE_BASE_URL, LLM_MODEL, EMBEDDING_MODEL, EMBEDDING_DIMENSION, SIMILARITY_FLOOR, MODEL_PRICES). Secrets per concern: `lasteverlm-db` (DATABASE_URL, app role, `sslmode=require`), `lasteverlm-s3` (ingest), `lasteverlm-inference` (ingest, rag), `lasteverlm-auth` (AUTH_JWT_SECRET, DEMO_TOKEN), `lasteverlm-account` (AUTH_ALLOWED_DOMAINS, ADMIN_EMAILS), optional `lasteverlm-smtp-seed`. Account gets neither S3 nor inference.
- Migrations: each service keeps `db/migrations/NNNN_<topic>.sql`; `make migrate` applies infra, core, account, ingest, rag in that order, one transaction per file, version key `<service>/NNNN_<topic>` in `schema_migrations`, never edit an applied file. The psql variable `:EMBEDDING_DIMENSION` is passed on every run. `CREATE EXTENSION vector` is infra's own first migration; services never create extensions.

## Deployment

One namespace `lasteverlm` on a Vultr Kubernetes cluster. One
Deployment and one ClusterIP Service per application service plus web,
ingress-nginx with TLS in front, path routing per the prefixes above
and `/` to web. Images are built per repository and tagged with the Git
SHA. Secrets are created from the environment by `make secrets` and
never committed. `make migrate` applies every service's migrations in
order: infra, core, account, ingest, rag. The cluster runs in Frankfurt;
Object Storage has no Frankfurt location and lives in Amsterdam.

## Extension points, by design

| Later feature | Where it goes | What stays untouched |
|---|---|---|
| URL and image sources | one more `SourceLoader` in ingest | API, schema, rag, web beyond a kind label |
| another LLM or embedding provider | one more provider module in core, selected by config | every service |
| hybrid retrieval (full text + vector) | one more `Retriever` in rag | ingest, web |
| another output kind | one more `OutputGenerator` in rag plus its renderer in web | ingest, account, the API |
| audio outputs | the prepared `audio` generator once a text-to-speech endpoint exists | everything else |
| separate ingest worker pod | a second Deployment of the same image with the `worker` entrypoint | ingest code |
| password or OAuth login | one more auth scheme in account and core's `current_user` | ingest, rag, web beyond the login page |
