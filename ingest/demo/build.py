"""Builds the demo library's generated files from their sources.

    .venv/bin/python demo/build.py

Writes `field-notes.pdf` (from `field-notes.txt`, one page per form feed,
real text layer so page citations work) and `marrow-bay-map.png` (a
poster-style map of the places in the field notes and the glossary)
into `src/lasteverlm_ingest/demo/`, where they ship with the package.
The outputs are committed; run this only after changing the sources.
Deterministic: the same sources give the same bytes.
"""

from __future__ import annotations

import math
import textwrap
import zlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DEMO = Path(__file__).resolve().parents[1] / "src" / "lasteverlm_ingest" / "demo"

# -- the PDF -------------------------------------------------------------------

PAGE_W, PAGE_H, MARGIN = 595, 842, 64
SIZE, LEADING, WRAP = 10.5, 14.5, 92


def _pdf_string(text: str) -> bytes:
    raw = text.encode("cp1252")
    return b"(" + raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def _page_stream(lines: list[tuple[str, str]]) -> bytes:
    out = [b"BT", f"{MARGIN} {PAGE_H - MARGIN} Td".encode()]
    for font, line in lines:
        size = 14 if font == "F2" else SIZE
        out.append(f"/{font} {size} Tf {LEADING} TL".encode())
        out.append(_pdf_string(line) + b" '")
    out.append(b"ET")
    return b"\n".join(out)


def _layout(page_text: str, first: bool) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    paragraphs = page_text.strip("\n").split("\n")
    for i, paragraph in enumerate(paragraphs):
        font = "F2" if first and i == 0 else "F1"
        if not paragraph.strip():
            lines.append(("F1", ""))
            continue
        for line in textwrap.wrap(paragraph, WRAP) or [""]:
            lines.append((font, line))
    return lines


def build_pdf(source: Path, target: Path) -> None:
    pages = source.read_text(encoding="utf-8").split("\f")
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",  # pages, filled below
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ]
    kids = []
    for number, text in enumerate(pages):
        stream = zlib.compress(_page_stream(_layout(text, number == 0)), 9)
        objects.append(
            b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream)
            + stream
            + b"\nendstream"
        )
        content = len(objects)
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R "
            b"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>" % (PAGE_W, PAGE_H, content)
        )
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode()
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    target.write_bytes(bytes(out))


# -- the map -------------------------------------------------------------------

W, H = 1200, 860
SEA, LAND, HILL, RIVER, INK, PAPER = (
    "#8fb8c9",
    "#e9dcb8",
    "#cdbb8c",
    "#5b8fa8",
    "#2b2620",
    "#f4ecd6",
)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, size: int = 22) -> None:
    font = _font(size)
    x, y = xy
    box = draw.textbbox((x, y), text, font=font)
    pad = 4
    draw.rectangle(
        (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad), fill=PAPER, outline=INK
    )
    draw.text((x, y), text, fill=INK, font=font)


def _place(
    draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, dx: int = 12, dy: int = -10
) -> None:
    x, y = xy
    draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=INK)
    _label(draw, (x + dx, y + dy), text)


def build_map(target: Path) -> None:
    image = Image.new("RGB", (W, H), SEA)
    draw = ImageDraw.Draw(image)
    # The mainland: everything east of a ragged coast running north-south.
    coast = [
        (560, 0),
        (540, 90),
        (575, 170),
        (520, 260),
        (500, 360),
        (545, 430),
        (515, 520),
        (470, 600),
        (500, 700),
        (560, 780),
        (600, 860),
        (W, H),
        (W, 0),
    ]
    draw.polygon(coast, fill=LAND, outline=INK)
    # Juniper Steps: terraces north-east.
    for i in range(5):
        draw.arc(
            (760 + i * 18, 70 + i * 22, 1120 - i * 18, 330 - i * 22), 200, 340, fill=HILL, width=10
        )
    # The river Quill from the hills down to Marrow Bay.
    quill = [
        (1150, 120),
        (1040, 190),
        (960, 260),
        (900, 300),
        (830, 330),
        (760, 380),
        (690, 420),
        (620, 440),
        (548, 432),
    ]
    draw.line(quill, fill=RIVER, width=14, joint="curve")
    # Lantern Hill.
    draw.polygon([(600, 560), (650, 480), (700, 560)], fill=HILL, outline=INK)
    # Saltglass Reef: a dotted arc offshore, south-west.
    for a in range(0, 100, 6):
        r = math.radians(200 + a)
        cx, cy = 430 + 120 * math.cos(r), 690 + 60 * math.sin(r)
        draw.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill="#ffffff", outline=INK)
    # The Grey Isles, far west, with Hollin Lighthouse.
    for box in [(70, 300, 200, 370), (210, 250, 270, 290), (150, 400, 210, 440)]:
        draw.ellipse(box, fill="#cfcac0", outline=INK)
    draw.rectangle((128, 310, 140, 340), fill="#ffffff", outline=INK)
    draw.polygon([(124, 312), (144, 312), (134, 298)], fill="#c0392b")

    _label(draw, (40, 30), "MARROW BAY & THE RIVER QUILL", 36)
    _label(draw, (40, 82), "Zeltavia. Surveyed 1893 by I. Vennholt, Royal Northern Survey", 20)
    _place(draw, (560, 440), "MARROW BAY", dx=16, dy=12)
    _label(draw, (575, 398), "Eel Steps (smokehouses)", 18)
    _place(draw, (650, 500), "Lantern Hill", dx=60, dy=-6)
    _place(draw, (900, 300), "Quill Ford", dx=14, dy=10)
    _place(draw, (1040, 190), "Fennick's Mill", dx=-170, dy=-46)
    _label(draw, (860, 40), "THE JUNIPER STEPS", 24)
    _label(draw, (740, 360), "River Quill", 20)
    _label(draw, (250, 690), "Saltglass Reef (wrecks: Margarethe, 1879)", 18)
    _place(draw, (134, 320), "Hollin Lighthouse", dx=-60, dy=36)
    _label(draw, (60, 470), "The Grey Isles (puffins)", 20)
    _label(draw, (230, 590), "THE NORTHERN SEA", 26)
    # Compass rose and scale bar.
    cx, cy = 1080, 720
    draw.polygon([(cx, cy - 70), (cx - 16, cy), (cx, cy - 12), (cx + 16, cy)], fill=INK)
    draw.polygon(
        [(cx, cy + 70), (cx - 16, cy), (cx, cy + 12), (cx + 16, cy)], outline=INK, fill=PAPER
    )
    draw.text((cx - 9, cy - 108), "N", fill=INK, font=_font(30))
    draw.line((820, 820, 1000, 820), fill=INK, width=4)
    for x in (820, 910, 1000):
        draw.line((x, 810, x, 830), fill=INK, width=3)
    draw.text((870, 780), "2 miles", fill=INK, font=_font(20))
    image.quantize(colors=48, dither=Image.Dither.NONE).save(target, optimize=True)


if __name__ == "__main__":
    build_pdf(DEMO / "field-notes.txt", DEMO / "field-notes.pdf")
    build_map(DEMO / "marrow-bay-map.png")
    for name in ("field-notes.pdf", "marrow-bay-map.png"):
        print(name, (DEMO / name).stat().st_size, "bytes")
