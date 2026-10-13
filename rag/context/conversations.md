# Conversations

## A notebook holds several conversations; every message belongs to one

**Id:** b72fc874-2d51-4b37-a5a9-03d5f3e7c321
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer request after the click-through, relayed by the coordinator, 2026-10-13
**Revisit when:** conversations need to be shared, moved between notebooks, or searched across

A notebook has any number of conversations (`conversations` table, one
per chat tab); `messages.conversation_id` is required. `/ask` takes the
conversation explicitly and a missing one is a 422, never a silent
default. Closing a tab deletes the conversation with its messages. The
migration keeps existing history by moving each notebook's messages
into one conversation "Chat 1". Scoped questions about a generated
output land in whatever conversation they were asked in.

**Reason:** separate topics in one notebook ("what is VNC", "how do I
use vi") should not share one running history, and a tab the user
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

**Reason:** follow-ups in the click-through ("but isn't the other
document about the VNC server?") only make sense with the turn before.
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
