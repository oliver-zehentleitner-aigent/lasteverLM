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
plan's `action_id`. An explanation runs as soon as its output is ready:
at confirm for an output that already exists, in the worker for one the
plan creates. An output still waiting for a source 30 minutes after
confirmation fails with the reason shown and is not charged; every
output has the same limit from its creation (33fc1c1f-8444-4f70-b597-b459ce000c78
in `outputs.md`), which for a plan's output is the same moment.

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

## The agent asks an open choice that changes the cost or the result, instead of deciding it

**Id:** 81014b92-e658-47bf-9855-8032dfe0ec4a
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer order relayed by the coordinator, 2026-10-15 (judge_default; ask when it is set and the message is silent, take an explicit message as said, a note when the default is off; a general question turn for a chat that works as a wizard; rejected: applying the default silently)
**Revisit when:** users answer the same question the same way nearly every time (a remembered answer per notebook may serve them better), or the chat needs a question whose answer is neither an option nor an argument of a step

A plan whose steps leave open a choice that changes the cost or the
result asks it before it is proposed. It shows a short question with two
to four choices, each with the plan's price if taken, one preselected.
The answer is applied to the steps, the plan is re-estimated and then
proposed, and only a proposed plan can run. A choice the message already
makes is taken as said and never asked. The judge is the first such
question: asked when the user's `judge_default` has a level, noted
("without a judge") when it is off. The mechanism is general: the
answer sets or removes one option on the named steps (`set_option`), or
sets one argument of them (`set_arg`). Questions come one at a time.

**Since the verification levels (2567fcf4-09b1-4bc9-80e7-759bce4c3326 in
`judge.md`):** the first question is the level, not the judge; the
mechanism is unchanged.

**Re-checked 2026-10-15:** the earlier revisit condition (a question
whose answer is not an option of a step) fired with the web-page
question, whose answer sets `url_refresh`. The decision holds; the
question turn gained the second kind of answer, nothing else changed.

**Reason:** a judge multiplies the calls of an output, so it is a cost
the user should choose in the request that incurs it. A default chosen
once in the settings is a fair starting point, but applying it silently
would charge for a check the user may not want this time. Asking only
when the message is silent keeps the chat quick for those who say what
they want, and showing the price of each choice lets the answer be an
informed one. Making it a general question turn, not a judge special
case, is what lets later questions build on it.

**Rejected alternatives:**
- Applying the default silently: hides a cost the user did not choose
  in this request.
- Asking every time: slows down users who already said what they want.
- A judge-only flag on the plan: every later question would need its
  own.

## Before an output reads a web page again, the plan asks, with the page's age and the price

**Id:** 3e2cbd75-6e9f-4b12-9f2d-49e1986fd45d
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer order relayed by the coordinator, 2026-10-15 (done message links the outputs; the web-page cache asked through the question turn with "use the cached version" preselected; plain answers show the age of a cited page; rejected: the permanent refresh control under the chat)
**Revisit when:** users pick "fetch again" nearly every time (fresh may be the better default), or ingest re-checks pages on its own schedule so a cached page is rarely old

A plan that creates an output from a notebook holding web pages asks
once whether to use the versions already read or fetch them again. The
question names the page and how long ago it was read (several pages:
their number and ages); fetching again
shows ingest's extra cost. Using the cached versions is preselected. A
message that already says it is taken as said. Questions come one at a
time, so this one follows the judge question when both apply. A plain
answer that cites a web page carries the time its version was read, and
the plan's summary message names and links what was made.

**Reason:** whether a page is still current matters only at the moment
something is made from it, and the user can judge that only knowing how
old it is and what fetching again costs. Asking there, with both in
front of them, makes the refresh a choice in the request that pays for
it. The cached version is the default because it is free and usually
recent enough. Showing the age on plain answers lets the user notice a
stale page where it matters and ask again with it fetched.

**Rejected alternatives:**
- A permanent refresh control under the chat: unclear what it applied
  to, and it had no effect once an output was created.
- Always fetching again: charges for every output even when the page is
  minutes old.
