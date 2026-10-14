"""The snapshot of a fetched web page: what was read, kept inert.

Every read of a web page stores its HTML beside the source, so the
viewer's "Original" shows exactly the page the chunks came from, not the
live page, which may have changed or gone. The snapshot is rebuilt from
an allowlist, not cleaned by a blocklist: only text and structure tags
survive, with a handful of harmless attributes and links to http(s)
pages. Scripts, styles (and their `url()` imports), frames, forms,
embedded objects, images and every other external resource, event
handlers and `style` attributes are dropped, so the file loads nothing
and runs nothing. A content security policy in the document (nothing
but the snapshot's own inline stylesheet) is the second line, should a
browser open it outside the viewer's sandbox.
"""

from __future__ import annotations

from html import escape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

# Tags kept as they are (their text always is).
_KEEP = frozenset(
    {
        "a", "abbr", "address", "article", "b", "blockquote", "br", "caption", "cite",
        "code", "dd", "del", "details", "dfn", "div", "dl", "dt", "em", "figcaption",
        "figure", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "ins", "kbd", "li",
        "main", "mark", "ol", "p", "pre", "q", "s", "samp", "section", "small", "span",
        "strong", "sub", "summary", "sup", "table", "tbody", "td", "tfoot", "th",
        "thead", "time", "tr", "u", "ul", "var", "header", "footer", "nav", "aside",
    }
)  # fmt: skip
# Tags dropped with everything inside them.
_DROP = frozenset(
    {
        "script", "style", "noscript", "template", "iframe", "frame", "frameset",
        "object", "embed", "applet", "svg", "math", "canvas", "form", "button",
        "select", "textarea", "audio", "video", "picture", "head", "title",
    }
)  # fmt: skip
_VOID = frozenset({"br", "hr", "img", "input", "link", "meta", "source", "wbr", "base", "col"})
# Attributes kept, on any kept tag; `href` only on links, and only http(s).
_ATTRS = frozenset({"title", "lang", "dir", "colspan", "rowspan", "datetime", "cite"})


class _Snapshot(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self._base = base_url
        self._drop = 0
        self._open: list[str] = []
        self.out: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        if self._drop or tag in _DROP:
            if tag not in _VOID:
                self._drop += 1
            return
        if tag == "img":
            alt = next((v for k, v in attrs if k == "alt" and v), None)
            if alt:
                self.out.append(f"[{escape(alt)}]")
            return
        if tag not in _KEEP:
            return
        kept = []
        for name, value in attrs:
            if value is None:
                continue
            if name in _ATTRS:
                kept.append(f' {name}="{escape(value)}"')
            elif name == "href" and tag == "a":
                target = urljoin(self._base, value)
                if urlsplit(target).scheme in ("http", "https"):
                    kept.append(f' href="{escape(target)}" rel="noreferrer noopener"')
        self.out.append(f"<{tag}{''.join(kept)}>")
        if tag not in _VOID:
            self._open.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if self._drop:
            if tag in _DROP:
                self._drop -= 1
            return
        if tag in _KEEP and tag not in _VOID and tag in self._open:
            while self._open:
                last = self._open.pop()
                self.out.append(f"</{last}>")
                if last == tag:
                    break

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
            return
        if not self._drop:
            self.out.append(escape(data))

    def close(self) -> None:
        super().close()
        while self._open:
            self.out.append(f"</{self._open.pop()}>")


_PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<meta name="referrer" content="no-referrer">
<title>{title}</title>
<style>
body{{font:16px/1.5 system-ui,sans-serif;max-width:46rem;margin:2rem auto;padding:0 1rem}}
pre{{white-space:pre-wrap}}table{{border-collapse:collapse}}
td,th{{border:1px solid #ccc;padding:.2rem .4rem}}
</style>
</head><body>
<p><small>Snapshot of {url}, fetched {fetched}.</small></p>
{body}
</body></html>
"""


def html_snapshot(html: str, url: str, fetched: str) -> str:
    """An inert copy of a fetched HTML page."""
    parser = _Snapshot(url)
    parser.feed(html)
    parser.close()
    title = " ".join(parser.title.split()) or url
    return _PAGE.format(
        title=escape(title), url=escape(url), fetched=escape(fetched), body="".join(parser.out)
    )


def text_snapshot(text: str, url: str, fetched: str) -> str:
    """A fetched plain-text page, as the same kind of document."""
    return _PAGE.format(
        title=escape(url),
        url=escape(url),
        fetched=escape(fetched),
        body=f"<pre>{escape(text)}</pre>",
    )
