# Workflow

## Five parallel coding-agent sessions, one human in the loop

**Id:** a788c54e-a18a-4f3a-a410-128c578dd5ec
**Type:** decision
**Status:** superseded
**Superseded by:** 7ad3c5a1-a7d3-408d-bbd2-f72bf7e66648
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12
**Revisit when:** the number of agents or the service cut changes

The project is built by up to five coding-agent sessions running at the
same time on one machine, with the maintainer as the human in the loop.
Agent A reviews and manages together with the maintainer and owns this
parent repository; agents B to E each own one service repository and
write code. Sessions can message each other directly, but only for
interface changes and blockers; everything else goes through Git. Each
service repository keeps its own `context/`; whatever is family-wide is
handed to agent A and recorded here, so no coding agent writes into a
checkout it does not own.

**Reason:** parallel agents are part of what the project demonstrates,
and one agent per repository is the simplest way to give each a clean
workspace. Routing family-wide rationale through one agent avoids four
sessions editing one working tree at once.

**Rejected alternative:** one agent working through the services
sequentially. Simpler to coordinate, rejected because it would show
nothing about working with several agents and would take several times
as long in wall-clock time.

## One shared GitHub account for all agents, the maintainer reviews and merges

**Id:** ebff131a-7797-439e-9877-0903c2e3df51
**Type:** decision
**Status:** superseded
**Superseded by:** b8d4c63e-d5c0-4eaa-8a55-e8788155ff53
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12

All agent sessions push through one GitHub account that holds forks of
the project repositories. Work lands as pull requests from the fork
against the maintainer's repositories; the maintainer reviews, with
agent A's pre-review, and is the only one who merges. Commits carry the
agent account's identity, not the maintainer's.

**Reason:** one account keeps the fork and permission setup to a single
place, and review by the maintainer before every merge is the control
point that makes five parallel agents safe to run. The agent account has
no merge rights by design.

**Rejected alternative:** one GitHub account per agent, for a visible
per-agent history. Rejected by the maintainer as setup overhead with no
benefit: branch names carry the agent, and the review gate is the same
either way.

## Every agent reads the family's reasoning before building against another service

**Id:** f2344982-34af-4679-a133-9eb5e8f126e4
**Type:** constraint
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12

Before starting work and before opening a pull request, an agent
fetches the parent repository and the repositories its service depends
on and reads their `context/index.md` and the topics it touches. Every
repository in the family keeps its own `context/` under Keep the Why
from the first commit, and family-wide reasoning is routed to the
parent through agent A.

**Reason:** six sessions in parallel only work when a decision made in
one repository is known in the others before code is written against
it. Git is the channel for that; direct messages are for interface
changes and blockers only. The maintainer set this as a hard rule.

**Rejected alternative:** a shared chat or a status document. Rejected
because it would be a second place for knowledge that already belongs
in the repositories, and would not survive the project.

## Until the prototype, agent A reviews and merges; the maintainer tests the result

**Id:** b8d4c63e-d5c0-4eaa-8a55-e8788155ff53
**Type:** decision
**Status:** superseded
**Superseded by:** 7ad3c5a1-a7d3-408d-bbd2-f72bf7e66648
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12
**Revisit when:** the first prototype is accepted by the maintainer

All agents still push through one shared account with per-agent commit
identity. Until the first prototype is accepted, agent A reviews every
pull request and merges it, and writes no code itself; a session G
takes over the core library. The maintainer tests the running
prototype instead of reading pull requests. After acceptance, merging
returns to the maintainer.

**Reason:** the maintainer's time is better spent on the product than
on reading six repositories' pull requests during the build, and one
reviewing agent that writes no code has the whole picture and no
conflict of interest. The shared account can neither approve its own
pull requests nor merge without write access, so the maintainer grants
write access and sets branch protection to require CI only.

**Rejected alternative:** the maintainer merges everything (the rule
in the superseded entry). Right for the long run, rejected for the
build phase because it would make the maintainer the bottleneck for
six parallel agents.

## Seven agent sessions in one repository; agent A reviews and merges every change

**Id:** 7ad3c5a1-a7d3-408d-bbd2-f72bf7e66648
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** the maintainer's role assignment per session, 2026-10-12 to 2026-10-15; the repository's pull request history

Seven sessions ran in parallel in the one repository (see "One
repository with isolated contexts" in `architecture.md`). Agent A
coordinates, reviews and merges every pull request and writes no
service code; agents B to G each own one directory (infra, ingest, rag,
web, account, core). A pull request is merged only when every check
has passed, and a release is tagged only when every part of a change is
merged. The maintainer tests the live system, decides every open
question, and gives every go for production data, permissions and new
features. The arrangement agreed for the time until the first
prototype stayed for the whole build. This replaces the plan of five
sessions and the review arrangement limited to the prototype.

**Reason:** one reviewer for every change keeps the cross-service view
in one place, and an all-checks gate catches what a reviewer misses.
Two more coding sessions than planned gave the shared library and the
web client an owner each instead of maintaining them on the side.

**Rejected alternative:** the maintainer merging after the prototype.
Not taken: several hundred pull requests would have taken the
maintainer's time from testing and deciding.

## Black formats the Python services; ruff only lints

**Id:** 011fb29d-7593-49be-a12f-2e0619e40d77
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer instruction, 2026-10-13

Every Python directory (core, account, ingest, rag, the infra scripts)
is formatted with black at line length 100, checked by `black --check`
in `make lint`. ruff stays for linting (imports, bugbear, pyupgrade)
and no longer formats.

**Reason:** the maintainer formats all of his repositories with black
and wants one formatter dialect across them, not one per project.

**Rejected alternative:** `ruff format`, which the services used until
then. It is black-compatible and one tool fewer, but a second
formatter in the maintainer's tool chain for no gain.

## Before the handover, every directory passes one audit against a shared checklist

**Id:** 171b4a92-a146-4b75-bb0a-30e3bf696bd0
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer instruction on the evening of 2026-10-13 ("full security and quality check, no technical debt"); agent A's checklist the same night

On the night before the maintainer's final walkthrough, every owner
audits its own directory against one checklist written by agent A:
security (authorisation on every route, input bounds, injection
surfaces, secrets, trust boundaries, timeouts, error texts), quality
(dead code, duplicates, strict typing, test gaps for everything shipped
that day, lint), and documentation (README, context entries with their
superseded chains, CHANGELOG sections). Findings are fixed in small pull
requests; what an owner leaves is reported with a reason and decided by
agent A or the maintainer. Cross-directory findings go to the owner of
the cause, never to whoever found them.

**Reason:** two days of parallel feature work by seven sessions leave
debt that no single reviewer saw whole: each pull request was reviewed
against its own diff, not against the system. One pass by the people
who know each directory, under one checklist, finds what the per-PR
review structurally cannot (the night found an X-Forwarded-For trust
hole at the ingress, a mind map XSS, a retry path that could bill a page
twice, and an upload race). Doing it before the walkthrough means the
maintainer tests the hardened system, not the one with the debt.

**Rejected alternatives:** ship and audit after the handover, rejected
because the reviewers would see the debt; one external or automated
review of the whole repository instead of owner audits, rejected because
the owners carry the context that makes a finding a fix in an hour, and
the automated scanners (CodeQL, Dependabot) already run and were clean
while the real findings were logic and configuration.

