-- lasteverLM ingest: the starter notebook can be made again.
-- notebooks.starter marks a notebook made as a copy of the starter (at the
-- first sign-in or on request); the web asks before making a second one.
-- library_seeds.copied_at is the last copy made on request, for the limit
-- of one an hour; the first sign-in's copy does not count. Expand only.
alter table notebooks add column if not exists starter boolean not null default false;
alter table library_seeds add column if not exists copied_at timestamptz;

-- Starter copies made before the flag existed: a notebook that links
-- starter-flagged sources and was created within a minute of its owner's
-- seed (the copy runs in that request). Inferred, not recorded.
update notebooks n set starter = true
 where not n.starter
   and exists (select 1 from sources s join library_sources l on l.id = s.library_source_id
                where s.notebook_id = n.id and l.starter)
   and exists (select 1 from library_seeds ls
                where ls.owner = n.owner
                  and n.created_at between ls.seeded_at - interval '1 minute'
                                       and ls.seeded_at + interval '1 minute');
