-- lasteverLM rag: an output job's journal of finished model calls (the generation, each
-- judge verdict and revision, the decision model, the focus embeddings),
-- keyed by request: a worker that takes the job over answers them from here
-- instead of calling and paying again. Cleared when the output is ready or
-- failed. Expand only: a new column with a default.
alter table outputs add column checkpoint jsonb not null default '{}'::jsonb;
