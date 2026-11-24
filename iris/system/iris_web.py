"""Iris-owned web search / extract (stdlib urllib). No Hermes checkout web tools."""

from __future__ import annotations

import html as html_lib
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from iris.infrastructure.external_api_keys import (
    SEARCH_PRESETS,
    SearchPreset,
    active_search_preset_id,
    load_search_api_keys,
    load_search_entries,
    search_preset_by_id,
)

_TIMEOUT_SEC = 20
_MAX_EXTRACT_BYTES = 500_000
_DEFAULT_CHAR_LIMIT = 15_000
_USER_AGENT = "IRIS-Light/1.0 (+web.run_search)"

# Prefer these when no explicit preset is set (Hermes-shaped cascade, Iris keys).
_FALLBACK_ORDER = ("brave", "tavily", "exa", "serpapi", "firecrawl", "parallel")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = data.strip()
        if text:
            self._chunks.append(text)

    def text(self) -> str:
        return "\n".join(self._chunks)


def _http_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> Any:
    req_headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SEC) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8", errors="replace"))


def _http_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SEC) as resp:
        return resp.read(_MAX_EXTRACT_BYTES)


def ensure_search_provider() -> tuple[SearchPreset | None, str]:
    """Pick one Iris search preset that is ready (key or key_optional)."""
    keys = load_search_api_keys()
    entries = load_search_entries()
    active = active_search_preset_id(entries) if entries else ""
    candidates: list[str] = []
    if active and active != "none":
        candidates.append(active)
    for pid in entries:
        if pid not in candidates and pid != "none":
            candidates.append(pid)
    for pid in _FALLBACK_ORDER:
        if pid not in candidates:
            candidates.append(pid)
    for pid in candidates:
        preset = search_preset_by_id(pid)
        if preset.id == "none":
            continue
        if preset.key_optional and not preset.env_key:
            # ddgs etc. — Phase1 Iris lane has no DDG client; skip to keyed APIs.
            continue
        if preset.env_key and keys.get(preset.env_key):
            return preset, ""
        if preset.key_optional and preset.env_key and keys.get(preset.env_key):
            return preset, ""
    return None, (
        "검색 API 키가 없습니다. 설정에서 Brave/Tavily/Exa/SerpAPI 등 키를 등록하세요."
    )


def _hit(title: str, url: str, description: str, position: int) -> dict[str, Any]:
    return {
        "title": title or url,
        "url": url,
        "description": description or "",
        "position": position,
    }


def _search_brave(query: str, limit: int, api_key: str) -> list[dict[str, Any]]:
    qs = urllib.parse.urlencode({"q": query, "count": str(limit)})
    data = _http_json(
        f"https://api.search.brave.com/res/v1/web/search?{qs}",
        headers={"X-Subscription-Token": api_key},
    )
    rows = ((data or {}).get("web") or {}).get("results") or []
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows[:limit], start=1):
        out.append(
            _hit(
                str(row.get("title") or ""),
                str(row.get("url") or ""),
                str(row.get("description") or ""),
                i,
            )
        )
    return out


def _search_tavily(query: str, limit: int, api_key: str) -> list[dict[str, Any]]:
    body = json.dumps(
        {"api_key": api_key, "query": query, "max_results": limit}
    ).encode("utf-8")
    data = _http_json(
        "https://api.tavily.com/search",
        method="POST",
        headers={"Content-Type": "application/json"},
        body=body,
    )
    rows = (data or {}).get("results") or []
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows[:limit], start=1):
        out.append(
            _hit(
                str(row.get("title") or ""),
                str(row.get("url") or ""),
                str(row.get("content") or row.get("snippet") or ""),
                i,
            )
        )
    return out


def _search_exa(query: str, limit: int, api_key: str) -> list[dict[str, Any]]:
    body = json.dumps({"query": query, "numResults": limit}).encode("utf-8")
    data = _http_json(
        "https://api.exa.ai/search",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
        },
        body=body,
    )
    rows = (data or {}).get("results") or []
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows[:limit], start=1):
        out.append(
            _hit(
                str(row.get("title") or ""),
                str(row.get("url") or ""),
                str(row.get("text") or row.get("snippet") or ""),
                i,
            )
        )
    return out


def _search_serpapi(query: str, limit: int, api_key: str) -> list[dict[str, Any]]:
    qs = urllib.parse.urlencode(
        {"engine": "google", "q": query, "api_key": api_key, "num": str(limit)}
    )
    data = _http_json(f"https://serpapi.com/search.json?{qs}")
    rows = (data or {}).get("organic_results") or []
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows[:limit], start=1):
        out.append(
            _hit(
                str(row.get("title") or ""),
                str(row.get("link") or ""),
                str(row.get("snippet") or ""),
                i,
            )
        )
    return out


