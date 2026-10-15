"""No rag source file has a PEP 263 encoding pattern in its first two
lines: CodeQL's extractor reads "coding: <word>" there even inside a
docstring, takes the word for the file's encoding and skips the file."""

import re
from pathlib import Path

ENCODING = re.compile(r"coding[:=]\s*([-\w.]+)")
ROOT = Path(__file__).resolve().parents[1]


def test_no_source_file_declares_an_encoding_by_accident():
    files = [
        p
        for folder in ("lasteverlm_rag", "tests", "evals")
        if (ROOT / folder).is_dir()
        for p in (ROOT / folder).rglob("*.py")
    ]
    assert files
    found = [
        str(p.relative_to(ROOT))
        for p in files
        if any(ENCODING.search(line) for line in p.read_text().splitlines()[:2])
    ]
    assert found == []
