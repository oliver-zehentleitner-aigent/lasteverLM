# The RAG pipeline

How a question becomes a cited answer, stage by stage, with the choice
made at each stage and why. The reasoning behind every choice is recorded
in the `context/` directories; this page is the map. Numbers here are
the production configuration (`infra/chart/values-prod.yaml`).

```
upload / URL / image / audio
   │  ingest: loader → passages (page-aware)
   ▼
chunks (420 regex tokens, overlap 50)  ──►  embeddings (qwen3-embedding-4b, 1024 dims)
   │                                           │
   └───────────── PostgreSQL + pgvector ◄──────┘       one set per library source
                        │
question ──► embedding ─┴─► cosine search in the notebook (k=8, floor 0.3)
                              │
                              ▼
            numbered passages ──► LLM (qwen3.8-27b) ──► answer with [n] markers
                                                            │
                                   [n] → chunk id, page, quote, similarity
```

## 1. Reading sources

Every source kind has one loader in ingest that turns bytes into
*passages*; a passage carries its page number when the kind has pages.

| Kind | Loader | What comes out |
|---|---|---|
| PDF | `pypdf` for the text layer; `pypdfium2` renders pages for the vision model in `vision` and `auto` mode | text per page, page number kept for citations |
| text | the bytes as one passage | text |
| URL | fetched by the worker through a guard that connects only to public addresses, HTML reduced to text with the standard library's parser | text, the URL as the name |
| image | the platform's vision-capable chat model, one billed call: every legible piece of text transcribed verbatim, then a description of the image, in the image's language | text that can be searched and cited |
| audio | MP3, and WAV within 25 MiB, as uploaded; a longer WAV (a 44.1 kHz stereo WAV reaches the cap after about 2.5 minutes; transcription is billed per second, so converting does not change the cost) and M4A/MP4, AAC, Ogg/Opus, FLAC and WebM converted by a minimal ffmpeg to mono 16 kHz MP3 first (stored beside the original, which stays for download); up to 25 MiB and four hours as transcribed, the whole file sent to the platform's transcription model in one billed call (usage kind `stt`); the platform returns no timestamps | one passage without a page number, chunked like text; an answer without speech fails the source, its call billed |

