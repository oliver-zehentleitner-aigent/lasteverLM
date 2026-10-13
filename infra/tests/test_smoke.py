"""Checks tests/smoke.py against an in-process stub of the three APIs.

The stub implements just enough of the v1 contract for the smoke test
to walk through; it is not a test of any service. Run with
`python3 -m unittest discover -s tests`.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import threading
import unittest
import uuid
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import smoke  # noqa: E402

TOKEN = "demo-secret"


class Stub(BaseHTTPRequestHandler):
    """One notebook store per server; behaviour switches via server.mode."""

    def log_message(self, *_):  # keep the test output quiet
        pass

    # helpers -------------------------------------------------------------
    def _send(self, status: int, payload=None):
        body = b"" if payload is None else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> bytes:
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    def _authed(self) -> bool:
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self._send(401, {"error": "unauthenticated"})
            return False
        return True

    # routes --------------------------------------------------------------
    def do_GET(self):
        if not self._authed():
            return
        store = self.server.store
        if self.path == "/api/account/me":
            return self._send(
                200,
                {
                    "id": "0000",
                    "email": "demo@localhost",
                    "is_admin": False,
                    "balance_cents": 0 if self.server.mode == "broke" else 1000,
                    "created_at": "2026-01-01T00:00:00Z",
                },
            )
        m = re.fullmatch(r"/api/ingest/notebooks/([^/]+)/sources", self.path)
        if m:
            sources = store["sources"].get(m.group(1), [])
            for s in sources:
                s["polls"] += 1
                if s["polls"] >= 2:
                    s["status"] = "failed" if self.server.mode == "fail-source" else "ready"
            return self._send(200, [{k: v for k, v in s.items() if k != "polls"} for s in sources])
        m = re.fullmatch(r"/api/rag/conversations/([^/]+)/messages", self.path)
        if m and m.group(1) in store["conversations"]:
            return self._send(200, store["messages"].get(m.group(1), []))
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._authed():
            return
        store = self.server.store
        body = self._body()
        if self.path == "/api/ingest/notebooks":
            nb = {"id": str(uuid.uuid4()), "title": json.loads(body)["title"], "created_at": "now"}
            store["notebooks"][nb["id"]] = nb
            return self._send(201, nb)
        m = re.fullmatch(r"/api/ingest/notebooks/([^/]+)/sources", self.path)
        if m:
            assert self.headers["Content-Type"].startswith(
                "multipart/form-data"
            ), "multipart expected"
            assert b'name="file"' in body and b"Zeltavia" in body, "file part missing"
            # Like ingest's library: the same bytes again are linked, already ready.
            content = body.split(b"\r\n\r\n", 1)[1].rsplit(b"\r\n--", 1)[0]
            digest = hashlib.sha256(content).hexdigest()
            known = store["library"].get(digest)
            src = {
                "id": str(uuid.uuid4()),
                "notebook_id": m.group(1),
                "library_id": known or str(uuid.uuid4()),
                "name": "zeltavia.txt",
                "kind": "text",
                "status": "ready" if known else "processing",
                "error": None,
                "created_at": "now",
                "polls": 0,
            }
            store["library"][digest] = src["library_id"]
            store["sources"].setdefault(m.group(1), []).append(src)
            return self._send(200 if known else 202, {k: v for k, v in src.items() if k != "polls"})
        m = re.fullmatch(r"/api/rag/notebooks/([^/]+)/conversations", self.path)
        if m:
            assert not body, "the smoke test opens a conversation with an empty body"
            conv = {
                "id": str(uuid.uuid4()),
                "notebook_id": m.group(1),
                "title": "New conversation",
                "created_at": "now",
            }
            store["conversations"][conv["id"]] = conv
            return self._send(201, conv)
        m = re.fullmatch(r"/api/rag/notebooks/([^/]+)/ask", self.path)
        if m:
            nb_id = m.group(1)
            conv_id = json.loads(body).get("conversation_id")
            if store["conversations"].get(conv_id, {}).get("notebook_id") != nb_id:
                return self._send(
                    422, {"detail": [{"loc": ["body", "conversation_id"], "msg": "Field required"}]}
                )
            src = store["sources"][nb_id][0]
            if self.server.mode == "no-citation":
                answer = {
                    "message_id": "m1",
                    "answer": "The sources do not cover this.",
                    "citations": [],
                }
            else:
                answer = {
                    "message_id": "m1",
                    "answer": "The capital of Zeltavia is Marrow Bay [1], on the river Quill [1].",
                    "citations": [
                        {
                            "n": 1,
                            "source_id": src["id"],
                            "source_name": src["name"],
                            "source_kind": "text",
                            "chunk_id": "c1",
                            "page": None,
                            "quote": "The capital of the fictional country Zeltavia is Marrow Bay.",
                        }
                    ],
                }
            store["messages"].setdefault(conv_id, []).extend(
                [
                    {
                        "id": "u1",
                        "role": "user",
                        "content": json.loads(body)["question"],
                        "citations": None,
                        "created_at": "now",
                    },
                    {
                        "id": "m1",
                        "role": "assistant",
                        "content": answer["answer"],
                        "citations": answer["citations"],
                        "created_at": "now",
                    },
                ]
            )
            return self._send(200, answer)
        self._send(404, {"error": "not found"})

    def do_DELETE(self):
        if not self._authed():
            return
        store = self.server.store
        m = re.fullmatch(r"/api/ingest/notebooks/([^/]+)", self.path)
        if m and store["notebooks"].pop(m.group(1), None):
            store["deleted"].append(m.group(1))
            return self._send(204)
        m = re.fullmatch(r"/api/ingest/library/([^/]+)", self.path)
        if m and m.group(1) in store["library"].values():
            store["library"] = {k: v for k, v in store["library"].items() if v != m.group(1)}
            return self._send(204)
        self._send(404, {"error": "not found"})


class SmokeTest(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        self.server.store = {
            "notebooks": {},
            "sources": {},
            "conversations": {},
            "library": {},
            "messages": {},
            "deleted": [],
        }
        self.server.mode = "ok"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def _run(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = smoke.main([self.url, "--token", TOKEN, "--ready-timeout", "10", *extra])
        return code, out.getvalue(), err.getvalue()

    def test_happy_path_passes_and_cleans_up(self):
        code, out, _ = self._run()
        self.assertEqual(code, 0, out)
        self.assertIn("OK:", out)
        self.assertEqual(len(self.server.store["deleted"]), 1)
        self.assertEqual(self.server.store["notebooks"], {})
        self.assertEqual(self.server.store["library"], {}, "the library source must go too")

    def test_every_run_uploads_new_content(self):
        # With --keep the library keeps the first run's bytes; a second run with
        # the same text would be linked as ready at once and fail.
        self.assertEqual(self._run("--keep")[0], 0)
        code, out, err = self._run()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(self.server.store["library"]), 1)

    def test_keep_leaves_the_notebook(self):
        code, _, _ = self._run("--keep")
        self.assertEqual(code, 0)
        self.assertEqual(self.server.store["deleted"], [])
        self.assertEqual(len(self.server.store["library"]), 1)

    def test_missing_citation_fails(self):
        self.server.mode = "no-citation"
        code, _, err = self._run()
        self.assertEqual(code, 1)
        self.assertIn("no citations", err)
        self.assertEqual(len(self.server.store["deleted"]), 1, "cleanup must run on failure")
        self.assertEqual(self.server.store["library"], {})

    def test_failed_source_fails(self):
        self.server.mode = "fail-source"
        code, _, err = self._run()
        self.assertEqual(code, 1)
        self.assertIn("processing failed", err)

    def test_exhausted_credit_fails_before_creating_anything(self):
        self.server.mode = "broke"
        code, _, err = self._run()
        self.assertEqual(code, 1)
        self.assertIn("no credit", err)
        self.assertEqual(self.server.store["notebooks"], {})

    def test_wrong_token_is_a_failure_not_a_crash(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = smoke.main([self.url, "--token", "wrong"])
        self.assertEqual(code, 1)
        self.assertIn("401", err.getvalue())

    def test_unreachable_is_exit_2(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = smoke.main(["http://127.0.0.1:9", "--token", TOKEN, "--timeout", "2"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
