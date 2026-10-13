"""Bounded loopback-only HTTP client, with proxies and redirects disabled."""

import json
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .config import ALLOWED_MODELS, Config, model_not_allowed_message, validate_host
from .contracts import ModelError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check_json_depth(value: object, error_cls: type[Exception], message: str, depth: int = 0) -> None:
    if depth > 16:
        raise error_cls(message)
    if isinstance(value, dict):
        children = value.values()
    elif isinstance(value, list):
        children = value
    else:
        return
    for child in children:
        check_json_depth(child, error_cls, message, depth + 1)


def bounded_json(body: bytes) -> dict:
    result = json.loads(body)
    check_json_depth(result, ModelError, "Local model response exceeded the JSON nesting limit.")
    if not isinstance(result, dict) or "error" in result:
        raise ModelError("Ollama returned an invalid response or model error.")
    return result


class OllamaClient:
    def __init__(self, config: Config):
        self.config = config
        validate_host(config.host)
        if config.model not in ALLOWED_MODELS:
            raise ModelError(model_not_allowed_message(config.model))
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def _request(self, endpoint: str, payload: dict | None = None) -> dict:
        encoded = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(self.config.host + endpoint, data=encoded,
                          headers={"Content-Type": "application/json"}, method="GET" if payload is None else "POST")
        try:
            with self.opener.open(request, timeout=self.config.model_timeout) as response:
                body = response.read(262145)
            if len(body) > 262144:
                raise ModelError("Local model response exceeded the size limit.")
            return bounded_json(body)
        except HTTPError as error:
            raise ModelError(f"Ollama HTTP error {error.code}; check the local model and runtime.") from None
        except (URLError, TimeoutError, OSError, HTTPException):
            raise ModelError("Cannot reach local Ollama; start it on 127.0.0.1:11434 and check the timeout.") from None
        except (ValueError, UnicodeError, RecursionError):
            raise ModelError("Ollama returned invalid JSON; nothing executed.") from None

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        return self._request("/api/chat", {
            "model": self.config.model, "messages": messages, "tools": tools,
            "stream": False, "think": False, "keep_alive": self.config.keep_alive,
            "options": {"num_ctx": self.config.context, "num_predict": self.config.max_output_tokens, "temperature": 0},
        })

    def doctor(self) -> dict:
        models = self._request("/api/tags").get("models", [])
        if not isinstance(models, list):
            raise ModelError("Invalid local model listing.")
        for model in models:
            if isinstance(model, dict) and model.get("name") == self.config.model:
                if not isinstance(model.get("digest"), str) or not model["digest"]:
                    raise ModelError("Local model listing lacks its artifact digest.")
                return {"model": self.config.model, "host": self.config.host,
                        "digest": model.get("digest"), "size_bytes": model.get("size"),
                        "context": self.config.context,
                        "max_output_tokens": self.config.max_output_tokens, "keep_alive": self.config.keep_alive}
        raise ModelError(f"Configured model {self.config.model} is not installed; pull the exact configured tag first.")
