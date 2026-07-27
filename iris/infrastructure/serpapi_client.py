"""SerpApi HTTP helper for Iris Light docs/self-check.

Hermes chat path uses the Hermes ``serpapi`` web provider + skill.
This module mirrors the engine catalog for Iris-side reference and tests.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"

# engine_id → query parameter name
ENGINE_QUERY_PARAMS: dict[str, str] = {
    "google": "q",
    "google_light": "q",
    "google_images": "q",
    "google_news": "q",
    "google_videos": "q",
    "google_scholar": "q",
    "google_maps": "q",
    "google_local": "q",
    "google_shopping": "q",
    "google_jobs": "q",
    "google_flights": "q",
    "google_hotels": "q",
    "google_finance": "q",
    "google_autocomplete": "q",
    "google_patents": "q",
    "google_trends": "q",
    "bing": "q",
    "bing_images": "q",
    "bing_news": "q",
    "yahoo": "p",
    "yahoo_images": "p",
    "yahoo_videos": "p",
    "duckduckgo": "q",
    "baidu": "q",
    "yandex": "text",
    "youtube": "search_query",
    "amazon": "k",
    "naver": "query",
}


def list_engines() -> list[str]:
    return sorted(ENGINE_QUERY_PARAMS)


def search(
    query: str,
    *,
    engine: str = "google",
    api_key: str | None = None,
    num: int = 5,
) -> dict[str, Any]:
    """Call SerpApi. Returns parsed JSON dict (may include top-level ``error``)."""
    key = (api_key or os.environ.get("SERPAPI_API_KEY") or os.environ.get("SERPAPI_KEY") or "").strip()
    if not key:
        return {"error": "SERPAPI_API_KEY not set"}
    eng = (engine or "google").strip().lower()
    qparam = ENGINE_QUERY_PARAMS.get(eng, "q")
    params = {"engine": eng, "api_key": key, "num": max(1, min(int(num), 100)), qparam: query}
    req = Request(
        f"{SERPAPI_ENDPOINT}?{urlencode(params)}",
        headers={"User-Agent": "iris-light-serpapi/1.0"},
        method="GET",
    )
    try:
        with urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"error": f"HTTP {exc.code}", "body": body[:400]}
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {"error": str(exc)}


if __name__ == "__main__":
    assert "google" in ENGINE_QUERY_PARAMS
    assert ENGINE_QUERY_PARAMS["yahoo_images"] == "p"
    assert list_engines()[0]
    print("serpapi_client self-check ok", len(ENGINE_QUERY_PARAMS), "engines")
