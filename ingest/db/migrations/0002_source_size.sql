-- lasteverLM ingest: the size of a source's stored object, for the admin
-- statistics (GET /api/ingest/admin/stats). Rows created before this
-- migration keep null and count as 0 bytes.
alter table sources add column if not exists size_bytes bigint;
