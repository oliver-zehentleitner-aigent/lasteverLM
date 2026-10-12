# Architecture

## Microservices on Kubernetes, one repository per service, Python everywhere

**Id:** d28cc444-b721-43b0-bdd8-f848ef827ec9
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12
**Revisit when:** the service count or the hosting budget changes

The system is cut into separately deployable services (ingest, rag, web,
plus an infra repository holding the cluster manifests), each in its own
Git repository under the `lasteverLM-` prefix, all backend code in
Python, deployed to a managed Kubernetes cluster on Vultr. This parent
repository holds the architecture, the family-wide `context/` and the
coordination files; it ships no code.

**Reason:** the project is a portfolio piece whose point is to show
architecture and operations judgement, not only a working chat. Separate
repositories also give each coding-agent session (see `workflow.md`) a
clean workspace with no merge contention, and Kubernetes is the
maintainer's home ground, so the ops cost is known rather than
speculative.

**Rejected alternative:** a single FastAPI monolith in one repository
with Docker Compose. Faster to an MVP and cheaper to run, rejected
because it would demonstrate none of the things the project exists to
demonstrate, and because four agents in one repository would spend their
time on merge conflicts. Known cost of the chosen path: cluster setup and
cross-repository coordination eat time that is not spent on features.

## Supabase as database, vector store, file storage and auth provider

**Id:** 95c444f7-45b9-4ef0-a5be-cc2b47e73d9d
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12
**Revisit when:** retrieval quality or Supabase limits become a problem

Notebooks, sources, chunks with their embeddings (pgvector), chat
messages and uploaded files all live in one Supabase project. Services
talk to it with the Supabase client and the service-role key; the
frontend never holds that key.

**Reason:** one managed component covers Postgres, vector search, object
storage and (if enabled, see below) authentication, which keeps the
cluster to the services this project actually writes. Supabase is also a
stack the project's audience knows, so it needs no explanation in a demo.

**Rejected alternative:** a self-run Postgres with pgvector plus MinIO
inside the cluster. Rejected because it adds two stateful workloads to
operate for no gain in the demo. A dedicated vector database (Qdrant,
Weaviate) was not seriously in contention: pgvector is enough at this
data volume and avoids a second store to keep consistent.

## Hosted Supabase or self-hosted on the cluster

**Id:** b376e44e-18b5-4857-af4b-5f3fcb7ecb4d
**Type:** decision
**Status:** open
**Evidence:** unknown
**Source:** planning conversation, 2026-10-12

Whether the Supabase project runs on supabase.com (free tier) or is
self-hosted on the Vultr cluster is not decided yet. The proposal on the
table is the hosted free tier, so that the whole hosting budget goes into
the cluster and no ops time goes into running Supabase. Until decided,
services must not assume anything beyond the public Supabase API.

## Model providers for the LLM and the embeddings

**Id:** b059feca-be73-4d1f-8af6-e5d3fd46b228
**Type:** decision
**Status:** open
**Evidence:** unknown
**Source:** planning conversation, 2026-10-12

Two provider choices are open: which LLM answers questions, and where
the embeddings come from (an API such as OpenAI, or a model running in
the cluster). The proposal on the table is Claude for answers, because
its citations feature maps directly onto the "answer with sources"
requirement, with the embedding path still undecided. The embedding
dimension in the `chunks` table depends on this choice, so the schema
carries a placeholder until it is settled. Alternatives considered:
unknown beyond the two embedding paths named above.

## Authentication: real login or demo token

**Id:** 38a1cd64-0e61-4e5f-9ce6-058d3ad01659
**Type:** decision
**Status:** open
**Evidence:** unknown
**Source:** planning conversation, 2026-10-12

Whether users log in through Supabase Auth or the deployment is reached
with a single shared demo token is not decided. Supabase Auth is small
effort and shows multi-user data separation; the demo token is less
effort and enough for a recorded walkthrough. The API contract in
`docs/architecture.md` takes a bearer token either way, so the services
can be built before this is settled.
