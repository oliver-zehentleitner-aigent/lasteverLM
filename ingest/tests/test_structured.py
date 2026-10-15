"""Structured data behind a URL: each format becomes lines that carry
their own context (a key path, an element path, a column name), and
hostile documents fail with a clear reason instead of rendering without
bound."""

import json

import pytest

from lasteverlm_ingest.loaders import LoaderError
from lasteverlm_ingest.loaders.pdf import PdfLoader
from lasteverlm_ingest.loaders.structured import (
    MAX_COLUMNS,
    MAX_DEPTH,
    MAX_FIELD_CHARS,
    MAX_VALUES,
    format_of,
    render,
    sniff_json,
)
from lasteverlm_ingest.loaders.text import TextLoader
from lasteverlm_ingest.loaders.url import Fetched, UrlLoader
from lasteverlm_ingest.worker import process_source
from tests.fakes import InMemoryRepository, InMemoryStorage
from tests.test_web_versions import Site, _deps, _read_page


def _lines(fmt: str, body: bytes) -> list[str]:
    return [p.text for p in render(fmt, body)]


@pytest.mark.parametrize(
    ("media_type", "fmt"),
    [
        ("application/json", "json"),
        ("application/vnd.github+json", "json"),
        ("application/ld+json", "json"),
        ("application/x-ndjson", "ndjson"),
        ("application/xml", "xml"),
        ("text/xml", "xml"),
        ("application/rss+xml", "xml"),
        ("application/atom+xml", "xml"),
        ("text/csv", "csv"),
        ("text/tab-separated-values", "tsv"),
        ("application/yaml", "yaml"),
        ("text/yaml", "yaml"),
        ("application/x-yaml", "yaml"),
        ("text/plain", None),
        ("image/png", None),
    ],
)
def test_format_of(media_type, fmt):
    assert format_of(media_type) == fmt


def test_json_keeps_the_key_path_on_every_value():
    body = b'{"Python": 12345, "Makefile": 230}'
    assert _lines("json", body) == ["Python: 12345\nMakefile: 230"]
    nested = {"repo": {"name": "x", "tags": ["a", "b"]}, "items": [{"n": 1}, {"n": 2.5}]}
    assert _lines("json", json.dumps(nested).encode()) == [
        "repo.name: x",
        "repo.tags[0]: a\nrepo.tags[1]: b",
        "items[0].n: 1",
        "items[1].n: 2.5",
    ]
    assert _lines("json", b'{"ok": true, "none": null, "e": {}}') == ["ok: true\nnone: null\ne: {}"]
    assert _lines("json", b"42") == ["value: 42"]


def test_ndjson_numbers_its_lines():
    assert _lines("ndjson", b'{"a": 1}\n\n{"a": 2}\n') == ["[0].a: 1", "[1].a: 2"]
    with pytest.raises(LoaderError, match=r"not valid JSON \(line 2\)"):
        render("ndjson", b'{"a": 1}\n{"a": \n')


def test_yaml_uses_safe_load_only():
    assert _lines("yaml", b"a: 1\nb:\n  c: [x, y]\n") == ["a: 1", "b.c[0]: x\nb.c[1]: y"]
    # A tag that would construct a Python object is refused, not run.
    with pytest.raises(LoaderError, match="not valid YAML"):
        render("yaml", b"!!python/object/apply:os.system ['echo hi']\n")