**PDF capture modes.** A PDF is read in one of three modes, chosen per
upload (default from the user's preference `pdf_capture`): `text` takes
the text layer only; `vision` renders every page (pypdfium2, 150 dpi)
and has the vision model transcribe it like an image, one billed call
per page; `auto`, the default, uses the text layer where a page has one
and vision only for the pages that have none, so a scanned or mixed PDF
works and the model is paid only for the pages that need it. A PDF
without any text in `text` mode fails visibly with a message naming the
mode: a source that is "ready" but cannot answer anything is the silent
failure the family forbids (`context/architecture.md`, fail loud).
Every mode is capped at 2000 pages per PDF and fails loud beyond it. A page "has a text layer" only when it is legible: at least 20 visible characters, at least 60 % of them letters; a layer of glyph codes from a font without a usable Unicode map goes to vision in `auto` and is skipped in `text`. There is no classic OCR engine; the vision model does the reading, for
images and for rendered pages alike. A cap (`PDF_VISION_MAX_PAGES`,
100) bounds the cost of one upload (`ingest/context/pdf-capture.md`).

Each source also gets a **summary**: one LLM call over the head of its
text, one paragraph of about 120 words in the document's language. The
summary feeds the generated documents (reports, quizzes, ...) and the
admin overview, never the question answering.

## 2. Chunking

Passages are cut by one chunker in core, `TokenWindowChunker`: sliding
windows of **420 regex tokens with an overlap of 50**, where a token is a
word or a single punctuation character found by a regular expression.
Windows never cross a passage, so a chunk from a PDF belongs to exactly
one page.

**Why windows and not paragraphs.** The sources are PDFs whose
paragraph structure is unreliable after text extraction (line breaks
inside sentences, headers and footers mixed in), web pages reduced to
text, and transcribed images. A fixed window with overlap gives every
chunk a predictable size for the embedding model and the prompt, and
the overlap keeps a sentence cut at a boundary retrievable from the
neighbouring chunk. Semantic chunking (by paragraph or by embedding
similarity between sentences) was not chosen: it needs structure the
inputs do not reliably have, and its benefit shows mainly on long,
well-structured prose, which is not the typical upload here.

**Why 420.** The first version used 800 regex tokens, assuming a regex
token is roughly a model token. Measured on a real 51-page German PDF,
the embedding model counted 1.9 model tokens per regex token: German
compounds and inflections split into several subword tokens. The top-8
context was twice the size the contract intends, doubling the prompt and
its price on every question. 420 regex tokens land near 800 model tokens
for German and near 550 for English; German is what the deployment
serves. Counting with the provider's own tokenizer would be exact and
is the next step if chunk boundaries ever show up in retrieval quality;
it was not taken because it adds a vocabulary dependency per provider to
two services, while a corrected constant removed the measured error
(`core/context/chunking.md`).

## 3. Embeddings

Every chunk is embedded with **`qwen3-embedding-4b`** on Vultr Serverless
Inference through its OpenAI-compatible endpoint, with
`dimensions=1024`. The question is embedded with the same model and
dimension at query time; the two must match, and the setting is pinned
in the chart because the database columns were created as `vector(1024)`
(changing it means a migration and re-embedding every chunk).

**Why this model.** The family decided to run everything on one Vultr
account (cluster, database, object storage, inference), so the choice
was among the platform's models. The 4B embedding model is multilingual,
which matters for German sources, and it is the largest embedding model
the platform offers; a hosted third party (OpenAI, Cohere) was rejected
with the rest of the multi-vendor setup, and a self-hosted Hugging Face
model would need GPU nodes the cluster does not have
(`context/architecture.md`, "Everything on Vultr").

Every embedding call writes one `usage` row priced per million tokens;
an embedding model without a price refuses to start
(`ingest/context/accounting.md`).

**Processed once.** Chunks and embeddings hang on the *library source*,
not on the notebook. The same file uploaded again, or added to a second
notebook from the library, links the existing entry and is neither
stored nor embedded again (`ingest/context/library.md`).

## 4. Vector store

The vectors live in the **Managed PostgreSQL with the `pgvector`
extension**, in the `chunks` table next to the chunk text, page and
source: `embedding vector(1024)`. There is no separate vector database.

**Why pgvector.** PostgreSQL is already the only state of the system and
the job queue for the workers. One store means one backup, one
connection pool, one transaction around "chunk written with its
embedding", and a search that joins the notebook's source links, the
source status and the chunk text in one SQL statement. Supabase Vector,
Pinecone, Qdrant and Chroma were considered when the stack was chosen
and rejected: a second managed service or a second stateful deployment
for a few hundred thousand vectors at most, and a second place where
"which chunks belong to this notebook" would have to be kept consistent
(`context/architecture.md`, the Supabase decision and its successor).

**Distance and index.** Search uses cosine distance (`<=>`); similarity
is `1 - distance`. There is no approximate index (HNSW, IVFFlat) yet:
the search is an exact scan over the notebook's chunks, which is correct
and fast at the sizes a notebook reaches here. An HNSW index with the
notebook filter is the known next step when a notebook grows past tens
of thousands of chunks; pgvector's iterative scan would be needed so the
filter does not starve the index (`rag/context/retrieval.md`).

## 5. Retrieval

For a question in a notebook, rag:

1. checks the user has credit (`core` `has_credit`), otherwise 402;
2. embeds the question (one embedding call, one usage row);
3. runs one SQL statement: chunks of the notebook's **ready** sources,
   ordered by cosine distance, **k = 8**, keeping only chunks with
   similarity **≥ 0.3** (`SIMILARITY_FLOOR`);
4. hands the model the list of the notebook's documents (uploads and
   generated, by kind and title) with the passages, so questions about
   the notebook itself ("which documents do you have", "the mind map
   you made") are answered correctly; only an empty notebook gets the
   fixed refusal without a model call (`rag/context/citations.md`).

Two scoping rules shape what is searched:

- **Uploads first, generated documents capped.** Generated documents
  (reports, quizzes, ...) are indexed as sources of kind `generated`
  and restate the uploads; included freely, the model cited its own
  paraphrase instead of the original. So the uploads fill the k slots
  by score and generated chunks may take at most
  `RETRIEVAL_GENERATED_SLOTS` (2) of them, and only above the floor: an
  original always outranks its paraphrase when both match, and the
  chat still knows and can cite the notebook's own documents
  (`rag/context/retrieval.md`, which records the uploads-only rule this
  replaced and why).
- **"Ask about this" on a generated document** searches that one
  document with k = 12 and no floor: a summary-type question matches no
  chunk strongly, and the scope already bounds the context.

Retrieval uses the question alone; the conversation's previous turns go
to the LLM for context but not into the vector search
(`rag/context/conversations.md`).

**What is not there, on purpose for now.** No reranker, no hybrid
(keyword plus vector) search, no query rewriting. Each is a known
improvement with a known cost in latency and model calls; the measured
problems so far were chunk size and the generated-source feedback loop,
both fixed at their cause.

## 6. Answering and citations

The retrieved chunks go to the LLM (**`qwen3.8-27b`**, reasoning off)
as numbered passages, with a system prompt that allows only those
passages, demands a `[n]` marker on every claim and forbids numbers that
do not exist. The model's answer comes back with markers.

The service then maps every marker back to the chunk it names:
`chunk_id`, the source, its page and a quote from the chunk text. A
marker whose number names no passage is stripped from the answer and
produces no citation, so nothing reaches the reader that looks like a
source but is none; a sentence left without a citation is visibly
unsupported. Markers are normalised (single markers, dense numbering by
first appearance). A provider-side citation feature was rejected: it
cannot be verified against this system's own chunks and ties the
service to one provider (`rag/context/citations.md`).

So a citation is not the model's claim that something is "on page 3".
It is the identifier of the vector chunk that was retrieved for the
question, with the page the chunk was cut from, the chunk's text, and
its similarity score to the question. The frontend opens the cited
passage from that record; a citation into a source that was removed
from the notebook is shown as "source removed", never silently
re-pointed.

## 7. Generated documents

Reports, quizzes, tables, mind maps, infographics and audio are made by
the rag worker from the sources' summaries plus the chunks retrieved for
a fixed focus query per kind ("figures, dates, comparisons" for the
table). Generated sources are excluded from a generator's input, so
every document derives from the user's own material and not from an
earlier paraphrase (`rag/context/outputs.md`). A ready document is
itself indexed as a source of kind `generated` so it can be asked about.

## Configuration

| Setting | Production | Where |
|---|---|---|
| `CHUNK_TOKENS` / `CHUNK_OVERLAP_TOKENS` | 420 / 50 (core defaults) | core `TokenWindowChunker` |
| `EMBEDDING_MODEL` / `EMBEDDING_DIMENSION` | `qwen3-embedding-4b` / 1024 | chart `values-prod.yaml` |
| `LLM_MODEL` | `qwen3.8-27b` | chart `values-prod.yaml` |
| `RETRIEVAL_K` | 8 (12 when scoped) | rag |
| `SIMILARITY_FLOOR` | 0.3 (none when scoped) | rag |
| `RETRIEVAL_GENERATED_SLOTS` | 2 | rag |
