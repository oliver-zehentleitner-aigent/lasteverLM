-- lasteverLM ingest: what a source's reading will cost, known at upload.
-- page_count (PDFs) and duration_seconds (MP3 and WAV, as core's probe
-- measures them) are stored when the file is added, so the cost of reading
-- an unread source can be estimated before it is read. Null for other
-- kinds and for rows from before this migration (estimated as a range).
alter table library_sources add column if not exists page_count integer;
alter table library_sources add column if not exists duration_seconds numeric;
