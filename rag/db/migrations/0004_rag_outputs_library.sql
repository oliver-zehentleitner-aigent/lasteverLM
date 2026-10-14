-- lasteverLM rag: outputs belong to the user and live in the library.
--
-- An output keeps its owner when its notebook is deleted: notebook_id is
-- the origin, nullable, set to null by the notebook delete, and
-- origin_title keeps the notebook's title for "from deleted notebook X".
-- deleted_at is the trash (purged after the owner's trash_days by the rag
-- worker). source_id names the output's generated library row directly
-- (its id equals the origin link's, so the values stay), because the link
-- goes with the notebook while the row stays.
--
-- Expand only: owner is filled here and by every insert of this release,
-- but stays nullable so pods of the previous release can still insert
-- during the rolling deploy; reads fall back to the notebook's owner.

alter table outputs add column if not exists owner uuid;
alter table outputs add column if not exists origin_title text not null default '';
alter table outputs add column if not exists deleted_at timestamptz;

update outputs o set owner = n.owner, origin_title = n.title
  from notebooks n
 where n.id = o.notebook_id and o.owner is null;

alter table outputs alter column notebook_id drop not null;
alter table outputs drop constraint if exists outputs_notebook_id_fkey;
alter table outputs add constraint outputs_notebook_id_fkey
    foreign key (notebook_id) references notebooks (id) on delete set null;

alter table outputs drop constraint if exists outputs_source_id_fkey;
update outputs o set source_id = null
 where o.source_id is not null
   and not exists (select 1 from library_sources l where l.id = o.source_id);
alter table outputs add constraint outputs_source_id_fkey
    foreign key (source_id) references library_sources (id) on delete set null;

create index if not exists outputs_owner_idx on outputs (owner, created_at desc);
create index if not exists outputs_trash_idx on outputs (deleted_at) where deleted_at is not null;
