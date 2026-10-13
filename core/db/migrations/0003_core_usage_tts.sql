-- lasteverLM core: `usage.kind` gains 'tts' (rag's audio output).
-- For a tts row the priced unit is input characters: tokens_in holds the
-- character count, tokens_out is 0, and MODEL_PRICES lists TTS_MODEL with
-- "in" in cents per million characters.
-- 0001 declared the check inline, so PostgreSQL named it usage_kind_check.

alter table usage drop constraint if exists usage_kind_check;
alter table usage add constraint usage_kind_check check (kind in ('llm', 'embedding', 'tts'));
