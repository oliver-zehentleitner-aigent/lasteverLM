-- lasteverLM rag: messages and outputs.
-- Applied by infra's `make migrate` after core (usage), account (ledger) and
-- ingest (notebooks, sources, chunks). One transaction per file; an applied
-- file is never edited, a change is a new numbered file. No vector column
-- here (chunks belong to ingest), so EMBEDDING_DIMENSION is not used.

begin;

create table if not exists messages (
    id           uuid primary key,
    notebook_id  uuid not null references notebooks (id) on delete cascade,
    role         text not null check (role in ('user', 'assistant')),
    content      text not null,
    citations    jsonb,
    created_at   timestamptz not null default now()
);
create index if not exists messages_notebook_idx on messages (notebook_id, created_at);

create table if not exists outputs (
    id           uuid primary key,
    notebook_id  uuid not null references notebooks (id) on delete cascade,
    kind         text not null check (kind in ('report', 'quiz', 'table', 'mindmap', 'infographic', 'audio')),
    title        text not null default '',
    content      jsonb,
    status       text not null check (status in ('waiting', 'processing', 'ready', 'failed')),
    error        text,
    share_token  text unique,
    -- the source of kind 'generated' that holds this output's chunks once it is ready;
    -- deleting the output deletes that source (service logic, the row cascade is the other way)
    source_id    uuid references sources (id) on delete set null,
    -- the table doubles as the job queue for the worker entrypoint: a worker claims a
    -- waiting/processing row with FOR UPDATE SKIP LOCKED, stamps itself here and counts
    -- the attempt; a claim older than ten minutes is abandoned, three attempts fail the row
    claimed_at   timestamptz,
    claimed_by   text,
    attempts     int not null default 0,
    created_at   timestamptz not null default now()
);
create index if not exists outputs_notebook_idx on outputs (notebook_id, created_at);
create index if not exists outputs_queue_idx on outputs (created_at) where status in ('waiting', 'processing');

commit;
