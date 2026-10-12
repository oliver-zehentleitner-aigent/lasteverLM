#!/usr/bin/env python3
"""End-to-end smoke test for a running lasteverLM deployment.

Logs in with the demo token, creates a notebook, uploads a text source,
waits until it is ready, asks a question and asserts that the answer
cites the source. Works against a local stack or the live cluster;
needs only the Python standard library.

    python3 tests/smoke.py https://lasteverlm.example.com --token "$DEMO_TOKEN"

Exit code 0 when every step passed, 1 on a failed assertion, 2 on a
transport error (connection refused, timeout). The notebook is deleted
at the end unless --keep is given.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid

SOURCE_TEXT = (
    "The lasteverLM smoke test document.\n\n"
    "The capital of the fictional country Zeltavia is Marrow Bay. "
    "Marrow Bay has a population of 41,000 and lies on the river Quill. "
    "Zeltavia's national dish is smoked eel with juniper. "
    "The country joined the Northern Trade League in 1987.\n"
)
QUESTION = "What is the capital of Zeltavia and on which river does it lie?"
MARKER = re.compile(r"\[(\d+)\]")


class SmokeFailure(Exception):
    """An assertion about the deployment's behaviour failed."""


class Client:
    def __init__(self, base_url: str, token: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def request(self, method: str, path: str, *, body: bytes | None = None,
                content_type: str | None = None, expect: tuple[int, ...] = (200,)):
        req = urllib.request.Request(self.base_url + path, data=body, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/json")
        if content_type:
            req.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status, raw = resp.status, resp.read()
        except urllib.error.HTTPError as err:
            status, raw = err.code, err.read()
        if status not in expect:
            raise SmokeFailure(f"{method} {path}: expected {expect}, got {status}: {raw[:300]!r}")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SmokeFailure(f"{method} {path}: response is not JSON: {raw[:300]!r}") from exc

    def json(self, method: str, path: str, payload: dict, *, expect=(200,)):
        return self.request(method, path, body=json.dumps(payload).encode(),
                            content_type="application/json", expect=expect)

    def upload(self, path: str, filename: str, content: bytes, *, expect=(202,)):
        boundary = f"----lasteverlm-{uuid.uuid4().hex}"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: text/plain\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        return self.request("POST", path, body=body,
                            content_type=f"multipart/form-data; boundary={boundary}", expect=expect)


def step(name: str) -> None:
    print(f"- {name}", flush=True)


def run(client: Client, ready_timeout: float, keep: bool) -> None:
    step("login with the demo token")
    me = client.request("GET", "/api/account/me")
    for key in ("id", "email", "balance_cents"):
        if key not in me:
            raise SmokeFailure(f"GET /api/account/me: missing {key!r} in {me}")
    if me["balance_cents"] <= 0:
        raise SmokeFailure(f"demo user has no credit: balance_cents={me['balance_cents']}")

    step("create a notebook")
    notebook = client.json("POST", "/api/ingest/notebooks",
                           {"title": f"smoke {time.strftime('%Y-%m-%d %H:%M:%S')}"}, expect=(201,))
    notebook_id = notebook["id"]
    try:
        step("upload a text source")
        source = client.upload(f"/api/ingest/notebooks/{notebook_id}/sources",
                               "zeltavia.txt", SOURCE_TEXT.encode())
        source_id = source["id"]
        if source.get("status") != "processing":
            raise SmokeFailure(f"upload answered with status {source.get('status')!r}, expected 'processing'")

        step(f"wait for the source to become ready (up to {ready_timeout:.0f}s)")
        deadline = time.monotonic() + ready_timeout
        while True:
            sources = client.request("GET", f"/api/ingest/notebooks/{notebook_id}/sources")
            current = next((s for s in sources if s["id"] == source_id), None)
            if current is None:
                raise SmokeFailure("uploaded source disappeared from the notebook")
            if current["status"] == "ready":
                break
            if current["status"] == "failed":
                raise SmokeFailure(f"source processing failed: {current.get('error')!r}")
            if time.monotonic() > deadline:
                raise SmokeFailure(f"source still {current['status']!r} after {ready_timeout:.0f}s")
            time.sleep(2)

        step("ask a question")
        answer = client.json("POST", f"/api/rag/notebooks/{notebook_id}/ask", {"question": QUESTION})
        text = answer.get("answer") or ""
        citations = answer.get("citations") or []
        if not text.strip():
            raise SmokeFailure("empty answer")
        if not citations:
            raise SmokeFailure(f"answer has no citations: {text[:200]!r}")
        numbers = {c.get("n") for c in citations}
        markers = {int(n) for n in MARKER.findall(text)}
        if not markers & numbers:
            raise SmokeFailure(f"answer carries no [n] marker matching a citation; markers={markers}, citations={numbers}")
        for c in citations:
            for key in ("n", "source_id", "source_name", "chunk_id", "quote"):
                if key not in c:
                    raise SmokeFailure(f"citation is missing {key!r}: {c}")
            if c["source_id"] != source_id:
                raise SmokeFailure(f"citation points at a foreign source {c['source_id']!r}")
        if "marrow bay" not in text.lower():
            raise SmokeFailure(f"answer does not name the capital from the source: {text[:200]!r}")
        print(f"  answer: {text[:160]!r}")
        print(f"  citations: {len(citations)}")

        step("read the message history")
        messages = client.request("GET", f"/api/rag/notebooks/{notebook_id}/messages")
        roles = [m.get("role") for m in messages]
        if roles[-2:] != ["user", "assistant"]:
            raise SmokeFailure(f"message history does not end with user, assistant: {roles}")
    finally:
        if keep:
            print(f"  keeping notebook {notebook_id}")
        else:
            step("delete the notebook")
            client.request("DELETE", f"/api/ingest/notebooks/{notebook_id}", expect=(204,))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("base_url", help="e.g. https://lasteverlm.example.com or http://localhost:8080")
    parser.add_argument("--token", default=os.environ.get("DEMO_TOKEN"),
                        help="bearer token; default: $DEMO_TOKEN")
    parser.add_argument("--ready-timeout", type=float, default=120.0,
                        help="seconds to wait for the source to become ready (default 120)")
    parser.add_argument("--timeout", type=float, default=60.0,
                        help="per-request timeout in seconds (default 60)")
    parser.add_argument("--keep", action="store_true", help="do not delete the notebook afterwards")
    args = parser.parse_args(argv)
    if not args.token:
        parser.error("--token or DEMO_TOKEN is required")

    client = Client(args.base_url, args.token, args.timeout)
    try:
        run(client, args.ready_timeout, args.keep)
    except SmokeFailure as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        print(f"ERROR: cannot reach {args.base_url}: {exc}", file=sys.stderr)
        return 2
    print("OK: login, notebook, upload, ready, ask with citation, history, cleanup")
    return 0


if __name__ == "__main__":
    sys.exit(main())
