# lasteverLM

[![Read the Docs](https://img.shields.io/badge/read-%20docs-yellow)](https://oliver-zehentleitner.github.io/lasteverLM/) [![Keep the Why · live](https://oliver-zehentleitner.github.io/lasteverLM/keep-the-why-dashboard/badge-entries.svg)](https://oliver-zehentleitner.github.io/lasteverLM/keep-the-why-dashboard/) [![ci](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml) [![ktw-lint](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml)

A NotebookLM-style assistant: upload documents, ask questions, get cited answers.

*Please explain this to me.*

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

The system is built by seven coding-agent sessions working in parallel
in this one repository, one directory each, with one of them reviewing
and merging and a human testing the result. The reasoning behind each
decision is recorded next to the code with
[Keep the Why](https://keepthewhy.com).

Status: the services exist and pass their checks; the first deployment is pending the cluster. The reasoning behind every decision is browsable in the [live dashboard](https://oliver-zehentleitner.github.io/lasteverLM/keep-the-why-dashboard/).

## License

MIT, see [LICENSE](LICENSE).
