# Vision evaluation

How well the platform's vision models turn images into text for the
index: what they read correctly, what they invent, whether they loop, and
what changes when a large image is read in tiles. The tiling of large
images and vision PDF pages (`loaders/tiles.py`) and the choice to keep
the current model are based on this.

## Method

- **Images** (`evals/vision/images.py`). The images are made by the
  script, so the evaluation is reproducible and holds no user data. Every
  image's exact text is its ground truth (`truth.json`).

  | Image | What it is |
  |---|---|
  | 01 | an app library screen: sidebar labels, a header, five rows |
  | 02 | a settings page of repeated labels: twelve rows of "E-mail: On", "Push: Off", "In-app: On" |
  | 03 | a German invoice table with amounts |
  | 04 | a bar chart with values |
  | 05 | a German text page with numbers |
  | 06 | a dark code editor |
  | 07 | a narrow receipt in small type |
  | 08 | a filled form with checkboxes |
  | 09 | a dark dashboard of statuses and latencies |
  | 10 | a 2880×1800 app screen: 16 sidebar labels and 72 small cards, each with a title and a detail line ("Updated 4 days ago · 9 sources") |
  | 11 | image 10 downscaled to 960×600 |
  | 12 | image 05 as a 620×450 JPEG at quality 18 |
  | page | a scanned A4 page (image only, no text layer) of 60 small lines, rendered as ingest renders vision pages: 150 dpi, 1241×1754 |

- **Reading** (`evals/vision/run.py`). Each image is read the way ingest
  reads it: the image prompt (the page prompt for the page), temperature
  0, at most 2000 output tokens, thinking off, one call per image. The
  `tiled` mode reads the hard cases a second time in tiles, with ingest's
  own `crops` and `join`.
- **Scoring** (`evals/vision/score.py`):
  - **Lines:** the share of the image's text lines found in the answer.
    It ignores case and whitespace, and treats a separator dot, bullet or
    dash between words as the same.
  - **Numbers:** the share of the image's numbers found as written.
  - **Invented:** numbers in the answer that appear nowhere in the
    image's text. This is a hallucination signal, read by hand, since a
    description may count things ("six bars").
  - **Wrong language:** the description is not in the language of the
    image's text (a stopword count).
  - **Loop:** ingest's own repetition check.
  - **Capped:** the answer stopped at the output cap.
- **Models:** the ten models on the platform that take images and answer
  in text (2026-10-15).
- **Runs:** one call per image and model; the raw answers are in
  `evals/vision/results/2026-10-15-*.jsonl`.

## Result, 2026-10-15

### Ordinary images (01–09): every model reads them

| Model | Lines | Numbers | Wrong language | Loop | Capped | Tokens out | Seconds |
|---|---|---|---|---|---|---|---|
| qwen3.8-27b (current) | 0.99 | 1.00 | 0/9 | 0 | 0 | 209 | 1.6 |
| qwen3.8-flash-next | 0.99 | 1.00 | 5/9 | 0 | 0 | 311 | 1.8 |
| glm-5.3-flash | 0.99 | 1.00 | 0/9 | 0 | 0 | 518 | 2.6 |
| glm-5.3 | 1.00 | 1.00 | 0/9 | 0 | 0 | 978 | 35.9 |
| glm-5.2 | 1.00 | 1.00 | 5/9 | 0 | 0 | 462 | 3.7 |
| minimax-m3 | 0.97 | 1.00 | 1/9 | 0 | 0 | 342 | 1.9 |
| muse-glimmer-30b | 0.99 | 1.00 | 0/9 | 0 | 1 | 866 | 2.4 |
| mimo-v2.6-flash-rl | 0.99 | 1.00 | 5/9 | 0 | 0 | 327 | 2.7 |
| deepseek-v4.1-flash | 0.99 | 1.00 | 4/9 | 0 | 0 | 282 | 1.6 |
| nemotron-3-nano-omni-30b-a3b-reasoning | 0.96 | 1.00 | 2/9 | 0 | 0 | 118 | 1.6 |

No model looped, and none invented a number that changes what the image
says. Most "invented" numbers were the code editor's line numbers, which
the ground truth leaves out. The models differ in the language of the
description, not in the transcription (below).

### A large screenshot: every model invents what it cannot read

The platform scales every image to about the same input before the model
sees it: 400–600 input tokens per call, whether the image is 620×450 or
2880×1800. On image 10, the small detail lines are unreadable at that
scale, and every model filled them in. Lines correct out of 160:

