"""Structured data behind a URL: JSON, NDJSON, XML, CSV, TSV and YAML.

Each format becomes lines that carry their own context, so a chunk cites
well wherever the chunker cuts it: JSON, YAML and XML as one line per
value with its full path (`languages.Python: 12345`,
`rss/channel/item[2]/title: …`), CSV and TSV as one line per row with
every value named by its column (`row 3: city: Graz; price: 12`). Values
of one object (one XML element, one row) form one passage, so they stay
together and apart from the next record.

Parsing is bounded beyond the fetch's byte cap: nesting deeper than
`MAX_DEPTH` or more than `MAX_VALUES` values fail the source with that
reason instead of rendering an unbounded amount of text. XML is parsed by
defusedxml with entity declarations and external references refused (no
entity expansion, no DTD fetch); YAML only by `safe_load`.
"""

from __future__ import annotations

import csv
import io
import json
import math
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from xml.etree.ElementTree import Element

import yaml
from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError
from defusedxml.ElementTree import fromstring as parse_xml

from lasteverlm_ingest.loaders import LoaderError, Passage
from lasteverlm_ingest.loaders.text import decode_text

MAX_DEPTH = 32
MAX_VALUES = 10_000
MAX_COLUMNS = 500
# Per CSV field; the csv module's own default is 128 KiB.
MAX_FIELD_CHARS = 100_000

JSON_TYPES = frozenset({"application/json", "text/json"})
NDJSON_TYPES = frozenset(
    {"application/x-ndjson", "application/ndjson", "application/jsonl", "application/x-jsonlines"}
)
XML_TYPES = frozenset({"application/xml", "text/xml"})
CSV_TYPES = frozenset({"text/csv"})
TSV_TYPES = frozenset({"text/tab-separated-values"})
YAML_TYPES = frozenset({"application/yaml", "text/yaml", "application/x-yaml", "text/x-yaml"})

# For the message a still unsupported type fails with.
SUPPORTED = "HTML, plain text, Markdown, PDF, JSON, NDJSON, XML (RSS, Atom), CSV, TSV, YAML"


def format_of(media_type: str) -> str | None:
    """The structured format of a media type, or None. `+json` and `+xml`
    suffixes count (`application/vnd.github+json`, `application/rss+xml`);
    XHTML is HTML, decided before this."""
    if media_type in JSON_TYPES or media_type.endswith("+json"):
        return "json"
    if media_type in NDJSON_TYPES:
        return "ndjson"
    if media_type in XML_TYPES or media_type.endswith("+xml"):
        return "xml"
    if media_type in CSV_TYPES:
        return "csv"
    if media_type in TSV_TYPES:
        return "tsv"
    if media_type in YAML_TYPES:
        return "yaml"
    return None


def sniff_json(text: str) -> bool:
    """A text/plain body that is JSON: only an object or array that parses
    cleanly, so prose that starts with a bracket stays prose."""
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return False
    try:
        json.loads(stripped)
    except (ValueError, RecursionError):
        return False
    return True


def render(fmt: str, body: bytes) -> list[Passage]:
    """The passages of a structured body; LoaderError with the reason when
    it does not parse or exceeds the limits."""
    text = decode_text(body)
    if fmt == "json":
        passages = _Tree("JSON").render(_load_json(text))
    elif fmt == "ndjson":
        tree = _Tree("NDJSON")
        lines = [line for line in text.split("\n") if line.strip()]
        passages = [
            p
            for i, line in enumerate(lines)
            for p in tree.walk(_load_json(line, i + 1), f"[{i}]", 0)
        ]
    elif fmt == "yaml":
        passages = _Tree("YAML").render(_load_yaml(text))
    elif fmt == "xml":
        passages = _Xml().render(body)
    elif fmt in ("csv", "tsv"):
        passages = _rows(text, "\t" if fmt == "tsv" else None, fmt.upper())
    else:  # pragma: no cover - format_of decides the formats
        raise LoaderError(f"no reader for {fmt}")
    if not passages:
        raise LoaderError(f"the {fmt.upper()} document contains no values")
    return passages


