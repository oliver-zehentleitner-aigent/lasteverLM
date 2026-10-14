-- lasteverLM ingest: the demo flag becomes the starter flag.
-- New users no longer get the Zeltavia demo seeds (processed at the demo
-- user's expense) but a copy of the starter notebook an admin marks
-- (settings 'starter_notebook'): ready copies of its sources, flagged
-- `starter` for the badge. Rows seeded as demo keep the flag under its new
-- name; nothing processes them at anyone else's expense any more.
do $$
begin
    if exists (select 1 from information_schema.columns
                where table_schema = current_schema() and table_name = 'library_sources'
                  and column_name = 'demo') then
        alter table library_sources rename column demo to starter;
    end if;
end
$$;
