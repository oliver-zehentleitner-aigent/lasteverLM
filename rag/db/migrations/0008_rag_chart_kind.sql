-- lasteverLM rag: the "chart" output kind (number series from the sources,
-- proposed by the LLM, picked by the user, every value checked against the
-- passages it cites).

alter table outputs drop constraint if exists outputs_kind_check;
alter table outputs add constraint outputs_kind_check
    check (kind in (
        'report', 'quiz', 'table', 'mindmap', 'infographic', 'audio', 'decision', 'chart'
    ));
