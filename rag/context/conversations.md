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
