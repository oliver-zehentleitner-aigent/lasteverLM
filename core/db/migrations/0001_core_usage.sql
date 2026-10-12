-- lasteverLM core: the shared `usage` table.
-- Applied by infra's `make migrate` after infra's extensions migration and
-- before account, ingest and rag, inside the runner's single transaction; an
-- applied file is never edited, a change is a new numbered file.
--
-- One row per LLM or embedding call, priced at write time by the service
-- that made the call (lasteverlm_core.record_usage). Usage rows are the
-- only debit: balance = sum(ledger.amount_cents) - sum(usage.cost_cents).
-- No foreign keys: `users` (account) and `notebooks` (ingest) are created
-- by later migrations, and a notebook's deletion must not erase what it
-- cost.


create table if not exists usage (
    id           uuid primary key default gen_random_uuid(),
    user_id      uuid not null,
    notebook_id  uuid,
    service      text not null check (service in ('ingest', 'rag')),
    kind         text not null check (kind in ('llm', 'embedding')),
    model        text not null,
    tokens_in    integer not null check (tokens_in >= 0),
    tokens_out   integer not null check (tokens_out >= 0),
    cost_cents   integer not null check (cost_cents >= 0),
    created_at   timestamptz not null default now()
);

-- The balance query sums per user; the admin panel sums per user as well.
create index if not exists usage_user_idx on usage (user_id, created_at desc);
create index if not exists usage_notebook_idx on usage (notebook_id) where notebook_id is not null;