| Model | 10, read whole | 11, downscaled |
|---|---|---|
| qwen3.8-27b | 68 | 9 |
| minimax-m3 | 67 | 70 |
| mimo-v2.6-flash-rl | 66 | 66 |
| qwen3.8-flash-next | 50 | 69 |
| glm-5.3-flash | 49 (capped) | 47 (capped) |
| deepseek-v4.1-flash | 48 | 68 |
| glm-5.2 | 48 (capped) | 49 (capped) |
| muse-glimmer-30b | 31 (capped) | 35 (capped) |
| glm-5.3 | 0 (capped) | 0 (capped) |
| nemotron-3-nano-omni-30b-a3b-reasoning | 0 | 0 |

What the invention looks like:
- qwen3.8-27b wrote "Updated 18 days ago - 73 minutes", which is not on
  the screen.
- minimax-m3 wrote "Updated 1 days ago · 0 sources" under all 72 cards,
  "SERVICES" for "SPACES" and "Train" for "Trash".

Such text varies, so the repetition check does not catch it, and it reads
like a transcript. Indexed, it would be cited as the source.

### In tiles, the same models read it

The same screenshot cut into four tiles of 1464×924 (and the A4 page
into two of 1241×901), read tile by tile and joined. Lines correct:

| Image | Model | Whole | Tiled | Input tokens | Output tokens | Seconds |
|---|---|---|---|---|---|---|
| 10 (160 lines) | qwen3.8-27b | 68 | 159 | 489 → 1956 | 1464 → 2075 | 3.2 → 3.3 |
| | minimax-m3 | 67 | 156 | 726 → 2904 | 1572 → 2331 | 4.4 → 3.2 |
| | glm-5.3-flash | 72 (capped) | 160 | 629 → 2516 | 2000 → 4184 | 4.4 → 5.7 |
| page (60 lines) | qwen3.8-27b | 37 | 60 | 515 → 1030 | 1691 → 1745 | 3.9 → 2.4 |
| | minimax-m3 | 58 | 60 | 759 → 1572 | 1254 → 1294 | 3.9 → 2.7 |
| | glm-5.3-flash | 21 (capped) | 60 | 663 → 1326 | 2000 → 3067 | 5.7 → 4.9 |

No tile was capped. The input grows with the number of tiles, and the
output stays about the transcript's length. The seconds are those of the
slowest tile, since the tiles run in parallel. A vision page is at least
as affected as a screenshot: an A4 page at 150 dpi is 2.2 MP.

### The description's language follows the prompt's examples

The image prompt asks for the description in the language of the image's
text, with German and French as examples. Several models then described
English images in German: flash-next, glm-5.2 and mimo 5 of 9, deepseek
4 of 9. qwen3.8-27b did this 0 times in this run and once (the chart) in
an earlier run of the same calls, so even at temperature 0 the result
is not fully stable.

A variant with an example in both directions ("English text, English
description; German text, German description; …") moved the errors
instead of removing them:

| Model | Wrong language, current prompt | Wrong language, variant |
|---|---|---|
| qwen3.8-27b | 0/9 | 2/9 (described the German invoice and receipt in English) |
| qwen3.8-flash-next | 5/9 | 0/9 |
| glm-5.2 | 5/9 | 3/9 |
| glm-5.3-flash | 0/9 | 0/9 |
| muse-glimmer-30b | 0/9 | 0/9 |

The transcription is verbatim either way, and retrieval works on it. The
prompt stays as it is.

## Decisions

- Images and vision pages over 1.5 MP are read in tiles
  (context/image-sources.md). This removes the invented lines for every
  model tested, at about one input budget per tile.
- The model stays qwen3.8-27b. No model reads a large screenshot whole,
  so switching would not fix the cause. qwen3.8-27b reads ordinary images
  as well as the best, and has among the shortest and fastest answers and
  the steadiest description language.
- The repetition loop on the starter screenshot was not reproduced on
  these images; no model looped. It is likely the same scaling, pushed
  further, and the screenshot is to be compared whole and tiled once it
  is uploaded again.

## Reproducing

```
cd ingest
python -m evals.vision.images /var/tmp/vision-images
python -m evals.vision.run read /var/tmp/vision-images out.jsonl --models qwen3.8-27b glm-5.3-flash
python -m evals.vision.run tiled /var/tmp/vision-images out.jsonl \
    --images 10_retina_app_cards.png page.jpg --models qwen3.8-27b
python -m evals.vision.score /var/tmp/vision-images/truth.json out.jsonl
```

`INFERENCE_API_KEY` comes from the environment, as for the service. The
images need the DejaVu fonts (`fonts-dejavu-core`).
