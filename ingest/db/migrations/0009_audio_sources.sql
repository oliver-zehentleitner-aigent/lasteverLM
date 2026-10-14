-- lasteverLM ingest: audio library sources (MP3 and WAV recordings,
-- transcribed by the platform's speech-to-text model). Deduplicated by
-- the sha256 of their bytes like every other file.
-- 0003 declared the check inline, so PostgreSQL named it
-- library_sources_kind_check.
alter table library_sources drop constraint if exists library_sources_kind_check;
alter table library_sources add constraint library_sources_kind_check
    check (kind in ('pdf', 'text', 'url', 'image', 'audio', 'generated'));
