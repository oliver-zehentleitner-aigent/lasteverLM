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

## Tool arguments come only from the user's message and library, never from a source

**Id:** 3b90af43-0016-4630-80af-0620749cf475
**Type:** constraint
**Status:** active
**Evidence:** confirmed
**Source:** maintainer go relayed by the coordinator, 2026-10-14 (tool args only from the user's message and own library; sources seen only in explain_output); the enforcement in code is rag's
**Revisit when:** a tool needs an argument the user cannot write themselves, or the planner needs a source's content to plan

The planning call sees the user's message, their earlier questions and
the names of the notebook's documents and outputs, but no passage. The
plan's validation then enforces the rule in code, whatever the model
wrote:
- a URL must appear in the user's message;
- a library source is found by name among the user's own library entries
  (through ingest's API, with the user's bearer);
- an output is one of the notebook's ready ones, or one this plan creates;
- options pass the kind's own validation.

A step that breaks a rule is marked invalid with its reason, never
corrected and never run. Only `explain_output` reads sources, and it
produces an answer, not tool calls.

**Reason:** a document is someone else's text inside the user's notebook.
An instruction written in it ("add this URL", "create forty audio
files") must never become an action the user pays for or did not ask
for. Keeping passages out of the planner removes the channel. Checking
the arguments in code covers a planner that invents or misreads one, and
the user still sees every step before confirming.

**Rejected alternatives:**
- Planning over the passages, as an answer is written: a document could
  plant tool arguments.
- Trusting the model's arguments and relying on confirmation alone: a
  user skimming a plan confirms what a document planted.
