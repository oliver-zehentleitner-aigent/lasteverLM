"""The vision evaluation's images, made here so the evaluation is
reproducible and holds no user data: every image's exact text is its
ground truth (`truth.json`).

01–09 are ordinary screens and documents
10–12 are the hard cases: a
2880×1800 app screen with 72 small cards, the same screen downscaled to
960×600, and a small low-quality JPEG of a text page. `dense_page.pdf` is
a scanned A4 page (image only, no text layer) with 60 small lines, and
`page.jpg` its render at ingest's vision DPI.

    python -m evals.vision.images <dir>
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from lasteverlm_ingest.loaders.pdf import render_page

F = "/usr/share/fonts/truetype/dejavu/"


def font(
    size: int, bold: bool = False, mono: bool = False, serif: bool = False
) -> ImageFont.FreeTypeFont:
    name = "DejaVuSansMono" if mono else "DejaVuSerif" if serif else "DejaVuSans"
    return ImageFont.truetype(F + name + ("-Bold" if bold else "") + ".ttf", size)


def build(OUT: Path) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    truth: dict[str, dict] = {}

    def save(name, img, lines, numbers, kind):
        img.save(OUT / name)
        truth[name] = {"lines": lines, "numbers": numbers, "kind": kind}

    # 1. A web app library screen, like the starter screenshot: a sidebar of
    # short labels, a header, a list of notebooks. The loop-prone kind.
    img = Image.new("RGB", (1440, 900), "#f6f7f9")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 240, 900], fill="#1f2430")
    side = [
        "lasteverLM",
        "Library",
        "Notebooks",
        "Outputs",
        "Settings",
        "SPACES",
        "Research",
        "Teaching",
        "Internal UI",
    ]
    for i, t in enumerate(side):
        d.text((24, 30 + i * 44), t, font=font(18, bold=(i == 0 or t == "SPACES")), fill="#e6e6e6")
    d.text((280, 30), "Library", font=font(30, bold=True), fill="#111")
    d.text((280, 80), "12 sources · 3 notebooks · 41.2 MB used", font=font(16), fill="#555")
    rows = [
        ("Quarterly report Q3.pdf", "PDF", "ready", "18 pages"),
        ("Interview Müller.mp3", "Audio", "ready", "42 min"),
        ("Pricing page", "Web", "waiting for credit", "–"),
        ("Whiteboard photo.jpg", "Image", "ready", "1 image"),
        ("Thesis draft v7.docx.pdf", "PDF", "failed", "–"),
    ]
    d.text((280, 130), "Name            ", font=font(14, bold=True), fill="#333")
    for j, (a, b, c, e) in enumerate(rows):
        y = 170 + j * 56
        d.rectangle([270, y - 10, 1400, y + 36], outline="#ddd", fill="white")
        d.text((285, y), a, font=font(17), fill="#111")
        d.text((780, y), b, font=font(15), fill="#444")
        d.text((900, y), c, font=font(15), fill="#0a7" if c == "ready" else "#c60")
        d.text((1150, y), e, font=font(15), fill="#444")
    lines = (
        side + ["Library", "12 sources · 3 notebooks · 41.2 MB used"] + [x for r in rows for x in r]
    )
    save("01_app_library.png", img, lines, ["12", "3", "41.2", "18", "42", "1", "7"], "ui")

    # 2. A settings page full of identical labels (the false-positive case).
    img = Image.new("RGB", (1200, 1000), "white")
    d = ImageDraw.Draw(img)
    d.text((40, 30), "Notification settings", font=font(28, bold=True), fill="#111")
    items = [
        "New source ready",
        "Source failed",
        "Output finished",
        "Credit low",
        "Weekly digest",
        "Shared notebook viewed",
        "Comment added",
        "Export ready",
        "Login from new device",
        "Plan confirmed",
        "Quiz generated",
        "Podcast generated",
    ]
    lines = ["Notification settings"]
    for i, t in enumerate(items):
        y = 100 + i * 70
        d.text((40, y), t, font=font(18), fill="#111")
        for k, ch in enumerate(["E-mail", "Push", "In-app"]):
            on = (i + k) % 3 != 0
            d.text((600 + k * 170, y), f"{ch}: {'On' if on else 'Off'}", font=font(16), fill="#333")
            lines.append(f"{ch}: {'On' if on else 'Off'}")
        lines.append(t)
    save("02_settings_identical_labels.png", img, lines, [], "ui")

    # 3. An invoice table with numbers.
    img = Image.new("RGB", (1100, 900), "white")
    d = ImageDraw.Draw(img)
    d.text((40, 30), "Rechnung Nr. 2026-0417", font=font(28, bold=True), fill="#111")
    d.text((40, 80), "Datum: 14.10.2026   Kunde: Bergwerk Systems GmbH", font=font(16), fill="#333")
    head = ["Pos", "Beschreibung", "Menge", "Einzelpreis", "Summe"]
    data = [
        ["1", "Beratung (Stunden)", "12", "95,00 €", "1.140,00 €"],
        ["2", "Lizenz Jahrespaket", "1", "2.400,00 €", "2.400,00 €"],
        ["3", "Schulung vor Ort", "2", "680,00 €", "1.360,00 €"],
        ["4", "Reisekosten", "1", "212,40 €", "212,40 €"],
    ]
    xs = [40, 110, 520, 650, 860]
    for x, h in zip(xs, head, strict=True):
        d.text((x, 150), h, font=font(16, bold=True), fill="#111")
    for r, row in enumerate(data):
        for x, v in zip(xs, row, strict=True):
            d.text((x, 195 + r * 45), v, font=font(16), fill="#222")
    d.text((650, 400), "Netto: 5.112,40 €", font=font(17), fill="#111")
    d.text((650, 435), "USt 20 %: 1.022,48 €", font=font(17), fill="#111")
    d.text((650, 470), "Gesamt: 6.134,88 €", font=font(19, bold=True), fill="#111")
    lines = (
        ["Rechnung Nr. 2026-0417", "Datum: 14.10.2026", "Bergwerk Systems GmbH"]
        + head
        + [v for row in data for v in row]
        + ["Netto: 5.112,40 €", "USt 20 %: 1.022,48 €", "Gesamt: 6.134,88 €"]
    )
    save(
        "03_invoice_de.png",
        img,
        lines,
        [
            "2026-0417",
            "14.10.2026",
            "12",
            "95,00",
            "1.140,00",
            "2.400,00",
            "680,00",
            "1.360,00",
            "212,40",
            "5.112,40",
            "1.022,48",
            "6.134,88",
            "20",
        ],
        "table",
    )

    # 4. A bar chart with values.
    img = Image.new("RGB", (1000, 700), "white")
    d = ImageDraw.Draw(img)
    d.text((40, 20), "Monthly active users 2026 (thousands)", font=font(22, bold=True), fill="#111")
    vals = [
        ("Jan", 14.2),
        ("Feb", 15.8),
        ("Mar", 19.4),
        ("Apr", 18.1),
        ("May", 23.7),
        ("Jun", 27.9),
    ]
    for i, (m, v) in enumerate(vals):
        x = 90 + i * 140
        h = int(v * 18)
        d.rectangle([x, 620 - h, x + 80, 620], fill="#3b6fd8")
        d.text((x + 15, 630), m, font=font(16), fill="#111")
        d.text((x + 10, 620 - h - 26), f"{v}", font=font(16, bold=True), fill="#111")
    save(
        "04_bar_chart.png",
        img,
        ["Monthly active users 2026 (thousands)"]
        + [m for m, _ in vals]
        + [str(v) for _, v in vals],
        [str(v) for _, v in vals] + ["2026"],
        "chart",
    )

    # 5. A German text page (document-like).
    para = (
        "Die Wasserversorgung der Gemeinde wurde im Jahr 1987 vollständig erneuert. "
        "Seitdem werden jährlich rund 412.000 Kubikmeter Trinkwasser aus drei Quellen "
        "gefördert. Die längste Leitung misst 7,4 Kilometer und verbindet den Hochbehälter "
        "am Kalvarienberg mit dem Ortszentrum. Bei Starkregen sinkt die Trübung nach etwa "
        "36 Stunden wieder unter den Grenzwert von 1,0 NTU."
    )
    img = Image.new("RGB", (1240, 900), "#fbfaf6")
    d = ImageDraw.Draw(img)
    d.text(
        (80, 60), "Kapitel 3: Wasserversorgung", font=font(30, bold=True, serif=True), fill="#111"
    )
    words, line, y, plines = para.split(), "", 140, []
    for w in words:
        if d.textlength(line + " " + w, font=font(20, serif=True)) > 1080:
            d.text((80, y), line.strip(), font=font(20, serif=True), fill="#222")
            plines.append(line.strip())
            y += 36
            line = ""
        line += " " + w
    d.text((80, y), line.strip(), font=font(20, serif=True), fill="#222")
    plines.append(line.strip())
    save(
        "05_text_page_de.png",
        img,
        ["Kapitel 3: Wasserversorgung"] + plines,
        ["3", "1987", "412.000", "7,4", "36", "1,0"],
        "text",
    )

    # 6. A code editor screenshot, dark theme.
    code = [
        "def degenerated(text: str) -> bool:",
        "    tokens = text.lower().split()",
        "    if len(tokens) < 500:",
        "        return False",
        "    distinct = len(set(tokens))",
        "    return distinct < 25",
        "",
        "# threshold calibrated on 2026-10-15",
        "LIMIT = 100",
    ]
    img = Image.new("RGB", (1100, 520), "#1e1e1e")
    d = ImageDraw.Draw(img)
    for i, c in enumerate(code):
        d.text((20, 30 + i * 34), f"{i + 1:>2}", font=font(18, mono=True), fill="#858585")
        d.text((80, 30 + i * 34), c, font=font(18, mono=True), fill="#d4d4d4")
    save(
        "06_code_dark.png", img, [c for c in code if c], ["500", "25", "2026-10-15", "100"], "code"
    )

    # 7. A narrow receipt with small text.
    img = Image.new("RGB", (420, 820), "white")
    d = ImageDraw.Draw(img)
    rl = [
        "CAFÉ ALPENBLICK",
        "Hauptplatz 4, 8010 Graz",
        "Tisch 7  Bon 0381",
        "2x Melange      9,80",
        "1x Apfelstrudel  4,90",
        "1x Mineral 0,5l  3,40",
        "SUMME EUR       18,10",
        "Bar             20,00",
        "Rückgeld         1,90",
        "15.10.2026 14:32",
        "Danke für Ihren Besuch!",
    ]
    for i, t in enumerate(rl):
        d.text((24, 30 + i * 62), t, font=font(15, mono=True, bold=(i in (0, 6))), fill="#222")
    save(
        "07_receipt.png",
        img,
        rl,
        [
            "4",
            "8010",
            "7",
            "0381",
            "9,80",
            "4,90",
            "0,5",
            "3,40",
            "18,10",
            "20,00",
            "1,90",
            "15.10.2026",
            "14:32",
        ],
        "receipt",
    )

    # 8. A form with checkboxes and filled fields.
    img = Image.new("RGB", (1000, 760), "white")
    d = ImageDraw.Draw(img)
    d.text((40, 30), "Registration form", font=font(26, bold=True), fill="#111")
    fields = [
        ("First name", "Anna"),
        ("Last name", "Steinberger"),
        ("Date of birth", "03.07.1991"),
        ("Membership no.", "M-48213"),
        ("Phone", "+43 664 1234567"),
    ]
    for i, (k, v) in enumerate(fields):
        y = 100 + i * 70
        d.text((40, y), k + ":", font=font(18), fill="#333")
        d.rectangle([300, y - 6, 900, y + 30], outline="#999")
        d.text((312, y), v, font=font(18), fill="#00a")
    opts = [("Newsletter", True), ("SMS reminders", False), ("Accept terms", True)]
    for i, (k, on) in enumerate(opts):
        y = 480 + i * 60
        d.rectangle([40, y, 66, y + 26], outline="#333", width=2)
        if on:
            d.line([44, y + 13, 52, y + 22, 63, y + 4], fill="#0a0", width=3)
        d.text((84, y), k, font=font(18), fill="#111")
    save(
        "08_form.png",
        img,
        ["Registration form"]
        + [f"{k}:" for k, _ in fields]
        + [v for _, v in fields]
        + [k for k, _ in opts],
        ["03.07.1991", "48213", "664", "1234567", "43"],
        "form",
    )

    # 9. A dark dashboard with small text and many identical "OK" statuses.
    img = Image.new("RGB", (1280, 760), "#11151c")
    d = ImageDraw.Draw(img)
    d.text((30, 20), "Cluster health", font=font(24, bold=True), fill="#e8e8e8")
    svc = [
        "core",
        "ingest",
        "rag",
        "web",
        "account",
        "worker-1",
        "worker-2",
        "worker-3",
        "postgres",
        "storage",
    ]
    lines = ["Cluster health"]
    for i, s in enumerate(svc):
        y = 80 + i * 62
        st = "OK" if s != "worker-3" else "DEGRADED"
        lat = 12 + i * 7
        d.text((30, y), s, font=font(16), fill="#cfd6e0")
        d.text((300, y), st, font=font(16, bold=True), fill="#3c3" if st == "OK" else "#e93")
        d.text((520, y), f"p95 {lat} ms", font=font(14), fill="#9aa4b2")
        lines += [s, st, f"p95 {lat} ms"]
    save("09_dashboard_dark.png", img, lines, [str(12 + i * 7) for i in range(10)] + ["95"], "ui")

    # 10–11. A retina-size app screen with many small cards, and downscaled.
    F_ = F + "DejaVuSans.ttf"
    FB = F + "DejaVuSans-Bold.ttf"
    img = Image.new("RGB", (2880, 1800), "#ffffff")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 420, 1800], fill="#f2f3f5")
    side = [
        "WEBLUI",
        "Library",
        "Settings",
        "Notebooks",
        "Sources",
        "Outputs",
        "SPACES",
        "Internet-UI",
        "Intranet-UI",
        "Design-UI",
        "Admin-UI",
        "Mobile-UI",
        "Archive",
        "Trash",
        "Help",
        "Feedback",
    ]
    for i, t in enumerate(side):
        d.text(
            (30, 30 + i * 46),
            t,
            font=ImageFont.truetype(FB if t in ("WEBLUI", "SPACES") else F_, 22),
            fill="#222",
        )
    labels = []
    for c in range(4):
        for r in range(18):
            t = f"{['Internet', 'Intranet', 'Design', 'Admin'][c]}-UI card {r + 1}"
            x, y = 480 + c * 600, 40 + r * 95
            d.rectangle([x, y, x + 560, y + 80], outline="#ccd", fill="#fafbff")
            d.text((x + 16, y + 12), t, font=ImageFont.truetype(F_, 20), fill="#111")
            d.text(
                (x + 16, y + 44),
                f"Updated {r % 9 + 1} days ago · {r * 3 + c} sources",
                font=ImageFont.truetype(F_, 15),
                fill="#667",
            )
            labels += [t]
    img.save(OUT / "10_retina_app_cards.png")
    truth["10_retina_app_cards.png"] = {"lines": side + labels, "numbers": [], "kind": "ui"}
    small = img.resize((960, 600))
    small.save(OUT / "11_app_cards_downscaled.png")
    truth["11_app_cards_downscaled.png"] = {"lines": side, "numbers": [], "kind": "ui"}
    cards = [
        x
        for c in range(4)
        for r in range(18)
        for x in (
            f"{['Internet', 'Intranet', 'Design', 'Admin'][c]}-UI card {r + 1}",
            f"Updated {r % 9 + 1} days ago · {r * 3 + c} sources",
        )
    ]
    truth["10_retina_app_cards.png"]["lines"] = side + cards
    truth["11_app_cards_downscaled.png"]["lines"] = side + cards

    # 12. The German text page, small and heavily compressed.
    doc = Image.open(OUT / "05_text_page_de.png").convert("L").resize((620, 450))
    buf = io.BytesIO()
    doc.save(buf, "JPEG", quality=18)
    (OUT / "12_text_page_lowq.jpg").write_bytes(buf.getvalue())
    truth["12_text_page_lowq.jpg"] = truth["05_text_page_de.png"]

    # A dense scanned A4 page, and its render at ingest's vision DPI.
    dpi = 300
    page = Image.new("RGB", (int(8.27 * dpi), int(11.69 * dpi)), "white")
    d = ImageDraw.Draw(page)
    d.text((150, 120), "Inventory report, warehouse 3, October 2026", font=font(52), fill="black")
    page_lines = []
    for i in range(60):
        t = (
            f"Item {i + 1:03d}: {((i * 7919) % 9000 + 1000) / 7:,.2f} kg, "
            f"lot B-{(i * 389) % 9000 + 1000}, shelf {chr(65 + i % 8)}{i % 12 + 1}"
        )
        d.text((150, 260 + i * 52), t, font=font(34), fill="black")
        page_lines.append(t)
    buf = io.BytesIO()
    page.save(buf, "PDF", resolution=dpi)
    (OUT / "dense_page.pdf").write_bytes(buf.getvalue())
    (OUT / "page.jpg").write_bytes(render_page(buf.getvalue(), 0))
    truth["page.jpg"] = {"lines": page_lines, "numbers": [], "kind": "page"}

    (OUT / "truth.json").write_text(json.dumps(truth, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    build(Path(sys.argv[1]))
