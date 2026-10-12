-- lasteverLM-account: admin-editable settings and the privacy-preserving visitor log.
-- Plain PostgreSQL, safe to re-run.

create table if not exists settings (
    key        text primary key,         -- 'smtp' | 'allowed_domains'
    value      jsonb not null,
    updated_at timestamptz not null default now()
);

-- No raw IP, no full user agent: ip_hash is sha256(daily random salt || ip), the
-- salt lives only in process memory. Rows older than the retention window are
-- deleted at service start.
create table if not exists visit_log (
    id        bigserial primary key,
    at        timestamptz not null default now(),
    path      text not null,
    user_id   uuid,
    ip_hash   text not null,
    ua_family text not null
);
create index if not exists visit_log_at_idx on visit_log (at desc);
