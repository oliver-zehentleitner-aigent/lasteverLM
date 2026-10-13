-- lasteverLM rag: the generation options an output was made with
-- (language for every kind; voice and speed for audio), as resolved at
-- creation, so the viewer can show them. Outputs from before have none.

alter table outputs add column if not exists options jsonb not null default '{}'::jsonb;
