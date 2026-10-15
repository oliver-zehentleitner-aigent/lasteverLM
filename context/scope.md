# Scope

## The MVP is grounded question answering over uploaded documents, nothing more

**Id:** d7adc698-ffa5-4edf-a031-59a2aacf4f1e
**Type:** decision
**Status:** superseded
**Superseded by:** 21eff4a6-f83a-48fc-b7df-f55e13c9a971
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12
**Revisit when:** the MVP is deployed and stable

The first release does exactly this: create a notebook, add sources
(PDF, plain text, URL), ask questions, get answers that cite the source
passages they rest on, keep the conversation per notebook. The layout is
the three-pane NotebookLM shape (sources, chat, notes) and must be
efficient and thought through, but it is not polished beyond that.

**Reason:** the project is a time-boxed portfolio piece. What it has to
show is that a vague brief turns into a stable, deployed system with a
clear architecture and a visible decision trail. Every feature beyond the
core costs time that would otherwise go into stability and the
decision trail, and adds nothing to what the project demonstrates.

**Deliberately left out:** audio overviews and other generated media,
mind maps, sharing between users, horizontal scaling, UI polish past a
clean layout. Each of these is a NotebookLM feature a reader might
expect; none of them is a precondition for the core loop, and the audio
overview in particular is expensive in both effort and API cost. They
are candidates for later, not forgotten.

## After the MVP, scope grows only on the maintainer's orders, then freezes

**Id:** 21eff4a6-f83a-48fc-b7df-f55e13c9a971
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** the maintainer's walkthroughs and orders, 2026-10-13 to 2026-10-15; the feature freeze, 2026-10-14
**Revisit when:** the project is handed over

The MVP was deployed on the first day and stable on the second, which
was the previous scope's own condition to revisit it. From then on the
scope grew from the maintainer's walkthroughs of the live system, on
the phone and on the desktop: audio overviews, mind maps and the other
output kinds, sharing by read-only link, horizontal scaling of the API
and worker pods, a German interface, several voices, the finance area
and the agent chat. Each addition is recorded with its reasoning in the
context of the part that owns it. Since 2026-10-14 the scope is frozen:
what was agreed is finished, fixes continue, and new features come only
from the maintainer.

**Reason:** a stable deployed core was the precondition, not the end.
Once it held, the features a reader of a NotebookLM clone expects
showed more than further polish of the core would have. The freeze
keeps the remaining budget for fixes and the handover.

**Rejected alternative:** keeping the MVP scope and spending the
remaining days on the core loop alone, rejected by the maintainer once
the core was stable.

## Time budget: three days, shared token budget

**Id:** a835376b-16d6-4c47-8f78-f5090170f032
**Type:** constraint
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12

The build has three days from 2026-10-12, with the first prototype
reviewed by the maintainer on the morning of 2026-10-13. All agent
sessions draw on one shared model subscription, so token spend is a
constraint of its own: long focused stretches, no polling, no status
chatter, no exploratory rewrites. The MVP is solid, not comfortable:
every repository follows the full repository standard and every agent
reads the other services' `context/` before building against them.

## The account service: magic-link login, sponsored credit, admin panel

**Id:** c6e89eca-8f4f-4345-bfe6-7191e96b461e
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12

Beyond the NotebookLM core loop, the MVP has a sixth service that owns
accounts: magic-link login limited to allowed e-mail domains, one-time
voucher codes that credit a balance (the code default is 10 EUR, the
production value 5 EUR), a per-user balance that every model call
draws on, and a compact admin panel with users, login log, an
aggregated visitor log, the mail configuration (read-only, set in the
environment) and the allowlist of domains and single addresses.

**Reason:** the maintainer wants to sponsor use of the deployment for a
known group: anyone under an allowed domain can create an account and
redeem a voucher, and the sponsor sees who uses what. That is a product
decision, not a clone feature, and it is what makes the deployment
usable by others than the maintainer.

**Privacy:** the visitor log stores a daily-rotating salted hash of the
address, never the raw IP, the user-agent family only, and is purged
after 30 days. The allowed domains are configuration, not code.

**Rejected alternative:** a single shared demo token and no accounts.
Enough for a recorded walkthrough, rejected because it shows no
multi-user separation and cannot sponsor anyone.
