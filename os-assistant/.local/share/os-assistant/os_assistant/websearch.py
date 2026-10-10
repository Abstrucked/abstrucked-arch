"""Bounded loopback-only SearXNG JSON client; proxies and redirects disabled."""

import json
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener
import unicodedata

from .config import Config, validate_host
from .contracts import AssistantError
from .ollama import NoRedirect, check_json_depth

INVALID = "SearXNG returned an invalid or oversized response."


def _clean(value: object, limit: int) -> str:
    text = value if isinstance(value, str) else ""
    text = "".join(" " if c.isspace() else c for c in text if c.isspace() or not unicodedata.category(c).startswith("C"))
    return " ".join(text.split())[:limit]


def search(config: Config, query: str, limit: int) -> dict:
    host = validate_host(config.web_search_host, label="SearXNG host")
    opener = build_opener(ProxyHandler({}), NoRedirect())
    request = Request(f"{host}/search?" + urlencode({"q": query, "format": "json", "safesearch": "1"}),
                      headers={"Accept": "application/json"}, method="GET")
    try:
        with opener.open(request, timeout=config.web_search_timeout) as response:
            body = response.read(262145)
        if len(body) > 262144:
            raise AssistantError(INVALID)
        data = json.loads(body)
        check_json_depth(data, AssistantError, INVALID)
    except HTTPError as error:
        if error.code == 403:
            raise AssistantError("SearXNG refused the JSON API; enable json in settings.yml search.formats.") from None
        raise AssistantError(f"SearXNG HTTP error {error.code}.") from None
    except (URLError, TimeoutError, OSError, HTTPException):
        raise AssistantError(f"Cannot reach local SearXNG at {host}; start it or check [web_search] host/timeout.") from None
    except (ValueError, UnicodeError, RecursionError):
        raise AssistantError(INVALID) from None
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise AssistantError(INVALID)
    results = []
    for item in data["results"]:
        if len(results) >= limit:
            break
        if not isinstance(item, dict) or not isinstance(item.get("url"), str):
            continue
        url = _clean(item["url"], 1 << 20)
        if len(url) > 512:  # a truncated URL would be broken, so drop the result
            continue
        try:
            parts = urlsplit(url)
            ok = parts.scheme in ("http", "https") and bool(parts.netloc)
        except ValueError:
            ok = False
        if ok:
            results.append({"title": _clean(item.get("title"), 200), "url": url,
                            "snippet": _clean(item.get("content"), 400)})
    unresponsive = data.get("unresponsive_engines")
    return {"executor": "searxng", "host": host, "query": query, "results": results,
            "unresponsive_engines": len(unresponsive) if isinstance(unresponsive, list) else 0}
