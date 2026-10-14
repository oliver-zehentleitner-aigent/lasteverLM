-- lasteverLM ingest: a notebook can be shared read-only by a link.
-- share_token is the link's secret (secrets.token_urlsafe(24), the scheme
-- of rag's outputs.share_token); null when not shared. Rag's public view
-- reads it and shows the notebook's title, its sources' names and kinds
-- and its shared outputs; never the source files.
alter table notebooks add column if not exists share_token text;
create unique index if not exists notebooks_share_token_idx
    on notebooks (share_token) where share_token is not null;
