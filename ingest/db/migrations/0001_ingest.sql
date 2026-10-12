-- lasteverLM ingest: notebooks, sources, chunks.
-- Applied by infra's `make migrate` after infra's extensions migration
-- (which creates the `vector` extension; services never create extensions,
-- the application role has no right to) and core's migration (`usage`).
-- One transaction per file; an applied file is never edited, a change is
-- a new numbered file. The embedding dimension is a psql variable so it
-- follows EMBEDDING_DIMENSION:
--   psql "$DATABASE_URL" -v EMBEDDING_DIMENSION="$EMBEDDING_DIMENSION" -f 0001_ingest.sql
-- Without the variable it defaults to 1536.

\if :{?EMBEDDING_DIMENSION}
\else
\set EMBEDDING_DIMENSION 1536
\endif

begin;

create table if not exists notebooks (
    id          uuid primary key,
    owner       uuid not null,
    title       text not null,
    created_at  timestamptz not null default now()
);
create index if not exists notebooks_owner_idx on notebooks (owner, created_at desc);

create table if not exists sources (
    id            uuid primary key,
    notebook_id   uuid not null references notebooks (id) on delete cascade,
    name          text not null,
    kind          text not null check (kind in ('pdf', 'text', 'url', 'image', 'generated')),
    storage_path  text,
    status        text not null check (status in ('processing', 'ready', 'failed')),
    error         text,
    summary       text,
    claimed_at    timestamptz,                 -- set by the worker that took the job
    claimed_by    text,                        -- its id (host:pid); stays as a trace
    attempts      integer not null default 0,  -- claims so far; failed for good after three
    created_at    timestamptz not null default now()
);
create index if not exists sources_notebook_idx on sources (notebook_id, created_at);
-- The work queue: unclaimed or stale `processing` rows, oldest first.
create index if not exists sources_queue_idx on sources (created_at) where status = 'processing';

create table if not exists chunks (
    id           uuid primary key,
    source_id    uuid not null references sources (id) on delete cascade,
    notebook_id  uuid not null,
    idx          integer not null,
    page         integer,
    text         text not null,
    embedding    vector(:EMBEDDING_DIMENSION) not null
);
-- Retrieval filters by notebook first; the vector index is per the rag
-- service's needs and is added by a later migration once data volume asks for it.
create index if not exists chunks_notebook_idx on chunks (notebook_id);
create index if not exists chunks_source_idx on chunks (source_id, idx);

commit;
