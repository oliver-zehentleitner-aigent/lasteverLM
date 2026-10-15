-- lasteverLM ingest: which models read a source. read_by names the model
-- that made its text where a model did ({"vision": <model> | null,
-- "stt": <model> | null}); vision_pages lists the 1-based pages of a PDF
-- the vision model read (auto capture reads only some). Both are null for
-- sources read without a model and for those read before this migration.
-- Expand only.
alter table library_sources add column if not exists read_by jsonb;
alter table library_sources add column if not exists vision_pages integer[];