def test_xml_keeps_the_element_path_rss_and_atom():
    rss = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>News</title>
    <item><title>First</title><link>https://x.test/1</link></item>
    <item><title>Second</title></item></channel></rss>"""
    assert _lines("xml", rss) == [
        "rss@version: 2.0",
        "rss/channel/title: News",
        "rss/channel/item[1]/title: First\nrss/channel/item[1]/link: https://x.test/1",
        "rss/channel/item[2]/title: Second",
    ]
    atom = b"""<feed xmlns="http://www.w3.org/2005/Atom"><title>Blog</title>
    <entry><title>Post</title><link href="https://x.test/p"/></entry></feed>"""
    assert _lines("xml", atom) == [
        "feed/title: Blog",
        "feed/entry/title: Post\nfeed/entry/link@href: https://x.test/p",
    ]


def test_csv_names_every_value_by_its_column():
    body = b"city,price,note\nGraz,12,\nWien,9,cheap\n"
    assert _lines("csv", body) == [
        "row 1: city: Graz; price: 12",
        "row 2: city: Wien; price: 9; note: cheap",
    ]
    # A semicolon file (common in German locales) and a TSV.
    assert _lines("csv", b"a;b\n1;2\n") == ["row 1: a: 1; b: 2"]
    assert _lines("tsv", b"a\tb\n1\t2\n") == ["row 1: a: 1; b: 2"]
    # A value without a header cell still names its column.
    assert _lines("csv", b"a\n1,2\n") == ["row 1: a: 1; column 2: 2"]
    assert _lines("csv", b"a,b\n") == ["columns: a; b"]


def test_a_billion_laughs_xml_is_refused():
    laughs = b"""<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">
    <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
    <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">]>
    <lolz>&lol3;</lolz>"""
    with pytest.raises(LoaderError, match="declares entities"):
        render("xml", laughs)


def test_an_external_entity_is_refused():
    xxe = b"""<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]>
    <x>&e;</x>"""
    with pytest.raises(LoaderError, match="declares entities"):
        render("xml", xxe)


@pytest.mark.parametrize("fmt", ["json", "yaml"])
def test_deep_nesting_fails_with_its_reason(fmt):
    deep = b"[" * (MAX_DEPTH + 5) + b"1" + b"]" * (MAX_DEPTH + 5)
    with pytest.raises(LoaderError, match=f"nests deeper than {MAX_DEPTH} levels"):
        render(fmt, deep)


def test_json_too_deep_for_the_parser_fails_the_same_way():
    with pytest.raises(LoaderError, match="nests deeper"):
        render("json", b"[" * 200_000 + b"]" * 200_000)


def test_deep_xml_fails_with_its_reason():
    deep = b"<a>" * (MAX_DEPTH + 5) + b"x" + b"</a>" * (MAX_DEPTH + 5)
    with pytest.raises(LoaderError, match=f"XML nests deeper than {MAX_DEPTH} levels"):
        render("xml", deep)


def test_a_yaml_alias_bomb_is_bounded_by_the_value_count():
    bomb = b"a: &a [1,2,3,4,5,6,7,8,9]\n" + b"".join(
        f"{n}: &{n} [{', '.join([f'*{p}'] * 9)}]\n".encode()
        for p, n in zip("abcd", "bcde", strict=True)
    )
    with pytest.raises(LoaderError, match=f"more than {MAX_VALUES} values"):
        render("yaml", bomb)


def test_a_self_referencing_yaml_is_refused():
    with pytest.raises(LoaderError, match="refers to itself"):
        render("yaml", b"&a [*a]\n")


@pytest.mark.parametrize(
    ("fmt", "body", "message"),
    [
        ("json", json.dumps(list(range(MAX_VALUES + 1))).encode(), "JSON has more than"),
        ("xml", b"<r>" + b"<i/>" * (MAX_VALUES + 1) + b"</r>", "XML has more than"),
        ("csv", b"a\n" + b"1\n" * (MAX_VALUES + 1), "CSV has more than"),
    ],
)
def test_too_many_values_fail_with_their_reason(fmt, body, message):
    with pytest.raises(LoaderError, match=message):
        render(fmt, body)


def test_a_huge_csv_row_fails_with_its_reason():
    with pytest.raises(LoaderError, match=f"longer than {MAX_FIELD_CHARS} characters"):
        render("csv", b"a\n" + b"x" * (MAX_FIELD_CHARS + 1) + b"\n")
    with pytest.raises(LoaderError, match=f"more than {MAX_COLUMNS} columns"):
        render("csv", b",".join([b"c"] * (MAX_COLUMNS + 1)) + b"\n")


def test_invalid_documents_say_so():
    with pytest.raises(LoaderError, match="not valid JSON"):
        render("json", b'{"a": ')
    with pytest.raises(LoaderError, match="not valid XML"):
        render("xml", b"<a><b></a>")
    with pytest.raises(LoaderError, match="contains no values"):
        render("csv", b"")


def test_sniff_json_only_when_it_parses_cleanly():
    assert sniff_json(' {"a": 1}\n') and sniff_json("[1, 2]")
    assert not sniff_json("[citation needed] is a phrase")
    assert not sniff_json("plain words") and not sniff_json("42")


def _url_loader(media_type: str, body: bytes) -> UrlLoader:
    def fetch(url: str) -> Fetched:
        return Fetched(url, media_type, None, body)

    return UrlLoader(fetch=fetch, text=TextLoader(), pdf=PdfLoader())


def test_the_url_loader_reads_json_and_sniffs_it_behind_text_plain():
    body = b'{"Python": 12345, "Makefile": 230}'
    for media_type in ("application/json", "text/plain"):
        passages = _url_loader(media_type, body).load(b"https://api.x.test/languages")
        assert [p.text for p in passages] == ["Python: 12345\nMakefile: 230"]
    # Text that only looks like JSON stays text.
    passages = _url_loader("text/plain", b"[1] is a footnote").load(b"https://x.test/")
    assert [p.text for p in passages] == ["[1] is a footnote"]


class JsonSite(Site):
    def fetch(self, url: str) -> Fetched:
        self.fetches += 1
        return Fetched(url, "application/json", None, self.text.encode())


def test_the_snapshot_shows_the_rendering_inert():
    repo, storage = InMemoryRepository(), InMemoryStorage()
    site = JsonSite('{"note": "<script>alert(1)</script>", "n": 3}')
    _, _, lib = _read_page(repo, storage, site)
    page = storage.objects[repo.library[lib].snapshot_path].decode()
    assert "note: &lt;script&gt;alert(1)&lt;/script&gt;" in page and "n: 3" in page
    assert "<script>" not in page and "default-src 'none'" in page


def test_a_hostile_document_fails_the_source_with_its_reason():
    repo, storage = InMemoryRepository(), InMemoryStorage()
    site = JsonSite("[" * (MAX_DEPTH + 5) + "]" * (MAX_DEPTH + 5))
    from tests.test_web_versions import PAGE, USER

    nb = repo.create_notebook(USER, "nb")
    link = repo.add_source(nb.id, PAGE, "url", "page-key", dedupe_key=f"url:{PAGE}")
    storage.put("page-key", PAGE.encode(), "text/uri-list")
    repo.queue_for_processing(USER, [link.library_id])
    process_source(link.library_id, _deps(repo, storage, site))
    source = repo.library[link.library_id]
    assert source.status == "failed" and "nests deeper" in source.error
