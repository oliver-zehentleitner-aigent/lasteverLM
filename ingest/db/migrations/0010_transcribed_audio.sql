-- lasteverLM ingest: the converted recording of an audio source.
-- An audio source in a format the transcription model does not take
-- (M4A, Ogg, FLAC, WebM, ...) is converted to MP3 by the worker; that
-- file is stored beside the original and is what was transcribed. Null
-- for MP3 and WAV (transcribed as uploaded) and every other kind.
alter table library_sources add column if not exists transcribed_path text;
