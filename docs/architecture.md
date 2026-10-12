# Architecture

Status: draft v0, under review. Services are built against this document;
a change to a contract below is a pull request here first.

## Overview

```text
browser ── web (static SPA) ──┐
                              ▼
                     ingress-nginx (TLS, path routing)
                        │                 │
            /api/ingest/*            /api/rag/*
                        ▼                 ▼
                   ingest svc          rag svc
                        │                 │
                        └──── Supabase ───┘
                    Postgres + pgvector, Storage, Auth
                        │
                  LLM / embedding provider (external API)
```

- **web**: single-page app, served as static files from its own container.
- **ingest**: accepts sources, stores the file, parses, chunks, embeds, writes chunks. Owns notebooks and sources.
- **rag**: retrieves chunks for a notebook, asks the LLM, returns an answer with citations. Owns messages.
- **infra**: cluster, ingress, manifests, migrations. No application code.
- Services share the database, not code. The schema is the contract between them.

## Data model (Supabase Postgres)

```sql
notebooks (
  id uuid primary key,
  owner uuid not null,          -- auth user id, or the demo user
  title text not null,
  created_at timestamptz default now()
)

sources (
  id uuid primary key,
  notebook_id uuid references notebooks on delete cascade,
  name text not null,           -- file name or URL
  kind text not null,           -- 'pdf' | 'text' | 'url'
  storage_path text,            -- Supabase Storage object, null for url
  status text not null,         -- 'processing' | 'ready' | 'failed'
  error text,
  created_at timestamptz default now()
)

chunks (
  id uuid primary key,
  source_id uuid references sources on delete cascade,
  notebook_id uuid not null,    -- denormalized for one-filter retrieval
  idx int not null,             -- position within the source
  page int,                     -- pdf page, null otherwise
  text text not null,
  embedding vector(1536)        -- dimension follows the embedding provider decision
)

messages (
  id uuid primary key,
  notebook_id uuid references notebooks on delete cascade,
  role text not null,           -- 'user' | 'assistant'
  content text not null,
  citations jsonb,              -- see /ask response
  created_at timestamptz default now()
)
```

Storage bucket `sources`, object path `<notebook_id>/<source_id>/<name>`.

## API contract v0

All endpoints take `Authorization: Bearer <token>`. What the token is
(Supabase JWT or demo token) is an open decision; services verify it
through one function so the scheme can change in one place. All bodies
and responses are JSON unless stated. Errors: `{"error": "<message>"}`
with a 4xx/5xx status.

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

Processing runs as a background task after the upload response: store
file, parse, chunk (about 800 tokens, 100 overlap), embed, insert
chunks, set status `ready` or `failed` with `error`. No queue in v0;
sources are small and the frontend polls `GET /sources`.

### rag, prefix `/api/rag`

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/notebooks/{id}/ask` | `{"question"}` | `Answer` |
| GET | `/notebooks/{id}/messages` | | `[Message]` |
| GET | `/healthz` | | `{"status": "ok"}` |

```json
Answer: {
  "message_id", "answer",
  "citations": [
    {"n": 1, "source_id", "source_name", "chunk_id", "page", "quote"}
  ]
}
Message: {"id", "role", "content", "citations", "created_at"}
```

`answer` references citations inline as `[1]`, `[2]`; `n` maps the
marker to the citation. Retrieval: top-k (k=8) chunks by cosine
similarity, filtered by `notebook_id` and `status = 'ready'` sources.
If no chunk passes a similarity floor, the answer says so and
`citations` is empty; the service never answers from model knowledge
alone.

## Configuration

Every service reads its configuration from the environment and fails at
startup when a required value is missing:

| Variable | Used by |
|---|---|
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | ingest, rag |
| `SUPABASE_JWT_SECRET` or `DEMO_TOKEN` | ingest, rag (one of them, per the auth decision) |
| `LLM_API_KEY`, `LLM_MODEL` | rag |
| `EMBEDDING_API_KEY`, `EMBEDDING_MODEL` | ingest, rag (same model on both sides) |
| `API_BASE_URL` | web (build-time) |

## Deployment

One namespace `lasteverlm` on a Vultr Kubernetes cluster. One
Deployment and one ClusterIP Service per application service,
ingress-nginx with TLS in front, path routing per the prefixes above.
Images are built per repository and tagged with the Git SHA. Secrets are
created from the environment by the deploy step and never committed.
