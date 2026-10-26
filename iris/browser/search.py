from __future__ import annotations

from urllib.parse import quote_plus

from iris.browser.youtube import youtube_search_url

BROWSER_HOME_URL = "https://www.google.com"

_ENGINES = {
    "web": "https://duckduckgo.com/?q={q}",
    "duckduckgo": "https://duckduckgo.com/?q={q}",
    "google": "https://www.google.com/search?q={q}&hl=ko",
    "youtube": None,
}


def normalize_search_engine(engine: str) -> str:
    eng = (engine or "web").strip().lower() or "web"
    if eng in ("ddg", "duckduckgo"):
        return "web"
    if eng not in ("web", "google", "youtube"):
        raise ValueError(f"unsupported search engine: {engine}")
    return eng


def search_url(query: str, *, engine: str = "web") -> str:
    q = (query or "").strip()
    if not q:
        raise ValueError("query required")
    eng = normalize_search_engine(engine)
    if eng == "youtube":
        return youtube_search_url(q)
    template = _ENGINES[eng]
    return template.format(q=quote_plus(q))
