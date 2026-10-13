-- lasteverLM ingest: the demo library every new user starts with.
-- library_seeds marks owners whose library has been considered for the
-- demo sources (seeded, or skipped because they already had entries), so
-- seeding happens at most once per owner. library_sources.demo marks the
-- seeded entries: the library shows a badge, and their processing is paid
-- by the demo user (DEMO_USER_ID), not by the new user.
create table if not exists library_seeds (
    owner      uuid primary key,
    seeded_at  timestamptz not null default now()
);
alter table library_sources add column if not exists demo boolean not null default false;
