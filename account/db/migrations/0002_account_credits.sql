-- lasteverLM-account: credits. balance_cents = sum(ledger.amount_cents) - sum(usage.cost_cents).
-- The usage table is core's (applied before this file). Plain PostgreSQL, safe to re-run.

create table if not exists vouchers (
    id           uuid primary key,
    code_hash    text not null unique,   -- the plain code is shown once at creation
    amount_cents integer not null check (amount_cents > 0),
    created_by   uuid not null references users(id),
    redeemed_by  uuid references users(id),
    redeemed_at  timestamptz,
    created_at   timestamptz not null default now()
);

-- Credits only; usage rows are the debit side, there is no negative ledger row.
create table if not exists ledger (
    id           bigserial primary key,
    user_id      uuid not null references users(id) on delete cascade,
    amount_cents integer not null check (amount_cents > 0),
    reason       text not null,          -- 'voucher' | 'seed'
    voucher_id   uuid references vouchers(id),
    created_at   timestamptz not null default now()
);
create index if not exists ledger_user_id_idx on ledger (user_id);

-- Initial credit for the demo user, once.
insert into ledger (user_id, amount_cents, reason)
select '00000000-0000-4000-8000-000000000001', 1000, 'seed'
where not exists (
    select 1 from ledger
    where user_id = '00000000-0000-4000-8000-000000000001' and reason = 'seed'
);
