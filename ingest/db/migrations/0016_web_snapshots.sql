-- lasteverLM ingest: a snapshot of every fetched web page version.
-- snapshot_path is the inert HTML copy of what was read (stored beside the
-- source as `_snapshot.html`), final_url the address after redirects,
-- checked_at the last time a refetch compared the page (fetched_at stays
-- the time this version was fetched). Expand only: all nullable.
alter table library_sources add column if not exists snapshot_path text;
alter table library_sources add column if not exists final_url text;
alter table library_sources add column if not exists checked_at timestamptz;
