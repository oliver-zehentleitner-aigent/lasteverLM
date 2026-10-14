import ipaddress
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lasteverlm_ingest.loaders import LoaderError, TransientLoaderError
from lasteverlm_ingest.loaders.html import HtmlLoader
from lasteverlm_ingest.loaders.pdf import PdfLoader
from lasteverlm_ingest.loaders.text import TextLoader
from lasteverlm_ingest.loaders.url import (
    Fetcher,
    GuardedBackend,
    UrlLoader,
    check_url,
    is_public,
)
from tests.test_loaders import minimal_pdf

PAGE = b"""<!doctype html><html><head><title>Lake  Report</title>
<meta charset="utf-8"><style>p{color:red}</style><script>var x=1;</script></head>
<body><nav>Home | About</nav><main><h1>Lake Report</h1><p>The lake is
 <b>deep</b>.</p><p>It is cold &amp; clear.</p></main><footer>(c) site</footer></body></html>"""

ROUTES: dict[str, tuple[int, dict[str, str], bytes]] = {
    "/page": (200, {"Content-Type": "text/html; charset=utf-8"}, PAGE),
    "/text": (200, {"Content-Type": "text/plain"}, "Grüße aus Wien".encode()),
    "/doc.pdf": (200, {"Content-Type": "application/pdf"}, minimal_pdf(["PDF behind a link"])),
    "/hop": (302, {"Location": "/page"}, b""),
    "/loop": (302, {"Location": "/loop"}, b""),
    "/missing": (404, {"Content-Type": "text/html"}, b"no"),
    "/busy": (503, {"Content-Type": "text/html"}, b"later"),
    "/image": (200, {"Content-Type": "image/png"}, b"\x89PNG"),
    "/big": (200, {"Content-Type": "text/plain"}, b"x" * 5000),
}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        status, headers, body = ROUTES[self.path]
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture(scope="module")
def server() -> Iterator[str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _loader(**fetcher_args: object) -> UrlLoader:
    # Loopback is the test server; production keeps the default guard.
    fetcher = Fetcher(max_bytes=4000, allowed=lambda _: True, **fetcher_args)  # type: ignore[arg-type]
    return UrlLoader(fetch=fetcher.fetch, text=TextLoader(), pdf=PdfLoader())


def test_html_page_keeps_title_and_main_content(server):
    [passage] = _loader().load(f"{server}/page".encode())
    assert passage.text == "Lake Report\n\nThe lake is deep.\n\nIt is cold & clear."


def test_redirect_text_and_pdf(server):
    assert _loader().load(f"{server}/hop".encode())[0].text.startswith("Lake Report")
    assert _loader().load(f"{server}/text".encode())[0].text == "Grüße aus Wien"
    [page] = _loader().load(f"{server}/doc.pdf".encode())
    assert "PDF behind a link" in page.text and page.page == 1


@pytest.mark.parametrize(
    ("path", "error", "message"),
    [
        ("/missing", LoaderError, "answered 404"),
        ("/busy", TransientLoaderError, "answered 503"),
        ("/image", LoaderError, "unsupported content type 'image/png'"),
        ("/big", LoaderError, "too large"),
        ("/loop", LoaderError, "redirects"),
    ],
)
def test_fetch_failures_are_classified(server, path, error, message):
    with pytest.raises(error, match=message):
        _loader().load(f"{server}{path}".encode())


def test_connection_refused_is_transient():
    with pytest.raises(TransientLoaderError):
        _loader().load(b"http://127.0.0.1:9/")


def test_default_guard_refuses_internal_addresses(server):
    loader = UrlLoader(fetch=Fetcher(max_bytes=1000).fetch, text=TextLoader(), pdf=PdfLoader())
    with pytest.raises(LoaderError, match="not a public address"):
        loader.load(f"{server}/page".encode())
    with pytest.raises(LoaderError, match="not a public address"):
        loader.load(b"http://localhost:1/")


@pytest.mark.parametrize(
    ("address", "public"),
    [
        ("93.184.215.14", True),
        ("2606:4700::1111", True),
        ("127.0.0.1", False),
        ("10.0.0.5", False),
        ("172.16.3.4", False),
        ("192.168.1.1", False),
        ("169.254.169.254", False),
        ("100.64.0.1", False),
        ("0.0.0.0", False),
        ("::1", False),
        ("fd00::1", False),
        ("fe80::1", False),
        ("::ffff:10.0.0.1", False),
        ("224.0.0.1", False),
    ],
)
def test_is_public(address, public):
    assert is_public(ipaddress.ip_address(address)) is public


def test_check_url():
    assert check_url(" https://example.org/x ") == "https://example.org/x"
    for bad in (
        "file:///etc/passwd",
        "gopher://x",
        "https://",
        "http://a:b@host/",
        "http://h:99999/",
    ):
        with pytest.raises(ValueError):
            check_url(bad)


def test_html_without_main_uses_body_and_charset():
    page = "<html><body><p>Straße</p><div>zwei</div></body></html>".encode("iso-8859-1")
    [passage] = HtmlLoader().load(page, "iso-8859-1")
    assert passage.text == "Straße\n\nzwei"
    with pytest.raises(LoaderError):
        HtmlLoader().load(b"<html><body><script>x()</script></body></html>")


def test_a_hanging_dns_lookup_is_bounded_by_the_deadline():
    release = threading.Event()

    def hang(*_args, **_kwargs):
        release.wait(5)
        return []

    started = time.monotonic()
    with pytest.raises(TransientLoaderError, match="did not resolve in time"):
        GuardedBackend(resolve=hang).connect_tcp("slow.example", 443, timeout=0.2)
    assert time.monotonic() - started < 2
    release.set()


def test_an_app_shell_says_it_needs_javascript():
    from lasteverlm_ingest.loaders.html import HtmlLoader

    shell = (
        b"<!doctype html><html><head><title>lasteverLM</title>"
        b'<script type="module" src="/assets/index.js"></script></head>'
        b'<body><div id="root"></div></body></html>'
    )
    with pytest.raises(LoaderError, match="no readable text without JavaScript"):
        HtmlLoader().load(shell)
    with pytest.raises(LoaderError, match="^the page contains no readable text$"):
        HtmlLoader().load(b"<html><body><div></div></body></html>")
