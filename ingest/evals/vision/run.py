"""The vision evaluation: every image read by every model the way ingest
reads it, and the hard cases read whole and in tiles.

    python -m evals.vision.images /var/tmp/vision-images
    python -m evals.vision.run read /var/tmp/vision-images out.jsonl --models qwen3.8-27b ...
    python -m evals.vision.run read ... --variant          # the language prompt variant
    python -m evals.vision.run tiled /var/tmp/vision-images out.jsonl \\
        --images 10_retina_app_cards.png page.jpg --models qwen3.8-27b ...
    python -m evals.vision.score /var/tmp/vision-images/truth.json out.jsonl

Reads `INFERENCE_API_KEY` (and `INFERENCE_BASE_URL`) from the environment
like the service; the key is never written anywhere. Every call is one
JSON line: model, image, mode (`full` or `tiled`), the answer, the finish
reason, tokens and seconds.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from lasteverlm_core.settings import VULTR_INFERENCE_BASE_URL
from openai import OpenAI

from lasteverlm_ingest.loaders.image import IMAGE_PROMPT, PAGE_PROMPT
from lasteverlm_ingest.loaders.tiles import crops, join, tile_boxes

# The language variant tried on 2026-10-15: an example in both directions.
VARIANT_PROMPT = IMAGE_PROMPT.replace(
    "German text, German description; French text, French description. Only an "
    "image without any text is described in English.",
    "English text, English description; German text, German description; French "
    "text, French description. An image without any text is described in English.",
)


def _client() -> OpenAI:
    return OpenAI(
        api_key=os.environ["INFERENCE_API_KEY"],
        base_url=os.environ.get("INFERENCE_BASE_URL") or VULTR_INFERENCE_BASE_URL,
        timeout=180,
    )


def _call(client: OpenAI, model: str, data: bytes, mime: str, prompt: str) -> dict[str, Any]:
    url = f"data:{mime};base64,{base64.b64encode(data).decode()}"
    start = time.monotonic()
    try:
        r = client.chat.completions.create(
            model=model,
            max_tokens=2000,
            temperature=0.0,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": [{"type": "image_url", "image_url": {"url": url}}]},
            ],
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
    except Exception as exc:  # recorded, not fatal
        return {"error": f"{type(exc).__name__}: {exc}"[:300]}
    choice = r.choices[0]
    return {
        "text": choice.message.content or "",
        "finish": choice.finish_reason,
        "tokens_in": r.usage.prompt_tokens if r.usage else None,
        "tokens_out": r.usage.completion_tokens if r.usage else None,
        "seconds": round(time.monotonic() - start, 1),
    }


def _mime(path: Path) -> str:
    return "image/png" if path.suffix == ".png" else "image/jpeg"


def _prompt(path: Path) -> str:
    return PAGE_PROMPT if path.name == "page.jpg" else IMAGE_PROMPT


def read(images: Path, out: Path, models: list[str], variant: bool) -> None:
    client = _client()
    files = sorted(p for p in images.iterdir() if p.suffix in (".png", ".jpg"))
    jobs = [(m, f) for m in models for f in files if f.name != "page.jpg"]

    def one(job: tuple[str, Path]) -> dict[str, Any]:
        model, path = job
        prompt = VARIANT_PROMPT if variant else _prompt(path)
        row = _call(client, model, path.read_bytes(), _mime(path), prompt)
        mode = "variant" if variant else "full"
        return {"model": model, "image": path.name, "mode": mode, **row}

    with ThreadPoolExecutor(max_workers=6) as pool, out.open("a") as fh:
        for row in pool.map(one, jobs):
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def tiled(images: Path, out: Path, models: list[str], names: list[str]) -> None:
    """Each named image read whole and in tiles (ingest's own tiling)."""
    from PIL import Image

    client = _client()
    with out.open("a") as fh:
        for name in names:
            path = images / name
            data = path.read_bytes()
            with Image.open(path) as image:
                columns = len({box[0] for box in tile_boxes(*image.size)})
            tiles, tile_mime = crops(data)
            for model in models:
                whole = _call(client, model, data, _mime(path), _prompt(path))
                fh.write(
                    json.dumps({"model": model, "image": name, "mode": "full", **whole}) + "\n"
                )
                with ThreadPoolExecutor(max_workers=4) as pool:
                    prompt = _prompt(path)
                    parts = [
                        f.result()
                        for f in [
                            pool.submit(_call, client, model, tile, tile_mime, prompt)
                            for tile in tiles
                        ]
                    ]
                failed = [p["error"] for p in parts if "error" in p]
                row = {
                    "model": model,
                    "image": name,
                    "mode": "tiled",
                    "tiles": len(tiles),
                    **(
                        {"error": failed[0]}
                        if failed
                        else {
                            "text": join([p["text"] for p in parts], columns),
                            "finish": (
                                "length" if any(p["finish"] == "length" for p in parts) else "stop"
                            ),
                            "tokens_in": sum(p["tokens_in"] or 0 for p in parts),
                            "tokens_out": sum(p["tokens_out"] or 0 for p in parts),
                            "seconds": max(p["seconds"] for p in parts),
                        }
                    ),
                }
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["read", "tiled"])
    parser.add_argument("images", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--images", dest="names", nargs="+", default=[])
    parser.add_argument("--variant", action="store_true")
    args = parser.parse_args()
    if args.command == "read":
        read(args.images, args.out, args.models, args.variant)
    else:
        tiled(args.images, args.out, args.models, args.names)


if __name__ == "__main__":
    main()
