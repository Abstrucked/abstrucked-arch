"""Transport never follows redirects or uses inherited proxies."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "os-assistant/.local/share/os-assistant"))

from os_assistant.config import DEFAULT_MODEL, Config
from os_assistant.contracts import ConfigurationError, ModelError
from os_assistant.ollama import OllamaClient


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        requests = []
        response = {"message": {"content": "hello"}}
        status = 200
        raw = None

        def do_POST(self):
            size = int(self.headers.get("Content-Length", 0))
            self.requests.append((self.path, json.loads(self.rfile.read(size))))
            self.respond()

        def do_GET(self):
            self.requests.append((self.path, None))
            self.respond()

        def respond(self):
            self.send_response(self.status)
            if self.status == 302:
                self.send_header("Location", "http://example.invalid/should-never-connect")
            self.end_headers()
            self.wfile.write(self.raw if self.raw is not None else json.dumps(self.response).encode())

        def log_message(self, *args):
            pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    yield Handler, OllamaClient(Config(host=f"http://127.0.0.1:{http.server_port}"))
    http.shutdown()
    http.server_close()
    thread.join(timeout=2)


def test_native_request_is_local_nonstreaming_nonthinking(server, monkeypatch):
    handler, client = server
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    assert client.chat([{"role": "user", "content": "hello"}], [])["message"]["content"] == "hello"
    endpoint, body = handler.requests[0]
    assert endpoint == "/api/chat"
    assert body["think"] is False and body["stream"] is False
    assert body["keep_alive"] == "2m"
    assert body["options"]["num_ctx"] == 8192
    assert body["options"]["temperature"] == 0
    assert body["options"]["num_predict"] == 768
    assert body["model"] == DEFAULT_MODEL


def test_redirect_is_not_followed(server):
    handler, client = server
    handler.status = 302
    with pytest.raises(ModelError, match="302"):
        client.chat([], [])
    assert len(handler.requests) == 1


@pytest.mark.parametrize("raw", [b"not json", b"[]", b'{"error":"private server detail"}', b"x" * 262145,
                                 b'{"nested":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}"],
                         ids=["invalid-json", "wrong-shape", "server-error", "oversized", "too-deep"])
def test_bad_or_oversized_response_is_safe(server, raw):
    handler, client = server
    handler.raw = raw
    with pytest.raises(ModelError) as error:
        client.chat([], [])
    assert "private server detail" not in str(error.value)


def test_doctor_exposes_only_selected_model_metadata(server):
    handler, client = server
    handler.response = {"models": [{"name": client.config.model, "digest": "sha256:fixture", "size": 1900000000}]}
    assert client.doctor()["digest"] == "sha256:fixture"
    assert handler.requests[0][0] == "/api/tags"


@pytest.mark.parametrize("host", ["http://example.com:11434", "http://localhost:11434", "http://0.0.0.0:11434"])
def test_library_client_rejects_remote_or_ambiguous_hosts(host):
    with pytest.raises(ConfigurationError):
        OllamaClient(Config(host=host))


def test_cloud_model_cannot_be_selected_through_local_server():
    with pytest.raises(ModelError, match="cloud"):
        OllamaClient(Config(model="example-cloud"))


def test_unknown_model_is_rejected_listing_allowed_names():
    with pytest.raises(ModelError, match="not allowed") as exc:
        OllamaClient(Config(model="mistral:7b"))
    assert "llama3.2:3b" in str(exc.value)


def test_allowlisted_non_default_model_is_accepted():
    assert OllamaClient(Config(model="openbmb/minicpm5-2b:latest")).config.model == "openbmb/minicpm5-2b:latest"


def test_doctor_does_not_fall_back_to_other_installed_models(server):
    handler, client = server
    handler.response = {"models": [{"name": "openbmb/minicpm5-2b:latest", "digest": "fixture-old-model", "size": 1900000000}]}
    with pytest.raises(ModelError, match=f"{DEFAULT_MODEL} is not installed"):
        client.doctor()
    assert handler.requests == [("/api/tags", None)]
