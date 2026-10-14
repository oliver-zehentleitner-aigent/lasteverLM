-- lasteverLM core: `usage.kind` gains 'decision' (the decision model behind
-- the Decision output). The priced unit is input tokens as the platform
-- reports them (usage.input_tokens): tokens_in holds them, tokens_out is 0,
-- and MODEL_PRICES lists DECISION_MODEL with "in" in cents per million tokens.

alter table usage drop constraint if exists usage_kind_check;
alter table usage add constraint usage_kind_check
    check (kind in ('llm', 'embedding', 'tts', 'stt', 'decision'));
