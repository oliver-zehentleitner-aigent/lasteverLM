# lasteverLM

[![Read the Docs](https://img.shields.io/badge/read-%20docs-yellow)](https://oliver-zehentleitner.github.io/lasteverLM/) [![ci](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml) [![ktw-lint](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml) [![black](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/black.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/black.yml) [![Keep the Why · live](https://keepthewhy.com/assets/badge.svg)](https://oliver-zehentleitner.github.io/lasteverLM/keep-the-why-dashboard/)

**Material in. Understanding out.** PDFs, text, web pages, images and audio go in; questions, reports, quizzes, tables, mind maps and spoken overviews come out, each sentence traceable to the passage it came from. A NotebookLM-style assistant, built to be checked.

## What it does

- **Sources in:** PDFs (text layer or vision for scanned pages), text and Markdown, web pages with versions and snapshots, structured URLs (JSON, XML, CSV, YAML), images and audio. Adding is free; a source is read when a question or an output needs it.
- **Cited answers:** a chat per notebook whose answers point to the exact passages they rest on; one click opens the passage in the source.
- **Nine outputs:** report, quiz, flashcards, data table, chart, mind map, infographic, audio (overview, story, conversation, FAQ) and decision. Tables, charts and infographics first propose candidates to pick.
- **Checked, at the level the user chooses:** a deterministic word and negation check for free; a judge of another model family for doubted, all or, in "bulletproof", every paragraph by two judges. A paragraph the judge cannot find in its cited passages is searched for in all selected sources before it is called unsupported.
- **Everything shows how it was made:** passages, model, prompt version, cost, coverage of the selected sources, and an ID with every failed attempt, so support can trace any output.
- **Price before every action**, credit from vouchers, an action starts only when the credit covers it and then runs to its end.

## Measured, not assumed

Model choices and checks were picked by measurement, each with its method, numbers and limits:

- [Judge evaluation](rag/docs/judge-eval.md): which model checks claims at which level.
- [Second judge evaluation](rag/docs/second-judge-eval.md): the independent second judge for "bulletproof".
- [Negation evaluation](rag/docs/negation-eval.md): the spaCy negation check, with a held-out set.
- [Vision evaluation](ingest/docs/vision-eval.md): ten vision models, and why large images are read in tiles.

## Try it

The [live system](https://lasteverlm.zehentleitner.co) signs in by magic link for allowed addresses; credit comes from a voucher. Every new account starts with a notebook about lasteverLM itself, with the handbook, an FAQ, the price list and finished outputs of every kind, and the ? at the top right opens a short guide and the introduction.

## How it was built

Seven coding-agent sessions in three and a half days, one per part of the system and one that reviewed and merged every pull request; a maintainer who set the rules, tested every release live and decided every open question. A pull request was merged only when every check passed, a release is a tag that builds, deploys and runs a smoke test over the public domain, and every decision is written down with the alternatives it rejected. Over 640 pull requests and 80 tags; the [Keep the Why dashboard](https://oliver-zehentleitner.github.io/lasteverLM/keep-the-why-dashboard/) shows the reasoning in the order it happened. The full account, with the numbers and what went wrong, is in [How it was built](docs/how-it-was-built.md).

## Repository

One repository for the whole system. The root is the umbrella:
architecture, the reasoning behind it, the task board and the
workflows. Each service is a directory with its own `context/`:

| Directory | Purpose |
|---|---|
| [core/](core/) | shared library: models, settings, auth, rate limiting, usage accounting, provider interfaces |
| [account/](account/) | magic-link login, sponsored credit, admin panel backend, access log, blocks and bans |
| [infra/](infra/) | Vultr cluster, Helm chart, deploy automation, migrations runner, smoke test |
| [ingest/](ingest/) | upload, parsing, chunking, embeddings, source summaries, ingest worker |
| [rag/](rag/) | retrieval, cited answers, generated documents, sharing, rag worker |
| [web/](web/) | wizard, two-column notebook view, viewer, login, credits, admin panel |

- [Docs site](https://oliver-zehentleitner.github.io/lasteverLM/) and [live system](https://lasteverlm.zehentleitner.co)
- [Architecture and API contract](docs/architecture.md)
- [The RAG pipeline](docs/rag-pipeline.md) — loaders, chunking, embeddings, pgvector, retrieval, citations, and why each was chosen
- [User interface](docs/ui.md)
- [Repository standard](docs/repository-standard.md)
- [Walkthrough script](docs/walkthrough.md) — the ten-minute recorded tour
- [Why it is built this way](context/index.md)
- [Open work](TASKS.md)
- [Contributing](CONTRIBUTING.md), [Security](SECURITY.md), [Code of conduct](CODE_OF_CONDUCT.md)

Everything runs on one Vultr account: a Kubernetes cluster, Managed
PostgreSQL with pgvector, Object Storage and Serverless Inference for
the language model and the embeddings. Every stage of the pipeline is
an interface with one implementation, so new source kinds, providers
and retrievers are modules, not rewrites.

Delivery is containers only: every service is an image in GitHub's
registry, deployed with one Helm chart, released with one tag. Every
process scales horizontally; PostgreSQL is the only state and also the
job queue for the workers.

The reasoning behind each decision is recorded next to the code with
[Keep the Why](https://keepthewhy.com).

Status: live at https://lasteverlm.zehentleitner.co, deployed on every tag with a smoke test over the public domain. The reasoning behind every decision is browsable in the [live dashboard](https://oliver-zehentleitner.github.io/lasteverLM/keep-the-why-dashboard/).

## License

MIT, see [LICENSE](LICENSE).
