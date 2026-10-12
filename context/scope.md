# Scope

## The MVP is grounded question answering over uploaded documents, nothing more

**Id:** d7adc698-ffa5-4edf-a031-59a2aacf4f1e
**Type:** decision
**Status:** active
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
voucher codes that credit a balance (default 10 EUR), a per-user
balance that every model call draws on, and a compact admin panel with
users, login log, an aggregated visitor log, SMTP settings and the
domain allowlist.

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
