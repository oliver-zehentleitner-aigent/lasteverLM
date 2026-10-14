-- lasteverLM ingest: a source is read when it is used, not when it is added.
-- An upload, URL or text is stored as 'added' (not read yet); no worker
-- claims it until POST /sources/process (rag before an answer or an
-- output, the web's "read now") moves it to 'processing'. Expand only:
-- pods of the previous release keep inserting 'processing' and their
-- workers keep claiming only 'processing'. 0003 declared the check inline,
-- so PostgreSQL named it library_sources_status_check.
alter table library_sources drop constraint if exists library_sources_status_check;
alter table library_sources add constraint library_sources_status_check
    check (status in ('added', 'processing', 'ready', 'failed'));
