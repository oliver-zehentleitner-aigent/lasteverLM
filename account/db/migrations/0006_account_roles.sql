-- lasteverLM-account: roles. 'viewer' reads the admin panel, 'admin' changes it, 'user' is
-- everyone else. Plain PostgreSQL, safe to re-run.

-- is_admin stays a plain column, kept equal to role = 'admin' by this service's two write
-- paths (create_user, set_role): core reads it, and migration 0001 (re-run on every deploy)
-- inserts it for the demo user, which a generated column would refuse.
alter table users add column if not exists role text not null default 'user'
    check (role in ('user', 'viewer', 'admin'));
update users set role = 'admin' where is_admin and role <> 'admin';
