-- lasteverLM rag: the "flashcards" output kind (front, back, hint per card;
-- the back checked against its cited passages like a quiz answer).

alter table outputs drop constraint if exists outputs_kind_check;
alter table outputs add constraint outputs_kind_check
    check (kind in (
        'report', 'quiz', 'table', 'mindmap', 'infographic', 'audio', 'decision', 'chart',
        'flashcards'
    ));
