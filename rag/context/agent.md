# Agent chat

## The agent plans, the user confirms, and only then do the steps run as the user

**Id:** 0516de53-3008-408b-ad65-b15cbd365679
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer go relayed by the coordinator, 2026-10-14 (plan-confirm-execute; autonomous execution and a chat without tools rejected); the coordinator's approval the same day of running ingest steps inside the confirm request, of the 30-minute timeout without discarding the output, and of a tool-calling protocol in core; the platform probe of qwen3.8-27b's tool calls, 2026-10-14
**Revisit when:** users routinely confirm plans unchanged, so that confirmation becomes friction without protection, or a step needs a token after the confirm request has ended

A chat message that asks for actions gets a plan, not an answer. It has
at most six steps, each with its estimate and, when it cannot run, its
reason. Nothing runs before the user confirms. A step's failure does not
stop the others, and every step's state is on the plan and on the message
that proposed it.

Steps that need ingest run inside the confirm request, with that
request's own bearer. Outputs go through the normal queue, under the
plan's `action_id`. Explanations run in the worker once their output is
ready. An output still waiting for a source 30 minutes after confirmation
fails with the reason shown and is not charged.

**Reason:** an agent acting on someone's notebook spends their money and
changes what they see, so the user decides before anything happens, with
the price in front of them. Running ingest's steps inside the request
that carries the token means rag never stores a user's token: a stored
JWT would be a secret at rest and would expire before a long plan ends.
Only the steps rag runs itself wait for the worker. A failed output stays
visible with its reason rather than disappearing, so a stuck plan explains
itself.

**Rejected alternatives:**
- Autonomous execution: the model acts and spends without the user's
  consent.
- A chat without tools: the user must click through every action
  themselves.
- The worker running ingest steps with a stored bearer: a token at rest,
  and one that expires.
- Discarding an output that timed out: the user would not see what
  happened.
