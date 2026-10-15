"""Large images are read in tiles.

The platform scales every image to about the same number of input tokens
before the vision model sees it, whatever its size (measured in
docs/vision-eval.md). A large screenshot's small text then becomes
unreadable, and the model fills it in with plausible but invented
lines. An image over `MAX_PIXELS` is therefore cut into the fewest equal
crops of at most `MAX_PIXELS` each (a 2880×1800 screenshot into four of
1464×924, a 1920×1080 one into two), overlapping by `OVERLAP` pixels so
no text line is cut in every tile it touches. The crops are read separately and joined in reading
order: left to right, top to bottom.
"""

from __future__ import annotations

import io
import math
import re

from PIL import Image

MAX_PIXELS = 1_500_000
OVERLAP = 48
# At most this many tiles per side; an image needing more is refused.
MAX_SPLIT = 6
# A line that a tile shares with the tile above or to its left is the
# overlap read twice and is dropped from the later tile; shorter lines (a
# lone label such as "OK") are kept, since they may be real repetitions.
MIN_DUPLICATE_CHARS = 20

Box = tuple[int, int, int, int]


def tile_boxes(width: int, height: int) -> list[Box]:
    """The crop boxes of an image, in reading order: the fewest equal
    tiles of at most `MAX_PIXELS` each (squarer ones on a tie); one box
    covering the whole image when it is not larger than that."""
    if width * height <= MAX_PIXELS:
        return [(0, 0, width, height)]
    grids = [
        (columns * rows, abs(math.log(_size(width, columns) / _size(height, rows))), columns, rows)
        for columns in range(1, MAX_SPLIT + 1)
        for rows in range(1, MAX_SPLIT + 1)
        if _size(width, columns) * _size(height, rows) <= MAX_PIXELS
    ]
    if not grids:
        raise ValueError(f"image of {width}x{height} needs more than {MAX_SPLIT}x{MAX_SPLIT} tiles")
    _, _, columns, rows = min(grids)
    tile_w, tile_h = _size(width, columns), _size(height, rows)
    xs, ys = _starts(width, columns), _starts(height, rows)
    return [(x, y, x + tile_w, y + tile_h) for y in ys for x in xs]


def _size(length: int, count: int) -> int:
    """Equal tiles that together cover `length` with `OVERLAP` between them."""
    return math.ceil((length + (count - 1) * OVERLAP) / count)


def _starts(length: int, count: int) -> list[int]:
    size = _size(length, count)
    return [min(i * (size - OVERLAP), length - size) for i in range(count)]


def crops(data: bytes) -> tuple[list[bytes], str]:
    """The image's tiles as encoded images, and their media type (PNG for
    a PNG, which keeps small text sharp; JPEG otherwise). A single tile is
    the original bytes, untouched."""
    with Image.open(io.BytesIO(data)) as image:
        boxes = tile_boxes(*image.size)
        if len(boxes) == 1:
            return [data], ""
        png = image.format == "PNG"
        source = image.convert("RGBA" if png and image.mode in ("RGBA", "LA", "P") else "RGB")
        out = []
        for box in boxes:
            buffer = io.BytesIO()
            if png:
                source.crop(box).save(buffer, "PNG", optimize=True)
            else:
                source.crop(box).convert("RGB").save(buffer, "JPEG", quality=90)
            out.append(buffer.getvalue())
    return out, "image/png" if png else "image/jpeg"


def image_tiles(data: bytes) -> int | None:
    """How many tiles the image is read in (1 when it is not tiled); None
    when Pillow cannot read its size."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            return len(tile_boxes(*image.size))
    except (OSError, ValueError):
        return None


def join(texts: list[str], columns: int) -> str:
    """The tiles' texts in reading order, separated by a blank line. A
    line of at least `MIN_DUPLICATE_CHARS` that the tile above or to the
    left already has (the overlap, read twice) is dropped from the later
    tile, as often as the neighbour has it."""
    out: list[str] = []
    for index, text in enumerate(texts):
        neighbours: list[str] = []
        if index % columns:
            neighbours += texts[index - 1].splitlines()
        if index >= columns:
            neighbours += texts[index - columns].splitlines()
        lines = _without_overlap(neighbours, text.strip().splitlines())
        if lines:
            out.append("\n".join(lines))
    return "\n\n".join(out)


def _without_overlap(neighbours: list[str], lines: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    for line in neighbours:
        key = _norm(line)
        if len(key) >= MIN_DUPLICATE_CHARS:
            seen[key] = seen.get(key, 0) + 1
    kept = []
    for line in lines:
        key = _norm(line)
        if seen.get(key, 0) > 0:
            seen[key] -= 1
            continue
        kept.append(line)
    return kept


def _norm(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip().lower()
