-- lasteverLM ingest: the capture mode of a PDF library source.
-- 'text' reads the text layer, 'vision' has the model read every rendered
-- page, 'auto' only the pages without a text layer. Null for every other
-- kind. The same bytes captured in two modes are two library sources, so
-- a PDF's dedupe key carries the mode: 'sha256:<hex>:<capture>'. Every
-- PDF from before this migration was read by its text layer.
alter table library_sources add column if not exists capture text
    check (capture in ('text', 'vision', 'auto'));
update library_sources set capture = 'text' where kind = 'pdf' and capture is null;
update library_sources set dedupe_key = dedupe_key || ':text'
 where kind = 'pdf' and dedupe_key like 'sha256:%' and dedupe_key not like 'sha256:%:%';
