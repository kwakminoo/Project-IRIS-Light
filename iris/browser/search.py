"""Pure search URL builders — no network I/O."""

from __future__ import annotations

from urllib.parse import quote_plus


def search_url(query: str, *, engine: str = "web") -> str:
    q = (query or "").strip()
    if not q:
        raise ValueError("query required")
    eng = (engine or "web").strip().lower()
    if eng != "web":
        raise ValueError(f"unsupported search engine: {engine}")
    return f"https://duckduckgo.com/?q={quote_plus(q)}"