# -- JSON and YAML ---------------------------------------------------------------


def _load_json(text: str, line: int | None = None) -> Any:
    where = f" (line {line})" if line else ""
    try:
        return json.loads(text)
    except RecursionError:
        raise LoaderError(f"JSON nests deeper than {MAX_DEPTH} levels{where}") from None
    except ValueError as exc:
        raise LoaderError(f"not valid JSON{where}: {exc}") from None


def _load_yaml(text: str) -> Any:
    try:
        documents = list(yaml.safe_load_all(text))
    except RecursionError:
        raise LoaderError(f"YAML nests deeper than {MAX_DEPTH} levels") from None
    except yaml.YAMLError as exc:
        raise LoaderError(f"not valid YAML: {exc}") from None
    return documents[0] if len(documents) == 1 else documents


@dataclass
class _Tree:
    """One line per value with its key path; one passage per object or
    list (its own scalar values), nested containers in their own."""

    name: str
    values: int = 0
    # Containers on the current path: an alias cycle (YAML) never ends.
    _open: set[int] = field(default_factory=set)

    def render(self, root: Any) -> list[Passage]:
        return list(self.walk(root, "", 0))

    def walk(self, node: Any, path: str, depth: int) -> Iterator[Passage]:
        if depth > MAX_DEPTH:
            raise LoaderError(f"{self.name} nests deeper than {MAX_DEPTH} levels")
        if not isinstance(node, dict | list):
            self._count()
            yield Passage(text=f"{path or 'value'}: {_scalar(node)}")
            return
        if id(node) in self._open:
            raise LoaderError(f"{self.name} refers to itself")
        self._open.add(id(node))
        items = node.items() if isinstance(node, dict) else enumerate(node)
        lines: list[str] = []
        nested: list[tuple[Any, str]] = []
        for key, value in items:
            child = _child(path, key)
            if isinstance(value, dict | list) and value:
                nested.append((value, child))
            else:
                self._count()
                lines.append(f"{child}: {_scalar(value)}")
        if lines:
            yield Passage(text="\n".join(lines))
        elif not nested:
            self._count()
            yield Passage(text=f"{path or 'value'}: {'{}' if isinstance(node, dict) else '[]'}")
        for value, child in nested:
            yield from self.walk(value, child, depth + 1)
        self._open.discard(id(node))

    def _count(self) -> None:
        self.values += 1
        if self.values > MAX_VALUES:
            raise LoaderError(f"{self.name} has more than {MAX_VALUES} values")


def _child(path: str, key: Any) -> str:
    if isinstance(key, int):
        return f"{path}[{key}]"
    return f"{path}.{key}" if path else str(key)


