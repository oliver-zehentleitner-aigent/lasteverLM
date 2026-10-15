-- lasteverLM rag: a judgement on request runs as a background job (expand
-- only). A request inserts a row; the worker claims it like an output job
-- (FOR UPDATE SKIP LOCKED, a stale claim taken over), writes its phase as the
-- heartbeat, keeps every failed attempt, and stores the result on the output
-- or the message as the synchronous request did. A High check of many units
-- outran the ingress' 120 s.

create table if not exists judge_jobs (
    id           uuid primary key,
    owner        uuid not null,
    target       text not null check (target in ('output', 'message')),
    target_id    uuid not null,
    notebook_id  uuid,
    level        text not null,
    status       text not null default 'queued'
                 check (status in ('queued', 'running', 'done', 'failed')),
    phase        jsonb,
    attempts     integer not null default 0,
    attempt_log  jsonb not null default '[]'::jsonb,
    error        text,
    claimed_by   text,
    claimed_at   timestamptz,
    created_at   timestamptz not null default now(),
    finished_at  timestamptz
);
create index if not exists judge_jobs_queue_idx on judge_jobs (status, created_at)
    where status in ('queued', 'running');
create index if not exists judge_jobs_target_idx on judge_jobs (target, target_id, created_at desc);
