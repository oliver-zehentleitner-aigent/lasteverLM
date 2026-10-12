# lasteverLM

[![Keep the Why](https://keepthewhy.com/assets/badge.svg)](https://keepthewhy.com)

A NotebookLM-style assistant: upload documents, ask questions, get cited answers.

*Please explain this to me.*

This is the parent repository of the lasteverLM family. It holds the
architecture, the reasoning behind it and the coordination between the
service repositories. The code lives there:

| Repository | Purpose |
|---|---|
| [lasteverLM-core](https://github.com/oliver-zehentleitner/lasteverLM-core) | shared library: models, settings, auth, usage accounting, provider interfaces |
| [lasteverLM-account](https://github.com/oliver-zehentleitner/lasteverLM-account) | magic-link login, sponsored credit, admin panel backend |
| [lasteverLM-infra](https://github.com/oliver-zehentleitner/lasteverLM-infra) | Kubernetes cluster on Vultr, manifests, migrations runner |
| [lasteverLM-ingest](https://github.com/oliver-zehentleitner/lasteverLM-ingest) | upload, parsing, chunking, embeddings |
| [lasteverLM-rag](https://github.com/oliver-zehentleitner/lasteverLM-rag) | retrieval and answers with citations |
| [lasteverLM-web](https://github.com/oliver-zehentleitner/lasteverLM-web) | three-pane frontend, login, credits, admin panel |

- [Architecture and API contract](docs/architecture.md)
- [User interface](docs/ui.md)
- [Repository standard](docs/repository-standard.md)
- [Why it is built this way](context/index.md)
- [Open work](TASKS.md)

Everything runs on one Vultr account: a Kubernetes cluster, Managed
PostgreSQL with pgvector, Object Storage and Serverless Inference for
the language model and the embeddings. Every stage of the pipeline is
an interface with one implementation, so new source kinds, providers
and retrievers are modules, not rewrites.

The system is built by six coding-agent sessions working in parallel,
with a human reviewing every merge. The reasoning behind each
decision is recorded next to the code with
[Keep the Why](https://keepthewhy.com).

Status: skeleton. Nothing runs yet.

## License

MIT, see [LICENSE](LICENSE).
