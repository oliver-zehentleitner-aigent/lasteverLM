-- lasteverLM rag: the "decision" output kind (a question answered by the
-- platform's decision model, with evidence for and against written by the
-- LLM from the same passages).

alter table outputs drop constraint if exists outputs_kind_check;
alter table outputs add constraint outputs_kind_check
    check (kind in ('report', 'quiz', 'table', 'mindmap', 'infographic', 'audio', 'decision'));
