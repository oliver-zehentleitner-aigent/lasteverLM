-- lasteverLM rag: the support check of an assistant answer, as on generated
-- outputs: {"units": [{"text", "refs", "support"}], "check": {...}}.
-- Answers without citations and messages from before have none.

alter table messages add column if not exists support jsonb;
