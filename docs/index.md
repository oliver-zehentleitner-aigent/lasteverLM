# lasteverLM

**Material in. Understanding out.** PDFs, text, web pages, images and
audio go in; questions, reports, quizzes, tables, mind maps,
infographics and spoken overviews come out, each sentence traceable to
the passage it came from. A NotebookLM-style assistant, built to be
checked: every claim carries its passages, every document its
generation log.

- **Live:** [lasteverlm.zehentleitner.co](https://lasteverlm.zehentleitner.co) — login by magic link on an allowed domain.
- **Code:** [github.com/oliver-zehentleitner/lasteverLM](https://github.com/oliver-zehentleitner/lasteverLM) — one repository, six services.
- **Docs:** [oliver-zehentleitner.github.io/lasteverLM](https://oliver-zehentleitner.github.io/lasteverLM/) — this site: architecture and API contract, user interface, walkthrough script, repository standard.
- **Why:** [the Keep the Why dashboard](https://oliver-zehentleitner.github.io/lasteverLM/keep-the-why-dashboard/) — every decision with the alternatives it rejected, in the order it was taken.

## How it is built

Everything runs on one Vultr account: a Kubernetes cluster, Managed
PostgreSQL with pgvector, Object Storage and Serverless Inference for the
language model, the embeddings and text-to-speech. Delivery is containers
only: every service is an image in GitHub's registry, deployed with one
Helm chart, released with one tag. Every process scales horizontally;
PostgreSQL is the only state and also the job queue for the workers.

| Directory | Purpose |
|---|---|
| `core/` | shared library: models, settings, auth, rate limiting, usage accounting, provider interfaces, object storage |
| `account/` | magic-link login, sponsored credit, admin panel backend, access log, blocks and bans |
| `infra/` | Vultr cluster, Helm chart, deploy automation, migrations runner, smoke test, local compose stack |
| `ingest/` | upload, URL and image sources, parsing, chunking, embeddings, source summaries, ingest worker |
| `rag/` | retrieval, cited answers, generated documents, audio, sharing, rag worker |
| `web/` | wizard, two-column notebook view, viewer, login, credits, admin panel |

The contract between the services is [Architecture and API
contract](architecture.md); how a question becomes a cited answer is
[The RAG pipeline](rag-pipeline.md); the screens are in [User
interface](ui.md); what every directory must carry is the [Repository
standard](repository-standard.md). The [walkthrough script](walkthrough.md)
is the ten-minute recorded tour.

## How it was built

Seven coding-agent sessions working in parallel, one per directory plus
a head that reviews and merges, with a human maintainer who decides and
tests. Each directory keeps its own `context/` with the reasoning behind
its code; the dashboard above reads all seven.
