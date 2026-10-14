-- lasteverLM rag: copying a starter notebook's outputs into a new user's copy.
--
-- Ingest copies the starter notebook (uploads, links, chunks, objects) for a
-- new user and, in the same transaction, inserts one row here with its id
-- maps. rag's worker claims the row, copies the starter's ready outputs
-- (rows, generated library rows with links and chunks, audio objects),
-- remaps the ids in their provenance and deletes the row. No model call.

create table if not exists output_copies (
    target_notebook uuid primary key references notebooks (id) on delete cascade,
    source_notebook uuid not null,
    owner           uuid not null,
    -- old link id -> new link id, and old library_sources.id -> new
    source_map      jsonb not null default '{}'::jsonb,
    -- old chunks.id -> new chunks.id, the copied uploads' chunks
    chunk_map       jsonb not null default '{}'::jsonb,
    created_at      timestamptz not null default now(),
    claimed_at      timestamptz,
    claimed_by      text,
    attempts        integer not null default 0,
    error           text
);

-- The starter output a copy came from: at most one copy per notebook, so a
-- copy run again (a retry, a worker taken over) adds nothing twice.
alter table outputs add column if not exists copied_from uuid;
create unique index if not exists outputs_copied_from_idx
    on outputs (notebook_id, copied_from) where copied_from is not null;
