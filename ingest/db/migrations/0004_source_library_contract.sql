-- lasteverLM ingest: the per-user source library (contract step of 0003).
--
-- 0003 moved everything a source was onto `library_sources` and kept the
-- old columns nullable, so pods of the release before it kept working
-- during the rolling deploy. Every pod now reads and writes only the
-- library columns; this drops the old ones. Ship it in a release after
-- the one that shipped 0003, never together with it.
--
-- A source an old pod inserted after 0003 ran (during that rollout) has
-- no library row yet: the backfill of 0003 runs once more first, so the
-- not-null constraints below hold for every row.

-- Conditional, so that running this file again (the columns are gone)
-- is a no-op like every other migration here.
do $$
begin
    if exists (select 1 from information_schema.columns
                where table_schema = current_schema() and table_name = 'sources'
                  and column_name = 'name') then
        insert into library_sources (id, owner, name, kind, url, size_bytes, storage_path,
                                     status, error, summary, claimed_at, claimed_by, attempts,
                                     created_at)
        select s.id, n.owner, s.name, s.kind,
               case when s.kind = 'url' then s.name end,
               case when s.kind = 'url' then null else s.size_bytes end, s.storage_path,
               s.status, s.error, s.summary, s.claimed_at, s.claimed_by, s.attempts,
               s.created_at
          from sources s
          join notebooks n on n.id = s.notebook_id
         where s.library_source_id is null
        on conflict (id) do nothing;
        update sources set library_source_id = id where library_source_id is null;
    end if;
    if exists (select 1 from information_schema.columns
                where table_schema = current_schema() and table_name = 'chunks'
                  and column_name = 'source_id') then
        update chunks set library_source_id = source_id
         where library_source_id is null and source_id is not null;
    end if;
end
$$;

alter table sources alter column library_source_id set not null;
-- The old queue index goes with the status column; the queue is
-- library_sources_queue_idx since 0003.
alter table sources
    drop column if exists name,
    drop column if exists kind,
    drop column if exists storage_path,
    drop column if exists status,
    drop column if exists error,
    drop column if exists summary,
    drop column if exists claimed_at,
    drop column if exists claimed_by,
    drop column if exists attempts,
    drop column if exists size_bytes;

alter table chunks alter column library_source_id set not null;
-- Their indexes (chunks_notebook_idx, chunks_source_idx) go with them.
alter table chunks
    drop column if exists source_id,
    drop column if exists notebook_id;
