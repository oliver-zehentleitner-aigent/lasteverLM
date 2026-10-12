# Workflow

## Five parallel coding-agent sessions, one human in the loop

**Id:** a788c54e-a18a-4f3a-a410-128c578dd5ec
**Type:** decision
**Status:** active
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
**Status:** active
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
