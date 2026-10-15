# rag

[![CI](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml)
[![ktw-lint](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml)
[![Keep the Why](https://img.shields.io/badge/Keep_the_Why-context%2F-2b6cb0)](https://keepthewhy.com)

The rag service of lasteverLM: retrieval over one notebook's chunks,
answers with citations mapped back to source and passage, the chat
conversations, and the generated documents (report, quiz, table, mind map,
infographic, audio, decision, chart, flashcards). The API contract and the data model live
in the repository root, [`docs/architecture.md`](../docs/architecture.md);
this directory implements the `/api/rag` prefix.

## Endpoints

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/api/rag/notebooks/{id}/ask` | `{"question", "conversation_id", "scope": {"output_id"}?, "source_ids"?, "url_refresh"?}` | `Answer`; with `plan` instead of an answer when the message asks for actions, see **Agent chat** |
| GET | `/api/rag/conversations/{id}/plans/{plan_id}` | | the plan with every step's state |
| POST | `/api/rag/conversations/{id}/plans/{plan_id}/confirm` | | runs a proposed plan; 409 when confirmed or cancelled already |
| POST | `/api/rag/conversations/{id}/plans/{plan_id}/answer` | `{"question_id", "choice"?, "text"?}` | the plan, now proposed, with the answer applied; 409 when it is not asking or the question is no longer open |
| POST | `/api/rag/conversations/{id}/plans/{plan_id}/cancel` | | cancels a proposed or asking plan |
| GET | `/api/rag/notebooks/{id}/suggestions` | | `{"suggestions", "cached"}`: starting questions, see **Suggestions** |
| POST | `/api/rag/messages/{id}/feedback` | `{"rating": "up" \| "down", "comment"?}` | `Message` with its `feedback`; the owner's, for answers only (409 otherwise), a new rating replaces the old |
| GET | `/api/rag/notebooks/{id}/conversations` | | `[Conversation]`, oldest first |
| POST | `/api/rag/notebooks/{id}/conversations` | `{"title"?}` | 201 `Conversation`; title defaults to `Chat N` |
| PATCH | `/api/rag/conversations/{id}` | `{"title"}` | `Conversation`; title trimmed, 1–80 chars, else 422 |
| DELETE | `/api/rag/conversations/{id}` | | 204, the conversation and its messages |
| GET | `/api/rag/conversations/{id}/messages` | | `[Message]`, oldest first |
| GET | `/api/rag/chunks/{chunk_id}` | | `ChunkView`: the verbatim chunk, its page, position and source |
| POST | `/api/rag/notebooks/{id}/outputs` | `{"kind", "options"?, "source_ids"?, "url_refresh"?}` | 202 `Output`, status `waiting` or `processing` |
| GET | `/api/rag/outputs/options` | | the options catalogue, see below |
| POST | `/api/rag/notebooks/{id}/charts/propose` | `{"instructions"?, "max"?, "source_ids"?, "url_refresh"?}` | `{"candidates", "reason"}`: candidate charts, nothing stored, see below |
| POST | `/api/rag/estimate` | `{"kind", "options"?}` or `{"action", "options"?}` | the charge range before it runs, see **Estimate** |
| POST | `/api/rag/outputs/voice-sample` | `{"voice", "speed"?, "language"?}` | `{"url", "cached"}`: a short MP3 preview of a voice |
| GET | `/api/rag/notebooks/{id}/outputs` | | `[Output]` made in that notebook, not in the trash |
| DELETE | `/api/rag/notebooks/{id}/outputs` | | 204, every output made in that notebook into the trash |
| GET | `/api/rag/library/outputs?kind=&trash=` | `kind` optional, `trash` default false | `[Output]`, the caller's outputs from every notebook, newest first; with `trash=true` the trashed ones |
| GET | `/api/rag/outputs/{id}` | | `Output`; 404 when trashed; while waiting or processing `phase` says what is happening now, see **Phase** |
| PATCH | `/api/rag/outputs/{id}` | `{"title"}` | `Output`; title trimmed, 1–200 chars, else 422; 409 unless ready; renames its generated source too |
| DELETE | `/api/rag/outputs/{id}` | | 204, into the trash |
| POST | `/api/rag/outputs/{id}/restore` | | 204, out of the trash |
| DELETE | `/api/rag/outputs/{id}/purge` | | 204, deleted for good; 409 unless in the trash |
| POST | `/api/rag/outputs/{id}/judge` | `{"level": "low" \| "medium" \| "high"}` | `Output` with every claim judged, nothing revised or removed; see **Judge** |
| POST | `/api/rag/messages/{id}/judge` | `{"level"}` | `Message`: an answer's paragraphs judged against its citations |
| POST | `/api/rag/outputs/{id}/share` | | `{"share_token"}` |
| DELETE | `/api/rag/outputs/{id}/share` | | 204 |
| GET | `/api/rag/shared/{token}` | no auth | the document without ids |
| GET | `/api/rag/shared/notebooks/{token}` | no auth | `{"title", "sources": [{"name", "kind"}], "outputs": [SharedOutput]}`, see below |
| GET | `/api/rag/admin/stats` | viewers and admins | `AdminStats`, see below |
| GET | `/api/rag/admin/stats/daily?days=` | viewers and admins; `days` 1–365, default 30 | `DailyStats`, see below |
| GET | `/api/rag/admin/outputs?id_prefix=` | viewers and admins; 6–32 hex digits of an output id, hyphens ignored, any case (422 otherwise) | `{"matches": [{"id", "notebook_id", "notebook_title", "kind", "title", "status", "error", "created_at", "finished_at", "deleted_at", "owner": {"id", "email"}, "attempts", "attempt_log"}], "truncated"}`, at most 20, newest first; a viewer gets the email masked (core's `mask_email`) |
| GET | `/api/rag/admin/feedback?days=` | viewers and admins; `days` 1–365, default 30 | `{"days": [{"day", "up", "down"}], "latest_down": [{"message_id", "notebook_id", "at", "comment", "answer", "question"}]}`, the 20 newest down-rated answers; a viewer gets the counts with `latest_down: []` and `"detail": "admins only"` |
| DELETE | `/api/rag/admin/users/{id}` | admins only | 204, see below |
| GET | `/healthz`, `/api/rag/healthz` | no auth | core's `Health`: `{"status": "ok", "version", "commit", "dependencies": {"postgres", "storage", "inference"}}`, each `ok` or `down` (core's `DependencyProbe`: 2 s per check, cached 15 s; `storage` only with object storage configured); a dependency that is down never fails the probe |

Every other endpoint takes `Authorization: Bearer <token>`. Errors are
`{"error": "<message>"}`: 401 unauthenticated, 402 credit exhausted,
403 admin only, 404 not yours or missing, 409 asking about an output that
is not ready, 422 an invalid body (an ask without `conversation_id`).
A model call the user waits for (a chat answer, the agent's planning,
starting questions, a voice sample) is tried once more when it fails;
the second failure is 502 `{"error": "the model did not answer", "code":
"model_no_answer", "cause"}`, with `cause` one of `timeout`,
`rate_limited`, `provider_error`, `empty_answer`, `truncated_answer`,
`unparseable_answer`, `no_audio` or `unknown`, for the web to say in the
user's language. Both attempts are billed when the provider charged them.

**Conversations.** A notebook has any number of conversations, one per
chat tab: `{"id", "notebook_id", "title", "created_at"}`. Every message
belongs to one; closing a tab is `DELETE`, which removes its messages
too. A new conversation without a title is `Chat N`, one above the
highest `Chat n` still open. `ask` requires `conversation_id` (no default
conversation); both messages are written into it, a scoped question
(`scope.output_id`) included. The model sees the newest six messages of
that conversation (each cut to 1000 characters, citation markers
removed) to resolve what a follow-up refers to; the answer still comes
from the retrieved passages only, and retrieval uses the question alone.

**Admin overview.** `GET /api/rag/admin/stats` counts across all users,
read only, with every key present (zeros included):
`{"notebooks": {"total"}, "messages": {"total", "last_24h"}, "outputs":
{"by_kind": {<each kind>}, "by_status": {<each status>}}, "jobs":
{"pending", "running", "failed"}, "shared": {"outputs"}}`. A job is
`pending` while waiting or processing without a live claim, `running`
while processing under a claim younger than ten minutes (the worker's
stale-claim limit), `failed` once failed; `shared.outputs` counts the
outputs that have a share token now. Views of shared outputs are in
account's visitor log (`/admin/visits`, path `/s/`).
`GET /api/rag/admin/stats/daily` feeds the charts:
`{"days": [{"day", "messages", "outputs", "outputs_by_kind": {<each kind>}}]}`,
one entry per UTC day for the last `days` days, oldest first and ending
today, every day and every kind present; `messages` counts questions and
answers written that day, `outputs` the outputs created that day in any
status. One query, read only. Both only read, so
the check is core's `admin_read` over `users.role` (`admin_role`):
admins and viewers pass, anyone else gets 403 `admin only`. A viewer is a
plain user everywhere else in rag, credit included.

**Deleting a user.** `DELETE /api/rag/admin/users/{id}` is account's
first step when an admin deletes a user (core's `admin_only`, admins
only), before ingest deletes the notebooks. It deletes the stored files
of the user's outputs (the audio MP3s), then, in one transaction, the
user's generated sources with their chunks, the user's outputs (also
those of deleted notebooks and in the trash), and the messages and
conversations of the user's notebooks. Notebooks and uploads stay for
ingest. Always 204, also when nothing is left or the user never
existed, so account can retry. A file that cannot be deleted is a 502
`could not delete stored object <key>` and no row is touched.

**Ask.** `answer` cites inline as single `[n]` markers, numbered 1..n in
order of first appearance; `n` maps to an entry in `citations` (`source_id`, `source_name`, `source_kind`, `chunk_id`,
`page`, `quote`, `similarity`, `chunk_index`, `chunk_count`). A citation
carries its provenance: `quote` is the verbatim text of the chunk
(never trimmed), `similarity` the cosine similarity the search
gave that chunk for this question (3 decimals), `chunk_index` (0-based)
and `chunk_count` its position in its source ("chunk 12 of 43"). The
stored assistant message keeps the same fields; messages written before
they existed have them as `null`. `GET /api/rag/chunks/{chunk_id}`
returns one chunk for its owner (`{"chunk_id", "source_id",
"source_name", "source_kind", "page", "chunk_index", "chunk_count",
"text"}`, 404 otherwise), so a reader can open the exact passage.
An answer that cites goes through the same support check as a generated
output (see Provenance): `units` holds one `{"text", "refs", "support"}`
per paragraph (its text as in `answer`, markers included) and `check`
the counts; both are stored with the assistant message and are `null`
for an answer without citations (one from the document list, the
refusal) and for messages from before. An answer in another language
than its cited passages (told apart by frequent English and German
words, per paragraph) is "translated": a paragraph with low overlap
there is `unverified`, not `unsupported`.
Text from the user's files is data in every prompt: both system prompts
say so, a name (file, document, notebook) is one line of at most 120
characters, and marker-shaped text in sources and summaries (`[2]`,
`[1, 3]`) reaches the model as `(2)`, `(1, 3)`, so a source cannot open a
fake passage or pass for a citation; the stored chunk and the quote stay
verbatim.
Retrieval is top-k by cosine similarity over the
notebook's ready sources with a similarity floor. An unscoped question
searches the uploads and the generated documents separately: the uploads
fill the k slots by score, and generated chunks above the floor may take
at most `RETRIEVAL_GENERATED_SLOTS` of them (default 2); the passages list
the uploads first, so an original precedes its paraphrase. The system
prompt lists the notebook's ready documents by kind and title (uploads and
generated), so a question about the notebook itself is answered even when
no passage matches; only a notebook without any ready document gets the
fixed refusal without a model call. `scope.output_id` restricts retrieval
to one generated document, without a similarity floor and with a larger
k, since the scope bounds the context.

**Source selection.** `source_ids` on `ask` and on `POST .../outputs` are
the sources the user ticked: link ids (the `id` of ingest's `Source` in
this notebook), uploads only. Absent or empty means all; an id that is not
an uploaded source of the notebook is a 422 (`source_ids: <id> is not a
source of this notebook`). On `ask` the uploads search is filtered to the
selection; the generated slots are unchanged, and the document list in
the system prompt still names every document but marks the uploads
outside the selection `not in scope`, so "why don't you see X" is
answered. A `scope.output_id` wins over the selection. On an output the
selection is stored as `options.sources` (the ids, deduplicated) and the
generator reads only those sources' summaries and chunks, balanced over
the selection; if none of them is ready when the job runs, the output
fails with `none of the selected sources is ready`. The shared view
(`/shared/{token}`) leaves `options.sources` out: it names the owner's ids.

**Outputs.** `POST /outputs` inserts the job and answers at once. The
worker entrypoint (`lasteverlm-rag-worker`) claims jobs from the
`outputs` table with `SELECT ... FOR UPDATE SKIP LOCKED` (a `waiting` row
once none of the uploads it reads, its selection or all, is still processing; a claim counts as an attempt, three
attempts fail the job, a claim older than ten minutes is abandoned), generates the document from the source
summaries plus the chunks retrieved for the kind's focus query, and
indexes the result as a source of kind `generated` in the same notebook
(chunked with core's token-window chunker, the same one ingest uses),
so the chat can cite it; `Output.source_id` names that source.

**Provenance.** Every kind cites the numbered passages of its prompt,
the same discipline as a chat answer: every unit (a report paragraph
that is not a heading, an infographic fact or section, an audio
paragraph or turn, a table row, a quiz question, a mind-map node below
the root) carries `refs` (passage numbers) and
`support`, the result of a deterministic check after generation, with no
second model call. A unit is `supported` when every ref names a passage
of the prompt and at least half (`OVERLAP_THRESHOLD = 0.5`) of its
content words occur in its cited passages together (method
`lexical-overlap-v2`: lowercased words of three or more characters or
with a digit, common English and German function words left out, cut to
five characters); `unsupported` without refs, with a ref no passage has,
or below the threshold; `unverified` when the refs are valid but the
overlap is low and the unit is in another language than its cited
passages (English or German, told per unit by frequent words), where
word overlap cannot tell; a chosen `language` alone does not count. A
unit the words support is also checked for negation
(`lasteverlm_rag/negation.py`, spaCy 3.8.7 with `en_core_web_sm` and
`de_core_news_sm`, loaded once per process on first use): when one of its
clauses states the same predicate of the same subject as the passage
clause it matches, with the opposite polarity ("is not open" over "is
open"), it is `possible_contradiction` instead. Quizzes and flashcards are
not checked for it (their explanations negate wrong options on purpose).
The calibration is in `docs/negation-eval.md`; the check adds about
270 MB of memory to a process that loads the models and 446 MB to the
image. The summary counts each value (`supported`, `unsupported`,
`unverified`, `possible_contradiction`). An interviewer's question without refs is no
claim and gets no `support`, nor does the mind map's root (it names the
whole map) unless it cites. A failing unit is kept and marked, never
dropped, and never fails the output. The report keeps `[n]` markers in
`content.markdown` (unknown numbers are removed) and lists
`content.units: [{"text", "refs", "support"}]`; infographic facts and
sections, the audio transcript entries, quiz questions and mind-map
nodes carry the two fields themselves; a table keeps `rows` as lists of
cells and adds `row_refs: [{"refs", "support"}]`, one per row (a quiz
question is checked with its answer and explanation). `Output.provenance` is the generation log, written when the
output is ready, for every kind (`null` for outputs from before): `{"version", "prompt_version", "model", "options",
"focus_query", "retrieval": {"k", "floor", "candidates": [{"chunk_id",
"source_id", "source_name", "page", "similarity", "in_prompt"}]},
"passages": [{"n", "chunk_id", "source_id", "source_name",
"source_kind", "page", "chunk_index", "chunk_count", "similarity",
"quote"}], "usage": {"llm": {"tokens_in", "tokens_out"}, "embedding":
{"tokens_in"}, "tts": {"seconds"}}, "started_at", "finished_at",
"check": {"method", "threshold", "supported", "unsupported",
"unverified"}}`. The shared view carries it too, without `chunk_id`,
`source_id` and the source selection, so a shared document can be
checked without logging in.

**Library and trash.** An output belongs to the user, not the notebook:
`Output.notebook_id` is the notebook it was made in and turns `null`
when ingest deletes that notebook (the foreign key sets it), while
`origin_title` keeps the notebook's title from the moment the output was
created. `GET /library/outputs` lists the caller's outputs from every
notebook. Its generated source is a library row of the user's, so ingest's
library picker can link it into another notebook, where the chat searches
and cites it without reprocessing. Deleting an output moves it to the
trash (`deleted_at`, `purge_at`): it and its generated source leave every
notebook, its share link answers 404, and its file stays. Restoring
links the source into the origin notebook again if it still exists;
links into other notebooks are not restored, as with ingest's library
trash. `DELETE /notebooks/{id}/outputs` trashes every output made in
that notebook, for the web's "delete the outputs too" before ingest
deletes the notebook. The worker purges a trashed output once the
owner's `trash_days` preference (default 14) has passed, at start and
then hourly; `DELETE /outputs/{id}/purge` does it at once. A purge
deletes the stored file first, then the generated source with its chunks
and links, then the row; a file that cannot be deleted is logged (the
sweep) or a 502 naming its key (the endpoint), and the rows stay for the
next try. A job whose notebook is deleted before it ran fails with "the
notebook was deleted".
`Output.error` is a public text: rag's own reasons (no ready source,
none of the selected sources ready, an answer that did not match the
document format, audio unavailable) as they are, otherwise a fixed text
per class (model provider, storage, internal); the exception's own
message, which can name endpoints or quote model output, goes to the log
only. A text-to-speech answer without audio is a provider failure, billed
like any other synthesis.

The focus-query chunks are balanced across sources: every ready upload
contributes its best two chunks whatever their score, the rest of the
budget (at least `RETRIEVAL_K`, two per source, at most 24 passages) goes
by score, so one large or very relevant source cannot fill the input on
its own. Every generator prompt says to cover all listed sources; the
mind map's root spans them, with a branch per source when they are on
distinct topics. After generation, a source whose distinctive file-name
words (words no other source's name has) appear nowhere in the document
is logged as a warning with the output id; the document is kept.

**Options.** `options` on `POST .../outputs` takes `language` (one of
ten codes, `de`, `en`, `fr`, ...) and `instructions` for every kind;
`report_style` and `length` for a report; `question_count`,
`difficulty` and `audience` for a quiz; `voice`, `speed`, `audio_style`
and `audio_voice_2` for audio; and the decision's own (below).
`instructions` is the user's own note to the generator (at most 500
characters, whitespace collapsed, blank dropped). It is given below the
system rules and steers focus, emphasis and tone. It never overrides the
rules, the citation rules or the reply format, and it is recorded with
the options in the provenance log. A report's `report_style` is
`briefing` (default), `detailed`, `executive_summary`, `explainer` (for
newcomers) or `academic`, and its `length` is `short` (at most 500
words), `medium` (default, at most 1200) or `long` (at most 2500): an
upper bound, shorter when the material says less, and the prompt
forbids adding facts, roles, steps or reasons the material does not
state to reach it.
A quiz asks for exactly `question_count` questions (5–30, default 10):
fewer gets the corrective retry, more are cut. Its `difficulty` is
`easy`, `medium` (default) or `hard`, and its `audience` is `children`,
`teens`, `adults` (default) or `experts`. Flashcards take `card_count`
(5–50, default 15; fewer gets the corrective retry, more are cut),
`difficulty` and `audience` as the quiz. Their content is `{"cards":
[{"front", "back", "hint"?, "refs", "support"}]}`: one unit per card,
its back the claim checked with its front, as a quiz answer is, judge
included. Report, quiz and flashcard defaults are stored on the output.
`audio_style` is `overview` (default), `story`, `conversation` or `faq`.
An FAQ has 5 to 8 questions a listener would most likely ask about the
material, each followed by its answer: the interviewer asks with `voice`,
the expert answers with `audio_voice_2`, in strict turn. The answers get
the support check, and the questions carry no claim.
`audio_voice_2` is the expert's voice and only valid for `conversation` and `faq`,
where it defaults to the next voice with the same native language as
`voice` in catalogue order (`ryan` → `aiden`, `vivian` → `serena`), or
`ryan` when there is none. An option the kind does not take, an unknown
key, code, style or voice, a second voice equal to the first, or a speed
off the offered range (0.75–1.5 in steps of 0.25) is a 422. Without `language` the document
follows the language of its sources; with it the generator is told to
write everything, the title included, in that language. Audio defaults
to `TTS_VOICE` and speed 1.0. The resolved options are stored on the
output (`outputs.options`) and returned as `Output.options` and on the
shared view. `GET /api/rag/outputs/options` lists the languages, the
voices (`id`, `label`, `gender`, native `language`, from the Qwen3-TTS
model card), the default voice, the styles and the default style, the
speed range, `instructions.max_chars`, the report's styles and lengths,
the quiz's count range, difficulties and audiences (each with its
default), the chart types and limits (`chart`) and which options each kind takes, so clients hardcode nothing; the language preference itself
lives in account and the web sends it explicitly.

**Voice previews.** `POST /api/rag/outputs/voice-sample` speaks one or
two fixed sentences in the requested language (default `en`) with that
voice and speed (default 1.0), validated against the same catalogue
(422 otherwise). The file is stored at
`samples/<voice>/<speed>/<language>.mp3`; the first request synthesizes
it (one `tts` usage row for the caller, about one cent, 402 without
credit), every later one, from any user, gets the stored file
(`"cached": true`) without a model call. The URL is presigned for one
hour. 503 when the deployment has no text-to-speech.

**Verification levels.** `options.verification` says how much checking
an output gets and may cost: `basic` (default, absent when stored) is the
word check and the negation check, free; `standard` also judges every
unit those doubt (`unsupported`, `unverified`, `possible_contradiction`)
once at the `low` judge, annotate only (`provenance.judge`: `{"mode":
"doubted", "judged", "level", "model", "verdicts", ...}`); `thorough` is
the judge at `medium` with revision, below (stored as `verification:
"thorough"` with `judge: "medium"`); `bulletproof` is the judge at
`high` with revision and, beside it on every unit and round, a second
judge of another family (`SECOND_JUDGE_MODEL`, default
`deepseek-v4.1-flash`, chosen in `docs/second-judge-eval.md`; it needs a
`MODEL_PRICES` entry). A unit counts as supported only if both say so; if
both fail it, it is revised and removed as at thorough; if they disagree
it is `disputed` ("the two judges disagree; read the passage yourself"),
revised like a failing unit and, still disputed after the last round,
kept and marked, never removed and never passed. Its `judge` then holds
each judge's own verdict, `first: {"model", "verdict", "reason", "quote"}` and
`second: {"model", "verdict", "reason", "quote"}`, and the log
`second_model`. On synthetic cases about one in five true claims ended
disputed. Bulletproof is slower and dearer than thorough. Sending both `verification` and
`judge` is 422; charts take neither. `GET /outputs/options` lists the
levels, and `POST /estimate` with a `kind` adds `levels`: `{"basic",
"standard", "thorough", "bulletproof"}`, each `{"min", "max"}` in euro cents, the
output's price at that level. A chat answer follows the user's level
(account's `verification_level`, else their older `judge_default`: off
basic, low standard, medium thorough, high bulletproof), annotate only,
inside the answer's request: standard judges its doubted paragraphs at
low, thorough every paragraph at medium, bulletproof every paragraph at
high and by the second judge, disagreement marked disputed;
`Message.support.judge` holds the summary.

**Judge.** `options.judge` (`off` by default, `low`, `medium` or
`high`) is offered for every kind except `chart`, whose values already
get the exact number check. With a level set, the word check is followed
by the judge: the level's model (`JUDGE_MODELS`, another family than the
author model) checks every claim unit against its cited passages, one
call per unit (`lasteverlm_rag/judge.py`). Its verdict is `supported`,
`contradicted` or `not_in_source`, with a reason and the decisive quote.

- **Rounds.** Units judged `contradicted` or `not_in_source` go to one
  call of the author model. It gets only those units, with the judge's
  reasons and their passages, and corrects each unit in its own form or
  drops it. A revision that does not fit the unit's form counts as none.
  Only the revised units are judged again, for at most three rounds.
- **Removal.** A unit that still fails after the last round, or that the
  reviser dropped, is removed from the output. It is listed in
  `provenance.judge.removed` (`text`, `verdict`, `reason`, `round`) and
  never dropped silently.
- **Annotations.** Every judged unit carries `judge: {"level", "model",
  "verdict", "reason", "quote", "round"}`. The word check runs again on
  the final units.
- **Log.** `provenance.judge` is `{"level", "model", "rounds": [{"round",
  "judged", "verdicts", "usage", "revision"?: {"revised", "dropped",
  "usage"}}], "removed"}`, and `provenance.usage.judge` holds the judge's
  tokens.
- **Order.** Audio is judged before it is spoken. A decision's agreement
  follows its judged evidence.
- **Billing and failures.** Judge calls are billed as `llm` usage of the
  judge model. A judge call without a usable answer (empty, unparseable,
  an unknown verdict, an SDK error) is tried once more. If that fails
  too, the unit is kept and marked `judge: {"verdict": null, "reason":
  "the judge gave no usable answer: <kind>"}`, counted as
  `no_usable_answer` in the round's verdicts, and never revised or
  removed. It never fails the output. The judge may use up to 4000
  output tokens, because some judge models reason before they answer.

`POST /outputs/{id}/judge` judges a ready output on request. It only
annotates, adds an entry to `provenance.judgements` and answers 409
`nothing to judge: no cited passages` for an output without logged
passages. `POST /messages/{id}/judge` does the same for a chat answer's
paragraphs against its citations, stored with the message's support.
Both are synchronous, need credit, and run four judge calls at a time.

**Reading when used.** A source linked into a notebook stays `added` (not
read) until something needs it. Before an output is created or a question
is answered, rag asks ingest, with the caller's own bearer, to read the
selected sources not read yet (`POST /api/ingest/sources/process`).

- **Refresh per page:** each web page in `url_refresh` (library ids of
  selected web pages) is checked again (`POST
  /api/ingest/sources/{link_id}/refetch`). All other pages use the
  cached version. An unchanged page costs nothing, and anything else in
  `url_refresh` is a 422. A page not read yet or being read is fresh
  already and is not checked. A changed page moves its link to a new
  library row, so waiting follows the link, not the library id. Ingest
  refusing or being down is a 502 `ingest: …`, and nothing is created.
- **Waiting:** ingest marks these sources `processing` until it is done.
  An output job waits for them, as it waits for any processing source. An
  answer waits up to `ANSWER_READ_WAIT_SECONDS` (60) and then answers
  from what is ready, ending with "Still being read: …".
- **Not covered:** a chart reads nothing (it is drawn from passages
  already read). A step the worker runs (an agent plan's explanation)
  has no bearer and uses only what is ready.
- **Estimate:** `POST /estimate` with `notebook_id` (and `source_ids`,
  `url_refresh`) adds `separate`: one line per source to read and per
  page to re-read, `{"library_id", "label", "basis", "min", "max"}` at
  ingest's per-source price (`POST /api/ingest/sources/estimate`). These
  are ingest's charges, so they are not in the total. An agent plan with
  an output lists the notebook's unread sources the same way.

**Sources that could not be read.** A selected source with status `failed`
stops an output. All uploads count as selected when nothing is selected.

- **On create:** the request is refused with 409 `Source '<name>' could
  not be read: <ingest's error>`. Nothing is created or charged.
- **While waiting:** if the source fails while the output waits for it,
  the worker fails the output with that message before any model call,
  so nothing is charged.
- **Retry path:** a failed web page listed in `url_refresh` is read
  again instead.
- **Answers:** an answer names such a source at its end and is never
  silent about it.
- **Estimate:** `POST /estimate` with `notebook_id` lists them under
  `blocked: [{"library_id", "name", "reason"}]`.
- **Waiting limit:** an output that waits more than 30 minutes for its
  sources to be read fails with `Source '<name>' did not become ready
  within 30 minutes`, uncharged and kept.

**Failed attempts.** An output's `error` after a failed attempt says what
happens next. While a retry is pending, it names the failure and ends
"attempt n of 3 follows". After the last attempt it says so, names the
model and the error class (never the provider's message), and states
whether calls were charged: "the model provider failed 3 times (glm-5.3:
timeout); no further attempt; nothing was charged". The worker logs every
failed attempt at WARNING with the output's short id (core's `short_id`,
its first eight hex digits), the attempt, the model, the error class and
the message, never a prompt.

Every failed attempt is also kept on the row (`outputs.attempt_log`,
migration `0017_rag_output_attempts.sql`), so the history outlives the
pods' logs: `Output.attempt_log` is a list of core's `AttemptRecord`,
`{"at", "attempt", "model", "error_kind", "provider_status", "message",
"service": "rag"}`, oldest first. `error_kind` is `provider`,
`provider_refused`, `configuration`, `timeout` or `internal`, and the
message is core's own text, never a prompt or source text. Outputs from
before have `[]`. `outputs.finished_at` is set when an output becomes
ready or failed.

**Phase.** While an output waits or runs, `Output.phase` is
`{"step", "since", "n"?, "of"?, "sources"?, "error"?}`. It is `null`
once the output is ready or failed. Each step is one that really
started:

| Step | When | Fields |
|---|---|---|
| `waiting_for_sources` | status `waiting`, computed on read | `sources`: the names still being read |
| `retrieving` | embedding the focus query and choosing passages | |
| `deciding` | the decision model's call (decision only) | |
| `writing` | the LLM writes the document (a decision's evidence) | |
| `checking` | the support check (a chart's number check) | |
| `judging` | a judge round (judge option only) | `n` round, `of` 3 |
| `revising` | the revision after a judge round | `n` round |
| `synthesizing_speech` | an audio segment | `n` segment, `of` segments |
| `indexing` | embedding the result for chat | |
| `retry` | between attempts | `n` next attempt, `of` 3, `error` e.g. `glm-5.3: timeout` |

The worker writes a new step at once, together with the claim's
heartbeat in one update (`outputs.phase`, migration
`0013_rag_output_phase.sql`). A counter of the same step is written at
most every 5 s. There is no percentage and no invented counter.

**Claim heartbeat.** A running job refreshes its claim (`claimed_at`) at
most once a minute: before each model call, each judge call and each
speech segment. Only a job whose worker stopped beating for 10 minutes is
taken over, so a long run (a judged report, a long audio) is never run a
second time, and never charged twice, while it is still going.

**Agent chat.** A chat message first goes to a planning call (the LLM
with tools, `complete_tools`). That call sees the user's message, their
earlier questions and the names of the notebook's documents and outputs,
never a passage.

- **Tools:** `add_url(url)`, `add_from_library(query)`,
  `create_output(kind, options)` (every kind but chart, its options as
  the catalogue lists them), `explain_output(output_id or "step:<n>",
  question?)`, `list_sources()`, `list_outputs()`. None deletes anything,
  and none touches the account.
- **No tool call:** the message is answered as before. The planning call
  and the answer book under one `chat_answer` action.
- **Tool calls:** a reply that calls at least one tool that changes the
  notebook (`add_url`, `add_from_library`, `create_output`) becomes a plan.
  Read tools alone (`explain_output`, `list_sources`, `list_outputs`) get
  the normal answer. A plan has at most six steps:
  `Answer.plan` = `{"plan_id", "status", "steps": [{"n", "tool", "args",
  "label", "valid", "invalid_reason"?, "estimate": {"min", "max"},
  "state", "error"?, "result"?, "processing"?}], "estimate": {"min",
  "max"}, "separate": [{"n", "label", "min", "max"}]}`, with estimates in
  euro cents. `estimate` is the plan's own action. Ingest's processing of
  a page an `add_url` step adds is booked under ingest's action, at the
  price `/prices` shows for adding a web page. So it is not in that total:
  it is the step's `processing` and a line of `separate`. The plan is also on the proposing message
  (`Message.plan`), kept current.
- **Invalid steps:** tool arguments come only from the user's message and
  their own library. A URL must be written in the message, a library
  source is found by name in the user's library (through ingest), and
  options go through the kind's validation. A step that breaks a rule
  stays in the plan with `valid: false` and its reason and is never run.

**Questions.** A plan asks when an open choice would change the cost or
the result, and never asks about something the message already answers.
It is then in status `asking`, with `plan.question` = `{"question_id",
"text", "choices": [{"id", "label", "estimate"}], "default", "free_text",
"answer"?}`: two to four choices, each with the plan's total if taken,
and one preselected. `POST .../answer` applies the choice to the steps
(it sets or removes an option and re-validates and re-estimates them),
records the answer as a user turn, and proposes the plan. Confirm answers
409 `answer the question first` until then. The mechanism is general,
and the verification level is its first question:

- **Message says:** a level the message names ("check it thoroughly",
  "ohne Prüfung") is taken as said, and "with a check" without a level is
  the user's own level, or `thorough` when theirs is basic. A `judge`
  option from an older planner reads as its level.
- **Message does not say, level basic:** no judge, and `plan.notes` says
  so in one line.
- **Message does not say, level above basic:** the plan asks "How
  thoroughly should the new documents be checked?" with
  `verification:basic`, `verification:standard` and
  `verification:thorough`, each with its estimate, the user's level
  preselected.

The second question is the web pages. A plan that creates an output from
a notebook holding web pages asks once, "<page> was read 15 h ago: use
that version or fetch again?", with "Use the versions already read"
(`pages:cached`) preselected and "Fetch them again (+ up to €x)", priced
by ingest's re-check. Fetching again sets `url_refresh` on the output
steps, so the outputs read the pages again first (a line of `separate`
per page). A message that says it ("neu laden", "fresh", "the cached
pages") sets `create_output`'s `web_pages` argument and is not asked.

Questions come one at a time: answering one opens the next, and the
plan stays `asking` until the last is answered. `plan.answered` lists
every answered question with its `answer`, in order. `plan.sources` =
`[{"name", "kind", "read_at"?}]` are the notebook's sources at planning
time, `read_at` the time a web page was last read or found unchanged.

Nothing runs before `POST .../plans/{plan_id}/confirm`.

- **Ingest steps** run inside the confirm request with its own bearer,
  because rag stores no tokens: adding a URL goes through ingest's SSRF
  guard, and linking library sources is ingest's bulk link.
- **Outputs** are created as any other, booked under the plan's
  `action_id` (`outputs.booking_id`); their jobs wait for the notebook's
  processing sources.
- **Explanations** run when their output is ready, as a scoped, cited
  answer in the conversation.
- **The worker** moves waiting steps on. An output still waiting for a
  source 30 minutes after confirmation fails with "a source did not
  become ready within 30 minutes", uncharged.
- **Failures and the end:** a failed step does not stop the others, and
  the plan ends with a summary message. It names what was made
  (`Created the quiz "<title>"`) and carries the plan (`Message.plan`),
  whose steps hold each `result` with the output's id, to link it.
- **Billing and limits:** every call of a plan books under its
  `action_id`. Ingest's processing of an added source books under
  ingest's own action. Credit is checked once, at confirm: the balance
  must cover the plan's maximum and its `separate` lines plus what started
  work holds (see Configuration), and a confirmed plan then runs all its
  steps, even if the balance goes negative on the way.
  The API's rate limit applies to confirm as to every route.

**Web page age.** An answer citing a web page says how old the version
it read is: `Answer.web_pages` (and `Message.web_pages`) =
`[{"library_id", "name", "fetched_at"}]`, each cited page once, so the
chat can offer to fetch it again (`url_refresh` on the next ask).

**Suggestions.**

- **With every answer.** Each chat answer returns `suggestions`, up to
  three short follow-up questions. They come from the same model call:
  the answer prompt asks for a `Suggestions:` tail, which is cut off the
  text before its citations are mapped, cleaned (no markers, one line, at
  most 150 characters, distinct) and stored with the message.
- **For a notebook.** `GET /notebooks/{id}/suggestions` gives a
  notebook's starting questions from one call over its source summaries.
  The call is billed as a `chat_answer` action of its own, and the result
  is cached in `notebook_suggestions` until the set of ready uploads
  changes (`"cached": true` then, without a call).
  - A notebook without a ready upload gets none, without a call.
  - An answer that does not parse is a billed 502.
  - The estimate for it is `{"action": "chat_answer", "options":
    {"suggestions": true}}`.

**Feedback.** The owner rates an answer with `POST
/messages/{id}/feedback` (`up` or `down`, an optional comment of at most
1000 characters). The rating is stored on the message as `feedback:
{"rating", "comment", "at"}`. `GET /admin/feedback` counts the ratings
per UTC day and lists the newest down-rated answers with the question
before them. The answers and questions are the users' own words, so a
viewer gets the counts only (`latest_down` empty, `"detail": "admins
only"`).

**Starter notebook.** A new user gets a copy of the maintainer's starter
notebook. Ingest copies its uploads (files, links, chunks) and, in the
same transaction, inserts one `output_copies` row:

- `target_notebook`: the copy;
- `source_notebook`: the starter;
- `owner`: the new user;
- `source_map`: old link and library ids to new;
- `chunk_map`: old chunk ids to new.

The worker claims these rows before any output job and copies the
starter's ready outputs outside the trash:

- **Rows:** owned by the new user, in the copy, with the same kind, title,
  content and options.
- **Generated sources:** each output's generated library row, link and
  chunks, embeddings included.
- **Audio:** the file is copied under a new key.
- **Ids:** the source selection, a chart's cited chunks, and the
  provenance's passages and candidates are rewritten through the maps.
  An id that cannot be mapped is dropped, never left pointing at the
  maintainer's rows.
- **Not copied or kept:** share tokens are not copied; judge annotations
  and the support check are kept.

It makes no model call and books nothing. `outputs.copied_from` makes a
copy idempotent, so a retry adds nothing twice. A copy that fails three
times keeps its row with the error.

**Shared notebooks.** Ingest shares a notebook under a token
(`notebooks.share_token`, set and revoked there). `GET
/api/rag/shared/notebooks/{token}`, without sign-in, returns three things:
the notebook's `title`; its ready uploads as `sources` (`name` and `kind`
only, no files, previews or ids); and its ready outputs outside the trash,
oldest first, as `outputs`. Each output is exactly what
`/shared/{token}` shows for a single output: no ids, no source selection,
and the provenance without chunk and source ids. Generated sources are
not listed among the sources, since they appear as outputs. An audio
`url` is presigned on every call. An unknown or revoked token answers
404 `notebook not found`.

`decision`: a question answered from the sources, by two independent
calls over the same numbered passages, retrieved with the question as
the focus query. Options: `question` (required, at most 500
characters), `decision_type` `yes_no` (default), `choice` with `choices`
(2–8 distinct labels) or `scale` with `levels` (3–7 ordered labels,
lowest first). The platform's decision model (`DECISION_MODEL`, core's
`OpenAICompatibleDecision`, one `decision` usage row) gets the question
and the passages and gives `model_answer`: `{"probability_yes",
"answer"}`, `{"choice", "distribution", "confidence"}` or `{"level",
"score" (probability-weighted level index, 0 = lowest), "legend",
"distribution", "confidence"}`, every value in 0..1 except `score`. The
LLM gets the same passages and the question but never that answer and
writes `verdict_text` (plain, one or two sentences), `evidence_for` and
`evidence_against` (`[{"text", "refs", "support"}]`, checked like every
unit), `gaps` (what the sources do not say) and, for a choice or a
scale, `llm_choice`, the option its evidence argues about. `agreement`
compares the two: `consistent`, `conflicting` (shown, never hidden) or
`unclear`, with `agreement_note`; for yes/no, a probability of at least
0.6 with more supported evidence for than against is consistent, at most
0.4 with more against too, the mirror cases conflict; for a choice or
scale, the same pick with more supported for is consistent, a different
pick with more supported for, or the same with more against, conflicts.
Without supported evidence on either side `agreement` is `undecided`,
`verdict_text` is "The sources do not decide this." and `model_answer`
is `null`: a number without evidence is the decision model's prior, not
a decision from the sources. The LLM's own sentence goes into
`provenance.llm_verdict_text` and the model's number into
`provenance.model_answer_without_evidence`. `supported_evidence` counts
the supported items on both sides, and `weight` says how firmly the
number is shown: `tendency` when one supported item or an `unclear`
balance stands behind it, `full` otherwise (a conflict included: both
sides are shown as they are), `null` when undecided. Nothing is hidden.
`provenance.calls` lists both calls (`role` `decision` with the state's
size, `role` `evidence`), `provenance.usage.decision` the decision
model's input tokens.

`chart`: a chart is made in two steps.

1. `POST /api/rag/notebooks/{id}/charts/propose` takes `{"instructions"?
   (at most 500 characters), "max"? (1–12, default 6), "source_ids"?,
   "url_refresh"?}`, the selection as for an output (absent or empty: all
   uploads). Selected sources not read yet are read first, as the caller,
   and waited for like a chat answer (`ANSWER_READ_WAIT_SECONDS`); still
   unread after that, the answer is no candidates with `reason` "still
   being read: <names>; find charts again in a moment". A failed selected
   source is 422 as on Create. It makes one LLM call over passages
   retrieved for numeric material from the selected sources only, billed
   as usual, and returns candidates without storing anything. Each candidate is
   `{"id", "title", "chart_type", "x_label", "y_label", "series":
   [{"name", "points": [{"x", "y", "refs", "derived_from"?,
   "support"}]}], "note", "passages": [{"n", "chunk_id", "source_name",
   "page"}], "proposal": {"model", "prompt_version", "tokens_in",
   "tokens_out", "proposed_at"}}`.
   - `chart_type` is one of `bar`, `line`, `pie` (one series), `stacked_bar`
     and `scatter` (numeric x).
   - When no retrieved passage has a digit, no model call is made. An empty
     list carries `reason` "the sources contain no number series".
2. The user picks candidates and creates the output with `{"kind":
   "chart", "options": {"charts": [picked candidates as returned],
   "instructions"?}, "source_ids"?}`. 1–12 candidates are accepted. Every
   passage they cite must be a chunk of an uploaded source of this notebook
   and, with a selection, of a selected source; otherwise the request is
   409 `{"error", "code": "chart_out_of_scope"}` (a proposal made for
   another selection: find charts again).
   - The worker makes no model call. It loads the cited chunks again,
     numbers them once for all picked charts, and checks every value.
   - The content is `{"charts": [{"title", "chart_type", "x_label",
     "y_label", "series": [{"name", "points": [{"x", "y", "refs",
     "support", "derived_from"?}]}], "note"}]}`.

The check (`number-match-v1`, no model call) is strict:
- A value is `supported` only when the number itself is written in a
  passage it cites, read in every way it can be written. `1.906` is also
  1906, `1,9 Mio.` also 1 900 000, and `12,5 %` also 0.125.
- A computed value (a share, a sum, a difference) names its passages in
  `derived_from` and is `derived`, never `supported`.
- Everything else is `unsupported`: a value off by one, no refs, or a
  passage gone since the proposal.

`provenance.calls` lists the proposal call (as the candidate reported it)
and the check. The shared views leave `options.charts` out, because it
holds chunk ids.

`audio`: the model writes a spoken-word script (three to five minutes)
in the chosen style, with a prompt and a JSON schema per style:
`overview` and `story` are `{"title", "paragraphs": [{"text", "refs"}]}`
read by one narrator (the story frames the material as a narrative but
invents nothing), `conversation` is `{"title", "turns": [{"speaker":
"interviewer" | "expert", "text", "refs"}]}`, where the expert
answers only from the material and both must speak (at most 6000
characters in all). The worker reads the turns with `TTS_MODEL`, the
narrator and the interviewer with `voice`, the expert with
`audio_voice_2`, each turn (or paragraph) on its own, in segments of
at most 1500 characters that end at a sentence, one `tts`
usage row per segment priced per second of generated audio as the
platform reports it, and stores the joined MP3 at
`<notebook_id>/<output_id>/audio.mp3` in object storage. The segments
arrive as VBR, each with a Xing header (frame and byte counts, a seek
table, a LAME tag). The joined file keeps one header for the whole
stream, rewritten with the totals, and drops the others; otherwise a
player takes the first segment's length for the file's and cannot seek
past it. Audio stored from 0.20.2 until this fix has every header:
`lasteverlm-rag-repair-audio` (needs `DATABASE_URL` and the `S3_*`
settings) lists those it would rewrite, and with `--apply` rewrites the
file in place and moves the transcript times back by the frames it
drops. It is idempotent; `--output <id>` limits it to some outputs. The row keeps
`{"key", "transcript": [{"speaker", "text", "start"?, "end"?}]}`. The
`speaker` is `narrator`, `interviewer` or `expert`; audio outputs from
before have no transcript.

- **Times:** `start` and `end` are the entry's seconds within the final
  MP3, measured by counting each segment's MP3 frames (`mp3.py`). The
  playback speed is therefore in them. The entries are contiguous, and
  the last ends at the file's length.
- **No times:** outputs from before have none. If a segment cannot be
  measured, the audio is kept without times and a warning is logged.
- **Reads:** every read (the output, the list, the shared view)
  returns `{"url", "transcript"}`, `url` a presigned GET URL valid for
  one hour.

The script, with `Interviewer:` / `Expert:` labels for a conversation,
is the indexed text, so the chat can cite what the audio says. Without
`TTS_MODEL` an audio output fails at once with a clear error, before
any model call.

## Configuration

Read from the environment; startup fails when a required value is
missing or a configured model has no price.

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | yes | PostgreSQL with the `vector` extension, shared with the other services |
| `INFERENCE_API_KEY`, `INFERENCE_BASE_URL` | key yes, URL defaults to Vultr Serverless Inference | OpenAI-compatible inference API |
| `LLM_MODEL`, `LLM_MAX_TOKENS` | model yes, budget default 1024 | chat model for answers and documents; called with thinking disabled, so the budget goes to content |
| `LLM_TIMEOUT_SECONDS` | no; default 60 | seconds per inference request (core); the worker uses at least 180, since a document is one long completion |
| `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION` | yes / default 1536 | query and chunk embedding, requested at that width (`dimensions`); identical to the ingest service |
| `MODEL_PRICES` | yes | JSON `{"<model>": {"in": cents, "out": cents}}` per million tokens; every configured model needs an entry |
| `AUTH_JWT_SECRET` or `DEMO_TOKEN` | one of them | bearer token scheme; both set means JWT first, demo token second |
| `JUDGE_MODELS` | no; defaults in core | JSON level → model for the judge (`low`, `medium`, `high`), chosen from `docs/judge-eval.md`; every model needs a `MODEL_PRICES` entry, or startup refuses |
| `INGEST_URL` | no; default `http://ingest` | ingest's API inside the cluster: reading sources when used, the agent chat's steps |
| `ANSWER_READ_WAIT_SECONDS` | no; default 60 | how long an answer waits for sources it started reading before it answers from what is ready |
| `DECISION_MODEL` | no; default `clef` (core) | the platform's decision model for the decision kind, used by the worker; it needs a `MODEL_PRICES` entry, `in` per million input tokens, or startup refuses |
| `TTS_MODEL`, `TTS_VOICE` | no; voice default `ryan` | enables the audio kind; the voice is the default for audio outputs and must be one of the platform's (`vivian`, `serena`, `ryan`, ...; startup refuses any other), not an OpenAI name; the model needs a `MODEL_PRICES` entry, `in` per million seconds of generated audio |
| `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION` | for audio | object storage for audio files, through core's storage client |
| `RETRIEVAL_K` | no | chunks per question, default 8 |
| `RETRIEVAL_GENERATED_SLOTS` | no; default `2` | how many of an unscoped question's k passages may come from generated documents (above the floor, listed after the uploads); `0` leaves them out |
| `SIMILARITY_FLOOR` | no | minimum cosine similarity, default 0.3 |
| `RATE_LIMIT_PER_MINUTE`, `BLOCK_MINUTES`, `BAN_AFTER_STRIKES`, ... | no | core's rate-limit middleware, defaults 120 / 15 / 3; see `core/README.md` |
| `LOG_LEVEL` | no | default `INFO` |
| `APP_VERSION`, `APP_COMMIT` | no | the build reported on `/healthz`; `unknown` when unset |

Auth, inference, prices and rate limiting are loaded by `lasteverlm_core`;
only the rest is rag's own. When an action starts (a chat answer, an
output's creation, a plan's confirm, a judgement on request, a voice
sample) the service runs core's credit check (`has_credit`: a positive
balance of ledger credits minus the charges of usage, for admins as for
everyone else) and answers 402 otherwise. An output's creation and a
plan's confirm also need the balance to cover their estimated maximum
(the output's, or the plan's total and its `separate` lines; with the
reading of unread sources and pages fetched again) plus what the user's
started work still holds. That is the sum of `outputs.reserved_cents`
(an output's maximum, set at creation) over the user's outputs in
`waiting` or `processing`, a running plan's waiting explanations, and
ingest's funded reads not finished (`library_sources.funded_cents` where
`funded_request_at` is set and `status = 'processing'`). Otherwise 402
`{"error": "credit does not cover this", "code": "credit_insufficient",
"needed_cents", "held_cents", "available_cents"}`. That is the only
check: an action that started runs to the end, the worker's attempts,
judge rounds, revisions and audio segments included, even if the balance
goes negative on the way. Every
model call is booked as one row of the `usage` table through core's
`record_usage`, under its user action. Core fixes the row's cost in US
cents (from `MODEL_PRICES`) and in euro cents (at the pricing rules'
`usd_per_eur`), and its charge in euro cents (the action's margin), and
it books the action's fixed fee once per `action_id`. rag computes no
cents of its own. Without an exchange rate nothing runs: every request
that would call a model (and the estimate) answers 503 `pricing has no
exchange rate, ask an admin` before any provider call, and the worker
claims no job, so no attempt is spent, and logs an error each pass. Its actions are:

| Action | One `action_id` per |
|---|---|
| `chat_answer` | asked question (embedding and answer) |
| `output:<kind>` | output, which is its id: every attempt, all TTS segments, both calls of a decision, and the judge's rounds and revisions |
| `chart_propose` | chart proposal |
| `judge` | judgement on request of an output or a chat answer |
| `voice_sample` | uncached voice preview |

**Estimate.** `POST /api/rag/estimate` takes either `{"kind",
"options"?}` for an output or `{"action", "options"?}` for
`chat_answer`, `chart_propose`, `judge` (`options.level` and
`options.kind`) or `voice_sample`. It returns `{"action",
"charge_cents_min", "charge_cents_max", "cost_eur_cents_min",
"cost_eur_cents_max", "cost_usd_cents_min", "cost_usd_cents_max"}`,
rounded outwards to a hundredth of a cent. The charge is in euro cents,
like the user's credit.

- **Calls.** The calls the action makes get assumed token counts in a
  low and a high case (`lasteverlm_rag/estimate.py`). The prompt
  material is 3000–9000 tokens. The written text runs from a quarter of
  the kind's token budget up to all of it. Audio is 3–5 minutes. The
  number of claim units is assumed per kind.
- **Judge.** With a judge level, the low case judges every unit once,
  and all pass. The high case judges every unit in all three rounds, with
  two revisions.
- **Pricing.** Each call is priced with core's `cost_cents` (US cents),
  converted at the current rules' rate and charged with the action's
  margin. The action's fee is counted once.
- **Not a quote.** It is an estimate; the booking uses the real counts.
  Options that do not fit, or an action rag does not run, give a 422.

## Run locally

```bash
make venv           # uv venv + editable install of ../core and this package with dev extras
make check          # ruff, mypy --strict, pytest; creates .venv on first run
make run            # API: uvicorn on :8000 with reload; needs the variables above
make worker         # worker: claims and runs output jobs; same variables
make build          # docker image lasteverlm-rag:<git sha>, built with the repository root as context
make judge-eval     # the judge evaluation against the platform; needs INFERENCE_API_KEY, see docs/judge-eval.md
```

The tests need no database and no inference provider: the store, the
retriever, the embedder, the LLM and the rate-limit store are faked
through `create_app`.

## Database

`db/migrations/0001_rag.sql` creates `messages` and `outputs`;
`0002_rag_conversations.sql` adds `conversations` and
`messages.conversation_id` and moves each notebook's existing messages
into one conversation `Chat 1`; `0003_rag_output_options.sql` adds
`outputs.options`; `0004_rag_outputs_library.sql` gives outputs an
`owner`, `origin_title` and `deleted_at`, makes `notebook_id` nullable
(set to null when the notebook is deleted) and points `source_id` at the
generated library row instead of its link (expand only: `owner` stays
nullable for pods of the previous release, and reads fall back to the
notebook's owner); `0005_rag_output_provenance.sql` adds
`outputs.provenance`, the generation log; `0006_rag_message_support.sql`
adds `messages.support` (`{"units", "check"}` of an answer);
`0007_rag_decision_kind.sql` allows the kind `decision`;
`0008_rag_chart_kind.sql` allows the kind `chart`;
`0009_rag_output_copies.sql` adds the `output_copies` queue and
`outputs.copied_from` for the starter notebook;
`0010_rag_suggestions_feedback.sql` adds `messages.suggestions`,
`messages.feedback` and the `notebook_suggestions` cache;
`0011_rag_flashcards_kind.sql` allows the kind `flashcards`;
`0012_rag_plans.sql` adds the agent chat's `plans`, `messages.plan` and
`outputs.booking_id`;
`0013_rag_output_phase.sql` adds `outputs.phase`, what a running output
is doing; `0014_rag_plan_questions.sql` lets a plan be `asking` and keeps
its question and notes. The
migrations runner applies them after
core, account and ingest. The
service reads ingest's `notebooks`, `library_sources`, `sources` and
`chunks`. A library source is a file, text, URL or image processed once
for its owner; `sources` links it into a notebook, and the link's id is
the source id the API and citations use. Chunks belong to the library
source, so search goes notebook → links → library sources (status, kind,
name, summary) → chunks. For a generated output rag writes a hidden
library row of kind `generated`, owned by the user, plus its link into
the notebook under one id, in one transaction, and the chunks on that
row. Ingest lists such rows only in its picker and never trashes or
purges them; rag trashes, restores and purges them with their output.

## Deployment

One image per Git SHA, built by `docker.yml` with the repository root as
context so `core/` is installed next to `rag/`, run as a non-root user in
the `lasteverlm` namespace. Two Deployments of the same image: the API
(default command, port 8000, behind ingress-nginx at `/api/rag`) and the
worker (`lasteverlm-rag-worker`), which scale independently; the API
stays stateless. Charts and secrets live in `infra/`.

## Layout

```text
lasteverlm_rag/
├── main.py         FastAPI app, routes, error shape
├── service.py      ask flow and output lifecycle (API side and worker side)
├── worker.py       worker entrypoint: claim jobs, run them, release or finish
├── citations.py    pure marker-to-citation mapping
├── coverage.py     balanced generator input and the uncovered-source check
├── judge.py        the judge's single call: prompt, deterministic parse of the verdict
├── estimate.py     the charge range of an action before it runs
├── judging.py      the judge in generation (rounds, revision, removal) and on request
├── numbers.py      the strict check of a chart's values (every reading of a written number)
├── options.py      output options catalogue (languages, voices, speeds) and validation
├── suggestions.py  suggested questions: the answer's tail, a notebook's starting questions
├── starter.py      copying a starter notebook's outputs: id remapping
├── speech.py       splitting an audio script into synthesis segments
├── voice_samples.py cached voice previews
├── agent.py        the agent chat's tools and plan validation (arguments only from the user)
├── agent_service.py plan, confirm, execute; the worker's half of the agent chat
├── reading.py      sources read when used: start reading, refresh pages, wait, estimate lines
├── ingest_client.py ingest's API for the agent's steps, with the user's bearer
├── admin.py        admin statistics (totals, daily series)
├── outputs/        OutputGenerator interface, one module per kind
├── store.py        Retriever and Store interfaces + PostgreSQL/pgvector adapters
├── models.py       request bodies and internal data shapes (shared models come from core)
└── config.py       settings from the environment
db/migrations/      the service's own tables
evals/judge/        the judge evaluation: fixture, runner, prices, committed results
docs/judge-eval.md  its method, results, limits and how to rerun it
```
