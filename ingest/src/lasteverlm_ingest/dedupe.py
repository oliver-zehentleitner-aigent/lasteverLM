"""The keys a library source is deduplicated by, per owner: the same key
again links the existing entry instead of storing or processing anything.
Uploads and the demo seeds build them here, so a user uploading a demo
file again finds the demo source."""

from __future__ import annotations

import hashlib

from lasteverlm_ingest.loaders.url import normalize_url


def file_key(data: bytes, capture: str | None = None) -> str:
    """`sha256:<hex>` of the bytes; a PDF appends its capture mode, since
    the same bytes read another way are another library source."""
    key = "sha256:" + hashlib.sha256(data).hexdigest()
    return f"{key}:{capture}" if capture is not None else key


def url_key(url: str) -> str:
    """`url:<normalized URL>`; raises ValueError for a URL `check_url` refuses."""
    return "url:" + normalize_url(url)
