-- lasteverLM ingest: the per-user source library (expand step).
--
-- A library source is what a user uploaded or entered once (a file, an
-- image, a URL), processed once, with one set of chunks. `sources` becomes
-- the link of a library source into a notebook; its id stays the public
-- source id (Source JSON, citations). Chunks hang on the library source and
-- are searched from every notebook that links it. Outputs indexed by rag
-- get a library row of kind 'generated' that is never listed.
--
-- Expand only: the moved columns on `sources` and `chunks.notebook_id` /
-- `chunks.source_id` stay (nullable) so pods of the previous release keep
-- working during the rolling deploy; 0004, one release later, drops them.
-- Existing rows keep their ids: every old source gets a library row with
-- the same id, so library_source_id = source id for all of them.

create table if not exists library_sources (
    id            uuid primary key,
    owner         uuid not null,
    name          text not null,
    kind          text not null check (kind in ('pdf', 'text', 'url', 'image', 'generated')),
    -- 'sha256:<hex>' of the bytes, or 'url:<normalised url>'; null for
    -- generated rows and for rows from before this migration
    dedupe_key    text,
    url           text,                        -- url kind only
    size_bytes    bigint,                      -- stored object size; null for urls
    storage_path  text,
    status        text not null check (status in ('processing', 'ready', 'failed')),
    error         text,
    summary       text,
    claimed_at    timestamptz,
    claimed_by    text,
    attempts      integer not null default 0,
    created_at    timestamptz not null default now()
);
create unique index if not exists library_sources_dedupe_idx
    on library_sources (owner, dedupe_key) where dedupe_key is not null;
create index if not exists library_sources_owner_idx on library_sources (owner, created_at desc);
-- The work queue moves here: unclaimed or stale `processing` rows, oldest first.
create index if not exists library_sources_queue_idx
    on library_sources (created_at) where status = 'processing';

insert into library_sources (id, owner, name, kind, url, size_bytes, storage_path, status,
                             error, summary, claimed_at, claimed_by, attempts, created_at)
select s.id, n.owner, s.name, s.kind,
       case when s.kind = 'url' then s.name end,
       case when s.kind = 'url' then null else s.size_bytes end, s.storage_path, s.status, s.error, s.summary,
       s.claimed_at, s.claimed_by, s.attempts, s.created_at
  from sources s
  join notebooks n on n.id = s.notebook_id
on conflict (id) do nothing;

alter table sources add column if not exists library_source_id uuid
    references library_sources (id) on delete cascade;
update sources set library_source_id = id where library_source_id is null;
create unique index if not exists sources_link_idx on sources (notebook_id, library_source_id);
alter table sources alter column name drop not null;
alter table sources alter column kind drop not null;
alter table sources alter column status drop not null;

alter table chunks add column if not exists library_source_id uuid
    references library_sources (id) on delete cascade;
update chunks set library_source_id = source_id where library_source_id is null;
create index if not exists chunks_library_idx on chunks (library_source_id, idx);
-- Chunks no longer die with a link: detaching keeps them, only deleting
-- the library source removes them.
alter table chunks drop constraint if exists chunks_source_id_fkey;
alter table chunks alter column source_id drop not null;
alter table chunks alter column notebook_id drop not null;
