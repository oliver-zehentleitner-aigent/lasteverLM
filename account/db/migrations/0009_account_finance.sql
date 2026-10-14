-- lasteverLM-account: infrastructure costs and paid vouchers, for the finance pages.
-- Plain PostgreSQL, safe to re-run.

-- One row per month (date = first day), source and item. 'vultr' rows are upserted by the
-- daily billing sync (pending charges for the running month, invoice items for closed
-- ones); 'manual' rows are entered by an admin. Amounts in the currency as billed.
create table if not exists infra_costs (
    id           uuid primary key,
    date         date not null,
    source       text not null check (source in ('vultr', 'manual')),
    item         text not null,
    amount_cents integer not null check (amount_cents >= 0),
    currency     text not null check (currency in ('USD', 'EUR')),
    updated_at   timestamptz not null default now(),
    unique (date, source, item)
);
create index if not exists infra_costs_date_idx on infra_costs (date);

-- A paid voucher was sold for money; a free one is a gift. Revenue counts only paid ones.
alter table vouchers add column if not exists paid boolean not null default false;
