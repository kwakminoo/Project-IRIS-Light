"""SerpApi web search plugin — Hermes bundled backend (Iris Light)."""

from __future__ import annotations

from plugins.web.serpapi.provider import SerpApiWebSearchProvider


def register(ctx) -> None:
    ctx.register_web_search_provider(SerpApiWebSearchProvider())
