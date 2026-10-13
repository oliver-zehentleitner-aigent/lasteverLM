-- lasteverLM-account: sign-in attempts, allowed and refused, with the plain client IP.
-- Plain PostgreSQL, safe to re-run.

-- Unlike visit_log this keeps the raw address: a refused sign-in is a security event an
-- admin wants to attribute (context/privacy.md). Rows older than RETENTION_DAYS are
-- deleted at service start, like core's access_log.
create table if not exists login_attempts (
    id      bigserial primary key,
    at      timestamptz not null default now(),
    email   text not null,
    ip      inet not null,
    outcome text not null check (outcome in ('allowed', 'refused'))
);
create index if not exists login_attempts_at_idx on login_attempts (at desc);
