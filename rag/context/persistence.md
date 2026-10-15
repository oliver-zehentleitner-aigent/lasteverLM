# Persistence

## A question and its answer are written together, after the answer exists

**Id:** 876ba580-088c-4412-bcc7-0fc033bcf03f
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** implementation session, 2026-10-12
**Revisit when:** answers are streamed or questions are queued

The user message and the assistant message are inserted only once the
answer (or the refusal) is complete, user first, assistant second.
Nothing is written before retrieval and generation. This is about a
question and its answer: the agent chat's own turns (the answer to a
plan's question, the note that a plan runs, its summary) are single
messages written when their event happens, after anything that could
fail.

**Reason:** the message history is what the frontend renders; if the
provider call fails, a stored question without an answer would show up as
a dangling turn the user cannot act on. Writing both at the end keeps the
history in complete pairs and the failure visible as an error response.

**Rejected alternative:** insert the user message first, so the question
survives a failed answer. Rejected because the frontend would then need
to handle half-turns, and the question is still in the error response
the caller already has.
