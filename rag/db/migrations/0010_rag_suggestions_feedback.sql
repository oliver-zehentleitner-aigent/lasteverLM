-- lasteverLM rag: suggested questions and feedback on answers.
--
-- An assistant message keeps the follow-up questions written with it and the
-- owner's rating; a notebook keeps its starting questions until its sources
-- change (``sources_key`` names the ready uploads they were made from).

alter table messages add column if not exists suggestions jsonb not null default '[]'::jsonb;
alter table messages add column if not exists feedback jsonb;
create index if not exists messages_feedback_idx on messages ((feedback ->> 'at'))
    where feedback is not null;

create table if not exists notebook_suggestions (
    notebook_id  uuid primary key references notebooks (id) on delete cascade,
    sources_key  text not null,
    suggestions  jsonb not null,
    created_at   timestamptz not null default now()
);
