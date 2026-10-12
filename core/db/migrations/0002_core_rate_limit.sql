-- lasteverLM core: access log, blocks and bans per client IP.
-- Applied by infra's `make migrate` after 0001_core_usage.sql, inside the
-- runner's single transaction; an applied file is never edited.
--
-- The fine layer of rate limiting (parent: docs/architecture.md, "Rate
-- limiting"): every API service's lasteverlm_core.RateLimitMiddleware
-- reads and writes these three tables, so all replicas share one view of
-- a client. Raw IPs live only here, for the security purpose; rows older
-- than the retention period are removed by lasteverlm_core.ratelimit.purge.
-- The account service reads them for the admin panel and lifts bans.


-- One row per request; /healthz is sampled. The sliding window of the
-- limiter is a count over (ip, at).
create table if not exists access_log (
    id        uuid primary key default gen_random_uuid(),
    at        timestamptz not null default now(),
    ip        inet not null,
    path      text not null,
    method    text not null,
    status    integer not null,
    user_id   uuid,
    service   text not null
);
create index if not exists access_log_ip_at_idx on access_log (ip, at desc);
create index if not exists access_log_at_idx on access_log (at);

-- Over the limit: blocked for BLOCK_MINUTES and one strike. updated_at is
-- the time of the last strike; strikes restart after the strike window.
create table if not exists ip_blocks (
    ip             inet primary key,
    blocked_until  timestamptz not null,
    strikes        integer not null default 1 check (strikes >= 1),
    updated_at     timestamptz not null default now()
);

-- The BAN_AFTER_STRIKESth strike inside the window. Active while lifted_at
-- is null; an admin lifts it.
create table if not exists ip_bans (
    ip          inet primary key,
    reason      text not null,
    created_at  timestamptz not null default now(),
    lifted_at   timestamptz
);

