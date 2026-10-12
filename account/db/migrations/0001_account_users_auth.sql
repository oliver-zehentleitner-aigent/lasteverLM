-- lasteverLM-account: users, login log, magic links, demo user.
-- Plain PostgreSQL, safe to re-run.

create table if not exists users (
    id            uuid primary key,
    email         text not null unique,
    is_admin      boolean not null default false,
    created_at    timestamptz not null default now(),
    last_login_at timestamptz
);

create table if not exists login_log (
    id      bigserial primary key,
    user_id uuid not null references users(id) on delete cascade,
    at      timestamptz not null default now()
);
create index if not exists login_log_at_idx on login_log (at desc);

-- Only the hash of the single-use token is stored; the token itself is in the mail.
create table if not exists magic_links (
    id         uuid primary key,
    user_email text not null,
    token_hash text not null unique,
    expires_at timestamptz not null,
    used_at    timestamptz,
    created_at timestamptz not null default now()
);
create index if not exists magic_links_expires_at_idx on magic_links (expires_at);

-- The demo user every caller of DEMO_TOKEN resolves to (family API contract).
-- Never an admin, never able to log in by mail (the address is not routable).
insert into users (id, email, is_admin)
values ('00000000-0000-4000-8000-000000000001', 'demo@localhost', false)
on conflict (id) do nothing;
