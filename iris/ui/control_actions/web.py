"""Control actions for Iris-owned web_search / web_extract (product chat path)."""

from __future__ import annotations

from typing import Any

from iris.system.control_surface import ActionRegistry, err_result, ok_result
from iris.system.iris_web import extract as iris_extract
from iris.system.iris_web import search as iris_search


def register_web_actions(window: Any, reg: ActionRegistry) -> None:
    del window  # no Qt host needed; network I/O only

    def web_run_search(args: dict[str, Any]) -> dict[str, Any]:
        query = str((args or {}).get("query") or "").strip()
        limit = (args or {}).get("limit", 5)
        payload = iris_search(query, limit=limit)
        if not payload.get("success"):
            return err_result(
                "web.run_search",
                str(payload.get("error") or "web search failed"),
                payload,
            )
        return ok_result("web.run_search", payload)

    def web_run_extract(args: dict[str, Any]) -> dict[str, Any]:
        raw = args or {}
        urls = raw.get("urls")
        payload = iris_extract(
            urls if urls is not None else raw.get("url"),
            format=raw.get("format"),
            char_limit=raw.get("char_limit"),
        )
        if not payload.get("success"):
            return err_result(
                "web.run_extract",
                str(payload.get("error") or "web extract failed"),
                payload,
            )
        return ok_result("web.run_extract", payload)

    reg.register(
        "web.run_search",
        web_run_search,
        summary=(
            "Search the web via Iris (Brave/Tavily/Exa/SerpAPI keys from settings). "
            "Required: query. Optional: limit (1..100)."
        ),
        risk="low",
        confirm_required=False,
    )
    reg.register(
        "web.run_extract",
        web_run_extract,
        summary=(
            "Extract readable text from public http(s) URLs (Iris urllib lane). "
            "Required: urls (list, max 5). Optional: char_limit."
        ),
        risk="low",
        confirm_required=False,
    )
