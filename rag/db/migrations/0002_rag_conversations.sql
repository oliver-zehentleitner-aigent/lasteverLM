-- lasteverLM rag: several conversations per notebook.
-- A conversation is one chat tab; every message belongs to exactly one.
-- Existing history is kept: each notebook that has messages gets one
-- conversation "Chat 1" (created at its first message) holding all of them.
-- Deleting a conversation deletes its messages; deleting a notebook deletes
-- its conversations.

create table if not exists conversations (
    id           uuid primary key,
    notebook_id  uuid not null references notebooks (id) on delete cascade,
    title        text not null,
    created_at   timestamptz not null default now()
);
create index if not exists conversations_notebook_idx on conversations (notebook_id, created_at);

alter table messages
    add column if not exists conversation_id uuid references conversations (id) on delete cascade;

insert into conversations (id, notebook_id, title, created_at)
select gen_random_uuid(), notebook_id, 'Chat 1', min(created_at)
from messages
where conversation_id is null
group by notebook_id;

update messages m
set conversation_id = c.id
from conversations c
where m.conversation_id is null and c.notebook_id = m.notebook_id;

alter table messages alter column conversation_id set not null;
create index if not exists messages_conversation_idx on messages (conversation_id, created_at);
