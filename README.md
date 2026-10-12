# lasteverLM

[![Keep the Why](https://keepthewhy.com/assets/badge.svg)](https://keepthewhy.com)

A NotebookLM-style assistant: upload documents, ask questions, get cited answers.

*Please explain this to me.*

This is the parent repository of the lasteverLM family. It holds the
architecture, the reasoning behind it and the coordination between the
service repositories. The code lives there:

| Repository | Purpose |
|---|---|
| [lasteverLM-infra](https://github.com/oliver-zehentleitner/lasteverLM-infra) | Kubernetes cluster on Vultr, manifests, database migrations |
| [lasteverLM-ingest](https://github.com/oliver-zehentleitner/lasteverLM-ingest) | upload, parsing, chunking, embeddings |
| [lasteverLM-rag](https://github.com/oliver-zehentleitner/lasteverLM-rag) | retrieval and answers with citations |
| [lasteverLM-web](https://github.com/oliver-zehentleitner/lasteverLM-web) | three-pane frontend |

- [Architecture and API contract](docs/architecture.md)
- [Why it is built this way](context/index.md)
- [Open work](TASKS.md)

The system is built by several coding-agent sessions working in
parallel, with a human reviewing every merge. The reasoning behind each
decision is recorded next to the code with
[Keep the Why](https://keepthewhy.com).

Status: skeleton. Nothing runs yet.

## License

MIT, see [LICENSE](LICENSE).