def _search_firecrawl(query: str, limit: int, api_key: str) -> list[dict[str, Any]]:
    body = json.dumps({"query": query, "limit": limit}).encode("utf-8")
    data = _http_json(
        "https://api.firecrawl.dev/v1/search",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        body=body,
    )
    rows = ((data or {}).get("data") or []) if isinstance(data, dict) else []
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows[:limit], start=1):
        out.append(
            _hit(
                str(row.get("title") or ""),
                str(row.get("url") or ""),
                str(row.get("description") or row.get("markdown") or ""),
                i,
            )
        )
    return out


_SEARCHERS = {
    "brave": _search_brave,
    "tavily": _search_tavily,
    "exa": _search_exa,
    "serpapi": _search_serpapi,
    "firecrawl": _search_firecrawl,
}


def search(query: str, *, limit: int = 5) -> dict[str, Any]:
    """Hermes-shaped search: ``{success, data.web[]}`` or ``{success:false, error}``."""
    q = (query or "").strip()
    if not q:
        return {"success": False, "error": "query required"}
    try:
        lim = min(max(int(limit), 1), 100)
    except (TypeError, ValueError):
        lim = 5
    preset, err = ensure_search_provider()
    if preset is None:
        return {"success": False, "error": err}
    fn = _SEARCHERS.get(preset.id)
    if fn is None:
        return {
            "success": False,
            "error": f"Iris web lane does not implement preset {preset.id!r} yet",
        }
    keys = load_search_api_keys()
    api_key = keys.get(preset.env_key, "")
    if not api_key:
        return {"success": False, "error": f"{preset.env_key} missing"}
    try:
        hits = fn(q, lim, api_key)
    except urllib.error.HTTPError as exc:
        return {"success": False, "error": f"{preset.id} HTTP {exc.code}"}
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"success": False, "error": f"{preset.id} failed: {exc}"}
    return {"success": True, "data": {"web": hits}, "backend": preset.id}


def _is_blocked_host(host: str) -> bool:
    host = (host or "").strip().lower().rstrip(".")
    if not host or host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return True
    for info in infos:
        ip_s = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_s)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            return True
    return False


def _strip_html(raw: bytes, char_limit: int) -> str:
    text = raw.decode("utf-8", errors="replace")
    parser = _TextExtractor()
    try:
        parser.feed(text)
        parser.close()
        body = parser.text()
    except Exception:
        body = re.sub(r"<[^>]+>", " ", text)
        body = html_lib.unescape(re.sub(r"\s+", " ", body)).strip()
    if len(body) <= char_limit:
        return body
    head = char_limit // 2
    tail = char_limit - head
    return body[:head] + "\n…\n" + body[-tail:]


def extract(
    urls: list[Any] | str,
    *,
    format: str | None = None,  # noqa: A002 — Hermes-shaped arg name
    char_limit: int | None = None,
) -> dict[str, Any]:
    """Extract page text. Returns ``{results: [...]}`` (Hermes-adjacent)."""
    del format  # unused Phase1
    if isinstance(urls, str):
        url_list = [urls]
    else:
        url_list = [str(u).strip() for u in (urls or []) if str(u).strip()]
    if not url_list:
        return {"success": False, "error": "urls required", "results": []}
    url_list = url_list[:5]
    try:
        limit = int(char_limit) if char_limit is not None else _DEFAULT_CHAR_LIMIT
    except (TypeError, ValueError):
        limit = _DEFAULT_CHAR_LIMIT
    limit = min(max(limit, 500), 100_000)
    results: list[dict[str, Any]] = []
    for raw_url in url_list:
        parsed = urlparse(raw_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            results.append({"url": raw_url, "success": False, "error": "invalid url"})
            continue
        if _is_blocked_host(parsed.hostname or ""):
            results.append({"url": raw_url, "success": False, "error": "blocked host"})
            continue
        try:
            raw = _http_bytes(raw_url)
            text = _strip_html(raw, limit)
            results.append({"url": raw_url, "success": True, "content": text})
        except urllib.error.HTTPError as exc:
            results.append({"url": raw_url, "success": False, "error": f"HTTP {exc.code}"})
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            results.append({"url": raw_url, "success": False, "error": str(exc)})
    ok_any = any(r.get("success") for r in results)
    return {"success": ok_any, "results": results}


def _self_check() -> None:
    # No key → structured error, no hang.
    from unittest.mock import patch

    empty = {p.env_key: "" for p in SEARCH_PRESETS if p.env_key}
    with patch(f"{__name__}.load_search_api_keys", return_value=empty), patch(
        f"{__name__}.load_search_entries", return_value=[]
    ):
        out = search("iris", limit=3)
    assert out.get("success") is False, out
    assert out.get("error"), out
    print("iris_web self_check ok", out.get("error")[:80])


if __name__ == "__main__":
    _self_check()
