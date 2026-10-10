"""SearXNG client: loopback-only, bounded, sanitized; no network is touched."""

import io
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "os-assistant/.local/share/os-assistant"))

from os_assistant import websearch
from os_assistant.config import Config
from os_assistant.contracts import AssistantError
from os_assistant.ollama import NoRedirect

CONFIG = Config(web_search_enabled=True)
SECRET = "very-secret-query"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    def __init__(self, body=b"", error=None):
        self.body, self.error, self.calls = body, error, []

    def open(self, request, timeout=None):
        self.calls.append((request, timeout))
        if self.error:
            raise self.error
        return FakeResponse(self.body)


@pytest.fixture
def opener(monkeypatch):
    fake = FakeOpener()
    seen = []

    def build(*handlers):
        seen.extend(handlers)
        return fake

    monkeypatch.setattr(websearch, "build_opener", build)
    fake.handlers = seen
    return fake


def serve(opener, payload):
    opener.body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()


def test_request_shape_and_hardening(opener):
    serve(opener, {"results": [], "unresponsive_engines": [["a", "timeout"], ["b", "x"]]})
    out = websearch.search(CONFIG, "hello world & more", 5)
    request, timeout = opener.calls[0]
    parts = urlsplit(request.full_url)
    assert request.full_url.startswith("http://127.0.0.1:8888/search?")
    assert parse_qs(parts.query) == {"q": ["hello world & more"], "format": ["json"], "safesearch": ["1"]}
    assert request.get_header("Accept") == "application/json"
    assert not request.has_header("Accept-encoding")
    assert timeout == CONFIG.web_search_timeout
    proxies = [h for h in opener.handlers if type(h).__name__ == "ProxyHandler"]
    assert proxies and proxies[0].proxies == {}
    assert any(isinstance(h, NoRedirect) for h in opener.handlers)
    assert out == {"executor": "searxng", "host": "http://127.0.0.1:8888", "query": "hello world & more",
                   "results": [], "unresponsive_engines": 2}


def test_unresponsive_invalid_counts_zero(opener):
    serve(opener, {"results": [], "unresponsive_engines": "no"})
    assert websearch.search(CONFIG, "q", 3)["unresponsive_engines"] == 0


def test_host_revalidated(opener):
    with pytest.raises(Exception, match="SearXNG host"):
        websearch.search(Config(web_search_host="http://example.com:8888"), "q", 3)
    assert not opener.calls


def test_proxy_env_ignored_and_redirect_not_followed(monkeypatch):
    # Real opener: a 302 must surface as an HTTP error, never be followed.
    for var in ("http_proxy", "HTTP_PROXY", "all_proxy"):
        monkeypatch.setenv(var, "http://127.0.0.1:1")
    handlers = []
    real = websearch.build_opener

    def spy(*h):
        handlers.extend(h)
        return real(*h)

    monkeypatch.setattr(websearch, "build_opener", spy)
    assert handlers == [] and websearch.ProxyHandler({}).proxies == {}
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", "http://example.invalid/x")
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        cfg = Config(web_search_host=f"http://127.0.0.1:{srv.server_address[1]}")
        with pytest.raises(AssistantError, match="HTTP error 302"):
            websearch.search(cfg, "q", 3)
    finally:
        srv.shutdown()
        srv.server_close()


def test_size_cap(opener):
    serve(opener, b'{"results": [], "pad": "' + b"a" * 262144 + b'"}')
    with pytest.raises(AssistantError, match="invalid or oversized"):
        websearch.search(CONFIG, "q", 3)


def test_depth_cap(opener):
    nested = {"results": []}
    node = nested
    for _ in range(20):
        node["x"] = {}
        node = node["x"]
    serve(opener, nested)
    with pytest.raises(AssistantError, match="invalid or oversized"):
        websearch.search(CONFIG, "q", 3)


@pytest.mark.parametrize("payload", [b"not json", [1], {"results": "x"}, {"other": []}, b"\xff\xfe"])
def test_malformed_payloads(opener, payload):
    serve(opener, payload)
    with pytest.raises(AssistantError, match="invalid or oversized"):
        websearch.search(CONFIG, "q", 3)


def test_scheme_filter_and_missing_url(opener):
    serve(opener, {"results": [
        {"title": "js", "url": "javascript:alert(1)"}, {"title": "file", "url": "file:///etc/passwd"},
        {"title": "ftp", "url": "ftp://h/x"}, {"title": "nohost", "url": "http://"},
        {"title": "nourl"}, "junk", {"title": "ok", "url": "https://example.org/a"},
        {"title": "ok2", "url": "http://example.net"},
    ]})
    out = websearch.search(CONFIG, "q", 10)
    assert [r["url"] for r in out["results"]] == ["https://example.org/a", "http://example.net"]


def test_field_caps_and_sanitizing(opener):
    serve(opener, {"results": [{
        "title": "T" * 500, "url": "https://example.org/" + "u" * 100, "content": "c‮\x00  a\n\tb" + "z" * 500,
    }]})
    r = websearch.search(CONFIG, "q", 3)["results"][0]
    assert len(r["title"]) == 200 and r["url"] == "https://example.org/" + "u" * 100 and len(r["snippet"]) == 400
    assert r["snippet"].startswith("c a b")
    assert "‮" not in r["snippet"] and "\x00" not in r["snippet"]


def test_limit_respected(opener):
    serve(opener, {"results": [{"title": str(i), "url": f"https://e.org/{i}"} for i in range(10)]})
    assert len(websearch.search(CONFIG, "q", 4)["results"]) == 4


def test_403_hint(opener):
    opener.error = HTTPError("u", 403, "Forbidden", {}, None)
    with pytest.raises(AssistantError, match="search.formats"):
        websearch.search(CONFIG, SECRET, 3)


def test_other_http_error(opener):
    opener.error = HTTPError("u", 500, "x", {}, None)
    with pytest.raises(AssistantError, match="SearXNG HTTP error 500."):
        websearch.search(CONFIG, "q", 3)


@pytest.mark.parametrize("error", [TimeoutError(), URLError("down"), ConnectionRefusedError()])
def test_unreachable_mapped(opener, error):
    opener.error = error
    with pytest.raises(AssistantError, match="Cannot reach local SearXNG at http://127.0.0.1:8888"):
        websearch.search(CONFIG, "q", 3)


@pytest.mark.parametrize("error", [
    HTTPError("u", 403, "x", {}, None), HTTPError("u", 500, "x", {}, None), TimeoutError(),
    URLError(SECRET), None,
])
def test_query_never_in_errors(opener, error):
    opener.error = error
    if error is None:
        serve(opener, b"garbage")
    with pytest.raises(AssistantError) as info:
        websearch.search(CONFIG, SECRET, 3)
    assert SECRET not in str(info.value)


def test_overlong_url_skipped_not_truncated(opener):
    serve(opener, {"results": [
        {"title": "long", "url": "https://example.org/" + "u" * 600},
        {"title": "edge", "url": "https://example.org/" + "u" * (512 - 20)},
    ]})
    out = websearch.search(CONFIG, "q", 5)["results"]
    assert [r["title"] for r in out] == ["edge"] and len(out[0]["url"]) == 512
