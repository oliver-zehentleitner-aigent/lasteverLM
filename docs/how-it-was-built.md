# How it was built

lasteverLM is also an experiment: can one maintainer build, run and
harden a system of this size with a fleet of AI coding-agent sessions,
in a few days, without giving up review, tests and a written record of
every decision? This page is the factual account: who did what, how
the work was organised, the numbers, and what went wrong.

## The setup

| Role | Who | Responsibility |
|---|---|---|
| Maintainer | one person | product rules and architecture, every open decision, live testing on phone and desktop after each release, every go for production data and permissions |
| A | coding-agent session | coordination, review and merge of every pull request, releases, root docs; no service code |
| B | coding-agent session | `infra/`: cluster, Helm chart, pipeline, runbooks |
| C | coding-agent session | `ingest/`: loaders, chunking, embeddings, library |
| D | coding-agent session | `rag/`: retrieval, citations, outputs, judges, agent chat |
| E | coding-agent session | `web/`: the React frontend and admin panel |
| F | coding-agent session | `account/`: sign-in, credit, finance, admin backend |
| G | coding-agent session | `core/`: the shared library |

All sessions ran in parallel on one machine, each in its own checkout
of this one repository, and talked to each other directly. Agents
pushed to a fork and opened pull requests; agent A merged them only
when every check had passed. A release is a Git tag: images are built,
Helm deploys them with migrations, and a smoke test runs over the
public domain.

## Timeline

| Day | What happened |
|---|---|
| 1 (12 Oct) | cluster, database, storage, the first end-to-end cited answer around midnight; v0.1.0 |
| 2 (13 Oct) | sources of every kind, the library, conversations, outputs with options, the admin panel; v0.4.0 to v0.9.0 |
| night 2–3 | one audit per directory against a shared checklist: client address trust (PROXY protocol), pod hardening, NetworkPolicies, pinned actions, SQL tested against real PostgreSQL; v0.9.1, v0.10.0 |
| 3 (14 Oct) | the maintainer's first walkthrough; audio, provenance on every output, decisions, charts, the judge with an evaluation, finance with real costs, read-when-used, web page versions and snapshots; up to v0.19.7 |
| 4 (15 Oct) | the second walkthrough; verification levels up to two independent judges, the negation check, output IDs with stored attempts, the credit start rule, structured URL data, tiled vision reads, self-healing jobs, the judge searching all sources before rejecting; up to v0.22.19 |

## The numbers

Measured from the repository, GitHub and the session transcripts
(active time counts gaps of up to 30 minutes).

| | |
|---|---|
| Calendar time | 12 Oct 18:18 to 16 Oct 00:10, about 78 hours |
| Active agent time, summed over seven sessions | 138:30 h |
| Merged pull requests | 648 |
| Releases (tags) | 81, v0.1.0 to v0.22.19 |
| Commits | 1 911 |
| Lines of Python, TypeScript and JavaScript | about 81 000 |
| Test files | 141 Python, 67 TypeScript |
| Recorded decisions (`context/` entries) | 300 in 84 files |
| Model requests by the agent sessions | 13 703 |
| Typical time from tag to live and smoke-tested | about 4 minutes (median 3.6) |

## How the work was kept in check

- **One reviewer, one gate.** Every pull request was read by agent A
  and merged only with every check green: tests per service, PostgreSQL
  tests against the real migrations, formatting, the decision-record
  linter, and a check that a pull request only changes the unreleased
  part of a changelog.
- **Decisions are written down when they are taken,** with the
  alternatives they rejected, next to the code, and browsable in the
  [Keep the Why dashboard](https://oliver-zehentleitner.github.io/lasteverLM/keep-the-why-dashboard/).
  Every directory went through two maintenance rounds against its own
  code before the end.
- **Measure, do not assume.** Billing units were checked against the
  platform, and model choices were made by published evaluations
  ([judge](https://github.com/oliver-zehentleitner/lasteverLM/blob/main/rag/docs/judge-eval.md),
  [second judge](https://github.com/oliver-zehentleitner/lasteverLM/blob/main/rag/docs/second-judge-eval.md),
  [negation](https://github.com/oliver-zehentleitner/lasteverLM/blob/main/rag/docs/negation-eval.md),
  [vision](https://github.com/oliver-zehentleitner/lasteverLM/blob/main/ingest/docs/vision-eval.md)).
- **Production stays the maintainer's.** Reads or writes of real user
  data, permission changes and repairs ran only with the maintainer's
  own go, given in the session that ran them; one agent passing on
  another's approval did not count.
- **The maintainer decides the scope.** After the first walkthrough
  the scope grew only on the maintainer's orders; on day 3 a feature
  freeze was declared, and from then on new work came only from the maintainer.

## What went wrong

Honest, because a fleet is fast and makes its own kind of mistakes.

- **Walkthrough findings.** The maintainer's live testing found what
  the tests did not: a network policy missing for a new service call,
  a vision model looping into nonsense that was accepted as a source,
  a chart built from deselected sources, an audio file whose header
  claimed only its first segment, decisions counting evidence by the
  word check alone, reports whose paragraphs were silently not
  checked. Each was fixed with a test, most within the hour.
- **Rollouts interrupted running jobs** until the workers got a long
  grace period, a clean handover and a journal to resume from.
- **The coordination tooling** had its own bugs: a release script in a
  shared checkout, a fixed date, an ignored push error, two release
  chains running at once, a user interface merged before its backend.
  None reached production; each led to a fix in the tooling or a rule
  in the review checklist.
- **Parallel pull requests collide** in shared files such as
  changelogs. Agents with several open pull requests learned to stack
  them in one line.

## What it shows

A fleet of agents produces volume quickly; what makes the result
trustworthy is the same as with people: one gate for every change, a
written reason for every decision, measurements instead of beliefs, and
a person who tests the real thing and makes the decisions.
