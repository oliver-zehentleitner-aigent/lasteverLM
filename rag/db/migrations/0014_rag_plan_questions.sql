-- lasteverLM rag: a plan can ask the user a question before it is proposed
-- (expand only). An open choice that changes the cost or the result (a
-- judge, when the user's default has one) is asked, not decided; the
-- plan waits in status 'asking' until the answer.

alter table plans drop constraint if exists plans_status_check;
alter table plans add constraint plans_status_check
    check (status in ('asking', 'proposed', 'running', 'done', 'failed', 'cancelled'));
-- the question (with how its answer applies to the steps) and the plan's notes
alter table plans add column if not exists question jsonb;
alter table plans add column if not exists notes jsonb;
