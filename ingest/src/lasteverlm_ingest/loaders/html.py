from __future__ import annotations

import re
from html.parser import HTMLParser

from lasteverlm_ingest.loaders import LoaderError, Passage

# Never text a reader wants: code, styling, and the page chrome around
# the article.
_SKIP = frozenset(
    {
        "script",
        "style",
        "noscript",
        "template",
        "svg",
        "canvas",
        "iframe",
        "head",
        "nav",
        "header",
        "footer",
        "aside",
        "form",
        "button",
        "select",
    }
)
_VOID = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}
)
_BLOCK = frozenset(
    {
        "address",
        "article",
        "blockquote",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "main",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }
)
_MAIN = ("main", "article")
_SPACES = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.scripts = 0
        self.title: list[str] = []
        self.body: list[str] = []
        self.main: list[str] = []
        self._skip = 0
        self._main = 0
        self._in_title = False
        self._pre = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            self.scripts += 1
        if tag in _VOID:
            if tag == "br":
                self._text("\n")
            return
        if tag == "title":
            self._in_title = True
        if tag == "pre":
            self._pre += 1
        if tag in _SKIP:
            self._skip += 1
        elif tag in _MAIN:
            self._main += 1
        if tag in _BLOCK:
            self._text("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag == "pre":
            self._pre = max(0, self._pre - 1)
        if tag in _SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in _MAIN:
            self._main = max(0, self._main - 1)
        if tag in _BLOCK:
            self._text("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title.append(data)
        elif not self._skip:
            # Line breaks in the markup are spaces, except inside <pre>.
            self._text(data if self._pre else data.replace("\n", " "))

    def _text(self, data: str) -> None:
        if self._skip:
            return
        self.body.append(data)
        if self._main:
            self.main.append(data)


def _tidy(parts: list[str]) -> str:
    lines = (_SPACES.sub(" ", line).strip() for line in "".join(parts).split("\n"))
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


class HtmlLoader:
    """Readable text of a web page with the standard library's parser.

    Scripts, styles and page chrome (nav, header, footer, aside, forms)
    are dropped. When the page marks its content with `<main>` or
    `<article>`, only that is kept; otherwise the whole body. The page
    title leads the text so that the summary and the citations name it.
    """

    def load(self, data: bytes, charset: str | None = None) -> list[Passage]:
        parser = _Extractor()
        parser.feed(_decode(data, charset))
        parser.close()
        main = _tidy(parser.main)
        text = main if main else _tidy(parser.body)
        if not text:
            if parser.scripts:
                # An app shell: its content is built in the browser, and the
                # worker runs no JavaScript.
                raise LoaderError(
                    "the page has no readable text without JavaScript (it builds its content "
                    "in the browser); add a page that serves its text as HTML"
                )
            raise LoaderError("the page contains no readable text")
        title = " ".join("".join(parser.title).split())
        if title and not text.startswith(title):
            text = f"{title}\n\n{text}"
        return [Passage(text=text)]


_META_CHARSET = re.compile(rb"""<meta[^>]+charset=["']?([A-Za-z0-9_.:-]+)""", re.IGNORECASE)


def _decode(data: bytes, charset: str | None) -> str:
    candidates = [charset] if charset else []
    found = _META_CHARSET.search(data[:4096])
    if found:
        candidates.append(found.group(1).decode("ascii"))
    for candidate in [*candidates, "utf-8"]:
        try:
            return data.decode(candidate)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("latin-1")
