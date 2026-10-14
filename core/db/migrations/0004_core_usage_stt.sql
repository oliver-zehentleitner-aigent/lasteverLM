-- lasteverLM core: `usage.kind` gains 'stt' (ingest's audio sources).
-- For an stt row the priced unit is seconds of audio, rounded up per call:
-- tokens_in holds the seconds, tokens_out is 0, and MODEL_PRICES lists
-- STT_MODEL with "in" in cents per million seconds.

alter table usage drop constraint if exists usage_kind_check;
alter table usage add constraint usage_kind_check
    check (kind in ('llm', 'embedding', 'tts', 'stt'));
