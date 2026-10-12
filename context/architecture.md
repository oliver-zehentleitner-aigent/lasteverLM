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
**Status:** superseded
**Superseded by:** 1551d8e8-e2b1-41ef-839d-2ef681d6d595
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12

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
**Status:** superseded
**Superseded by:** 1551d8e8-e2b1-41ef-839d-2ef681d6d595
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
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12
**Revisit when:** answer or citation quality of the open-weight models is not good enough for the demo

Both the language model and the embeddings come from Vultr Serverless
Inference, used through the OpenAI SDK with a configurable base URL.
The embedding dimension is a configuration value with a default of
1536, identical in ingest and rag.

**Reason:** it keeps the whole stack on the one cloud account whose
credit pays for the project, needs no second API key, and the
OpenAI-compatible interface means any other compatible provider is a
config change. Citations are built by the rag service itself, so no
provider-specific citation feature is needed (see the entry below).

**Rejected alternatives:** Claude through the Anthropic API with its
citations feature, which maps well onto cited answers but ties the
citation path to one provider and needs a separate key and budget;
OpenAI or OpenRouter for either side, rejected for the same reason.
Embeddings from a model running inside the cluster were briefly
considered and rejected: CPU cost on the cluster for something the
inference API already offers. Claude stays the fallback if the
open-weight models cite poorly, through the same interface.

## Authentication: magic link restricted to allowed e-mail domains, plus a demo token

**Id:** 38a1cd64-0e61-4e5f-9ce6-058d3ad01659
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12

Users log in with a magic link: enter an e-mail address, receive a
link, click, done. Only addresses under domains on an allowlist get a
link; the allowlist lives in the database, is edited in the admin
panel, and is seeded once from an environment variable, so it never
appears in a repository. A demo token from config resolves to a seeded
demo user for development and recorded walkthroughs and is unset in
production.

**Reason:** the deployment is meant for a known group of people who
should be able to create an account without anyone handing out
credentials, and without a password to manage. The allowlist does that.
Keeping the list out of the repositories is a privacy requirement of
the maintainer.

**Rejected alternatives:** Supabase Auth, gone with Supabase (see the
platform entry); e-mail plus password, rejected because it adds reset
flows and password storage for no gain with this user group; a demo
token only, rejected because the project should show real multi-user
separation and the sponsored credit model needs accounts.

## Everything on Vultr: Kubernetes, Managed PostgreSQL with pgvector, Object Storage, Serverless Inference

**Id:** 1551d8e8-e2b1-41ef-839d-2ef681d6d595
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12
**Revisit when:** the hosting credit runs out or a Vultr service is missing something the MVP needs

The cluster, the database with its vector index, the upload storage and
the model inference all come from Vultr. Supabase is out. Mail is the
one external piece, over SMTP configured in the admin panel.

**Reason:** the maintainer holds a hosting credit on this account that
cannot be paid out, so everything that runs there is effectively free,
and one account with one API key is a cleaner story than a cluster on
one provider and data on another. Managed PostgreSQL means no stateful
workload to back up inside the cluster. The pgvector extension is
available there under the name `vector`.

**Rejected alternatives:** Supabase hosted (free tier limits, a second
provider, and nothing it offered that the project needs beyond
Postgres, storage and auth, each of which has a Vultr or an own
replacement); Postgres inside the cluster through an operator
(CloudNativePG), rejected because it adds a stateful workload with a
backup story to operate during a three-day build for a showcase gain
nobody asked for.

## Citations are built by the rag service, not taken from a provider feature

**Id:** 8457792a-46f9-4029-8d9c-cd8089d7e266
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12

Retrieved chunks go numbered into the prompt, the model answers with
`[n]` markers, and rag maps each marker back to the chunk, its source
and page, dropping markers that point at nothing. The citation model
is defined once, in core, and the frontend knows only that model.

**Reason:** this works with every OpenAI-compatible provider and keeps
the provider choice a configuration matter. A provider-side citation
feature would tie the core requirement of the product to one vendor.

**Rejected alternative:** the Anthropic citations API. Better citation
quality out of the box, rejected because it would make the one feature
the product is about provider-specific.

## Shared core library instead of duplicated contracts

**Id:** 97441817-e59f-45c1-aba4-5d585ecd6940
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12
**Revisit when:** a service needs a model or helper the others must not see

The Pydantic models, settings loading, bearer-token resolution, usage
accounting (`record_usage`, `balance_cents`, model prices) and the
provider interfaces live in one Python package, `lasteverLM-core`,
which account, ingest and rag depend on. Installed from Git by tag
first, from PyPI once stable.

**Reason:** three services sharing one database need one definition of
the rows and one way to price a model call; duplicating a hundred lines
three times is where the first drift between services starts. A library
is also where the "one interface, one implementation" rule is enforced
rather than only described.

**Rejected alternative:** copy the shared code into each service.
Faster tonight, rejected because every later change to a contract
would have to land in three repositories in lockstep. Known cost of the
chosen path: a version pin to keep current in three places.

## Usage rows are the debit; no second ledger write

**Id:** 454bd7eb-b5a2-4c63-9544-6425f342a5a6
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12

Every model call writes one `usage` row with its token counts and a
`cost_cents` priced at write time by the service that made the call,
through a core helper and a price table from config. The balance is
the sum of ledger credits minus the sum of usage costs. The account
service only reads usage.

**Reason:** one write per call, done by the service that has the
numbers, cannot drift from a separate debit written later by another
service; and pricing at write time means a price change never rewrites
history. Services share the database, so no service call is needed for
accounting.

**Rejected alternative:** services write raw token counts and the
account service turns them into ledger debits afterwards. Rejected
because it needs a second writer and a reconciliation that can lag or
fail, for the same result.