def _scalar(value: Any) -> str:
    if isinstance(value, dict):
        return "{}"
    if isinstance(value, list):
        return "[]"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, int | float):
        return json.dumps(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return " ".join(str(value).split())


# -- XML -------------------------------------------------------------------------


@dataclass
class _Xml:
    """One line per element text and attribute with its element path
    (`feed/entry[2]/title`); an element's leaf children and attributes in
    one passage, elements with children of their own in theirs."""

    values: int = 0
    elements: int = 0

    def render(self, body: bytes) -> list[Passage]:
        try:
            root = parse_xml(body, forbid_dtd=False, forbid_entities=True, forbid_external=True)
        except DefusedXmlException:
            raise LoaderError(
                "the XML declares entities or external references, which are not read"
            ) from None
        except ParseError as exc:
            raise LoaderError(f"not valid XML: {exc}") from None
        except RecursionError:
            raise LoaderError(f"XML nests deeper than {MAX_DEPTH} levels") from None
        return list(self._walk(root, _tag(root), 0))

    def _walk(self, element: Element, path: str, depth: int) -> Iterator[Passage]:
        if depth > MAX_DEPTH:
            raise LoaderError(f"XML nests deeper than {MAX_DEPTH} levels")
        lines = self._own(element, path)
        nested: list[tuple[Element, str]] = []
        for child, child_path in self._children(element, path):
            if len(child):
                nested.append((child, child_path))
            else:
                lines.extend(self._own(child, child_path))
            if child.tail and child.tail.strip():
                lines.append(self._line(path, child.tail))
        if lines:
            yield Passage(text="\n".join(lines))
        for child, child_path in nested:
            yield from self._walk(child, child_path, depth + 1)

    def _own(self, element: Element, path: str) -> list[str]:
        lines = [self._line(f"{path}@{_local(k)}", v) for k, v in element.attrib.items()]
        if element.text and element.text.strip():
            lines.append(self._line(path, element.text))
        return lines

    def _children(self, element: Element, path: str) -> Iterator[tuple[Element, str]]:
        """Each child element with its path; siblings sharing a name are
        numbered from 1 (`item[1]`, `item[2]`), a single one is not."""
        children = [c for c in element if isinstance(c.tag, str)]
        self.elements += len(children)
        if self.elements > MAX_VALUES:
            raise LoaderError(f"XML has more than {MAX_VALUES} elements")
        totals: dict[str, int] = {}
        for child in children:
            totals[_tag(child)] = totals.get(_tag(child), 0) + 1
        seen: dict[str, int] = {}
        for child in children:
            name = _tag(child)
            seen[name] = seen.get(name, 0) + 1
            suffix = f"[{seen[name]}]" if totals[name] > 1 else ""
            yield child, f"{path}/{name}{suffix}"

    def _line(self, path: str, text: str) -> str:
        self.values += 1
        if self.values > MAX_VALUES:
            raise LoaderError(f"XML has more than {MAX_VALUES} values")
        return f"{path}: {' '.join(text.split())}"


def _local(name: str) -> str:
    """The name without its namespace URI (`{http://…}title` → `title`)."""
    return name.rpartition("}")[2]


def _tag(element: Element) -> str:
    return _local(element.tag) if isinstance(element.tag, str) else "node"


# -- CSV and TSV -----------------------------------------------------------------


def _rows(text: str, delimiter: str | None, name: str) -> list[Passage]:
    """One passage per row, every value named by its column, so a number is
    never cited without what it measures. The first row is the header."""
    if delimiter is None:
        delimiter = _delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    previous = csv.field_size_limit(MAX_FIELD_CHARS)
    try:
        rows = _read_rows(reader, name)
    finally:
        csv.field_size_limit(previous)
    if not rows:
        return []
    header = [h.strip() or f"column {i + 1}" for i, h in enumerate(rows[0])]
    passages = []
    for number, row in enumerate(rows[1:], start=1):
        cells = [
            f"{header[i] if i < len(header) else f'column {i + 1}'}: {' '.join(v.split())}"
            for i, v in enumerate(row)
            if v.strip()
        ]
        if cells:
            passages.append(Passage(text=f"row {number}: " + "; ".join(cells)))
    if not passages:  # a header alone
        passages.append(Passage(text="columns: " + "; ".join(header)))
    return passages


def _read_rows(reader: Any, name: str) -> list[list[str]]:
    rows: list[list[str]] = []
    values = 0
    try:
        for row in reader:
            if len(row) > MAX_COLUMNS:
                raise LoaderError(
                    f"{name} line {len(rows) + 1} has more than {MAX_COLUMNS} columns"
                )
            values += len(row)
            if values > MAX_VALUES:
                raise LoaderError(f"{name} has more than {MAX_VALUES} values")
            rows.append(row)
    except csv.Error as exc:
        if "field larger than field limit" in str(exc):
            raise LoaderError(
                f"{name} has a value longer than {MAX_FIELD_CHARS} characters"
            ) from None
        raise LoaderError(f"not valid {name}: {exc}") from None
    return rows


def _delimiter(text: str) -> str:
    """Comma, or what the first lines use instead (semicolon, tab, pipe)."""
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",;\t|").delimiter
    except csv.Error:
        return ","
