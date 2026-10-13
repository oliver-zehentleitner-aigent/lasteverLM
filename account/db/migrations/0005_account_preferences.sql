-- lasteverLM-account: per-user preferences (ui_language, output_language, audio_voice).
-- Plain PostgreSQL, safe to re-run.

-- A jsonb column rather than a table: three optional scalars per user, read with the
-- user on every /me, never queried on their own. Keys absent or null mean "not set".
alter table users add column if not exists preferences jsonb not null default '{}'::jsonb;
