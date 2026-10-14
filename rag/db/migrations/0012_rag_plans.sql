-- lasteverLM rag: the agent chat's plans.
--
-- A chat message that asks for actions gets a plan of at most six steps;
-- nothing runs before the user confirms it. The steps keep their state
-- (proposed, queued, running, waiting, done, failed) and their result.
-- Every call of a plan books under its action_id; an output a plan creates
-- carries that id in outputs.booking_id.

create table if not exists plans (
    id               uuid primary key,
    conversation_id  uuid not null references conversations (id) on delete cascade,
    notebook_id      uuid not null references notebooks (id) on delete cascade,
    owner            uuid not null,
    status           text not null default 'proposed'
                     check (status in ('proposed', 'running', 'done', 'failed', 'cancelled')),
    steps            jsonb not null,
    estimate         jsonb not null,
    action_id        uuid not null,
    -- the assistant message that proposed the plan; it shows the plan's current state
    message_id       uuid,
    created_at       timestamptz not null default now(),
    confirmed_at     timestamptz,
    finished_at      timestamptz
);
create index if not exists plans_running_idx on plans (confirmed_at) where status = 'running';

alter table outputs add column if not exists booking_id uuid;

-- the plan a message proposed, as it stands now (kept in step with plans.steps)
alter table messages add column if not exists plan jsonb;
