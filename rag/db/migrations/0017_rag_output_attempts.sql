-- lasteverLM rag: an output's failed attempts and when it ended (expand
-- only). attempt_log is one record per failed attempt: when, which attempt,
-- the model in flight, the kind of failure, the provider's HTTP status and
-- the public error text; never a prompt or source text. Support reads it
-- after any deploy, which the pods' logs do not survive. finished_at is set
-- when the output becomes ready or failed; older rows have none.

alter table outputs add column if not exists attempt_log jsonb not null default '[]'::jsonb;
alter table outputs add column if not exists finished_at timestamptz;
