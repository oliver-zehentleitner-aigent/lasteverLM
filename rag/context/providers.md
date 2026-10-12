# Providers

## A model reply without content is a provider failure, never an empty answer

**Id:** 866cf948-6745-40f1-8a82-a8e20c19b5a7
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** platform probe reported by the family, 2026-10-12; implementation session, 2026-10-12
**Revisit when:** the LLM is called with thinking disabled and the probe no longer reproduces

The platform's LLM is a reasoning model; a probe with a small token
budget returned only reasoning tokens and empty content. The service
treats empty content as a provider failure wherever it calls the model:
`/ask` answers 502 and stores no message (the usage row stays, the tokens
were spent); a generator raises a provider error, which the worker
retries like any transient failure, up to the attempt cap.

**Reason:** an empty string is not an answer and must not reach the
history or a document; a retry is the right reaction because the next
call may well return content, unlike a schema miss, which the model
repeats.

**Rejected alternatives:** storing the empty reply as the assistant
message, rejected because it would show the user a blank turn and bill
it as answered; treating it as a final generation failure, rejected
because the cause is budget and model mode, not the material.
