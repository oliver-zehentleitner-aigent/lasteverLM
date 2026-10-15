# Conversations

## A notebook holds several conversations; every message belongs to one

**Id:** b72fc874-2d51-4b37-a5a9-03d5f3e7c321
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer request after a manual walkthrough, relayed by the coordinator, 2026-10-13
**Revisit when:** conversations need to be shared, moved between notebooks, or searched across

A notebook has any number of conversations (`conversations` table, one
per chat tab); `messages.conversation_id` is required. `/ask` takes the
conversation explicitly and a missing one is a 422, never a silent
default. Closing a tab deletes the conversation with its messages. The
migration keeps existing history by moving each notebook's messages
into one conversation "Chat 1". Scoped questions about a generated
output land in whatever conversation they were asked in.

**Reason:** separate topics in one notebook (questions about two
different documents) should not share one running history, and a tab the user
closes should take its messages with it. A row per conversation gives
each tab an id, a title and an ordering of its own, and lets the model
read only the history of the tab the question came from.

**Rejected alternatives:** a tag or label on each message within one
history per notebook, rejected because closing a tab would have meant
deleting by tag, a tab's title and creation time would have had no row
to live in, and every query would filter a shared history instead of
reading one conversation; a default conversation when `conversation_id`
is missing, rejected because a client that forgets the id would write
into the wrong tab without noticing.

## The model sees the conversation's newest turns; retrieval uses the question alone

**Id:** 6d11168c-ef4f-4074-af28-ae0015b3ecd0
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** implementation session, 2026-10-13
**Revisit when:** follow-up questions with pronouns ("how do I install it?") retrieve the wrong passages in practice

The answer prompt carries the newest six messages of the conversation,
each cut to 1000 characters and with citation markers removed, before
the passages. The system prompt says earlier turns only tell what the
question refers to; facts and citations still come from the passages
of this question. Retrieval embeds the current question only.

**Reason:** follow-ups such as "but isn't the other document about
that?" only make sense with the turn before.
Six messages are three exchanges, enough to resolve a reference without
filling the context window. Old markers point at passages of an earlier
retrieval, so they are removed to keep the model from citing numbers
that mean something else now.

**Rejected alternatives:** rewriting a follow-up into a standalone
question with an extra LLM call before retrieval, not done for now
because it costs one more model call per question and the need is not
yet shown; it is the next step if pronoun follow-ups retrieve badly.
Embedding the previous question together with the current one was not
done either, because it pulls retrieval towards the old topic when the
user changes subject.

## An answer's suggested questions come as a text tail of the same call, not as JSON

**Id:** 21dcf298-5d48-490c-b266-a729462b80c5
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** maintainer wish relayed by the coordinator, 2026-10-14 (three follow-ups, the same model call, "structured tail or JSON field", stripped from the answer, stored); the choice of the tail is rag's
**Revisit when:** answers are streamed to the client, or the model often leaves the tail out

The answer prompt asks the model to end with a line "Suggestions:" and
three questions, one per line. `split_suggestions` cuts that tail off at
its last occurrence, before the citations are mapped, and cleans the
questions: no markers, one line, at most 150 characters, distinct, at
most three. An answer without the tail has no suggestions and is
otherwise unchanged.

**Reason:** the suggestions must cost nothing extra and add no wait,
and the same call does both. A JSON object around the answer would change how the answer
itself is written and parsed: every answer would fail or need a
corrective retry when the JSON is off, for the sake of a side feature.
A tail is cheap to cut, and missing it costs only the suggestions.
Cutting it before the citations are mapped keeps the questions' markers
out of the answer's citations.

**Rejected alternatives:**
- A JSON answer with a suggestions field: it puts the main answer at
  risk for a side feature.
- A second call: extra cost and latency for a side feature.
