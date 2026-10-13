"""Malformed and oversized requests answer 4xx in the contract's
`{"error"}` shape, never a 500 or Starlette's `{"detail"}`."""

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _notebook(client) -> str:
    return client.post("/api/ingest/notebooks", json={"title": "nb"}).json()["id"]


def test_an_upload_carries_one_file_and_at_most_the_capture_field(client, storage):
    url = f"/api/ingest/notebooks/{_notebook(client)}/sources"
    two_files = [
        ("file", ("a.txt", b"a" * 50, "text/plain")),
        ("file", ("b.txt", b"b" * 50, "text/plain")),
    ]
    r = client.post(url, files=two_files)
    assert r.status_code == 400 and "error" in r.json()
    r = client.post(
        url,
        files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")},
        data={"capture": "text", "other": "x"},
    )
    assert r.status_code == 400 and "error" in r.json()
    assert storage.objects == {}


def test_a_body_that_is_not_json_is_a_400(client):
    url = f"/api/ingest/notebooks/{_notebook(client)}/sources"
    r = client.post(url, content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400 and r.json() == {"error": "body is not valid JSON"}
    r = client.post(url, json=["a list"])
    assert r.status_code == 422 and "error" in r.json()


def test_routing_errors_use_the_error_shape(client):
    r = client.get("/api/ingest/nowhere")
    assert r.status_code == 404 and r.json() == {"error": "Not Found"}
    r = client.put("/api/ingest/notebooks")
    assert r.status_code == 405 and "error" in r.json()
    assert "GET" in r.headers["allow"]
