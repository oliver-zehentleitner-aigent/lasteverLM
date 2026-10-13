-- lasteverLM ingest: a trash for the source library.
-- DELETE /library/{id} sets deleted_at and removes the entry's links; the
-- entry, its chunks and its object stay until the owner's retention
-- (account's users.preferences->'trash_days', default 14) has elapsed,
-- then the worker's purge removes them. 0004 is reserved for the contract
-- step of 0003 and ships one release later.
alter table library_sources add column if not exists deleted_at timestamptz;
create index if not exists library_sources_trash_idx
    on library_sources (deleted_at) where deleted_at is not null;
