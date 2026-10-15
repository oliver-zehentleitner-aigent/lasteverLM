-- lasteverLM rag: what a waiting output holds of its owner's balance (expand
-- only): its estimated maximum charge, set at creation. A new action starts
-- only if the balance covers its own maximum plus every waiting output's and
-- every funded source read ingest still holds (library_sources.funded_cents).

alter table outputs add column if not exists reserved_cents numeric not null default 0;
