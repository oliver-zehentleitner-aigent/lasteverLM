-- lasteverLM ingest: web pages get versions.
-- A web page can be fetched again (POST /sources/{id}/refetch). The worker
-- compares the hash of the extracted text with `content_hash`: unchanged,
-- only `fetched_at` moves and nothing is charged; changed, a new library
-- row `version + 1` takes the dedupe key and every link, and the old row
-- stays read-only (`superseded_by` names its successor; hidden from the
-- library, its chunks kept so old citations stay checkable).
-- Expand only: every column is nullable or defaulted.
alter table library_sources add column if not exists version integer not null default 1;
alter table library_sources add column if not exists fetched_at timestamptz;
alter table library_sources add column if not exists content_hash text;
alter table library_sources add column if not exists refetch_requested_at timestamptz;
alter table library_sources add column if not exists superseded_by uuid
    references library_sources (id) on delete set null;
