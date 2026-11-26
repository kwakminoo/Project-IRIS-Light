"""Iris-native tool progressive disclosure for the product sidecar.

Hermes tool_search only defers registry-backed / explicitly listed tools. Iris
replaces ``agent.tools`` with Speak schemas that are not in the Hermes registry,
so every name stayed eager and gpt-oss under ``tool_choice=required`` could
mispick ``search_files`` instead of the prompted ``terminal`` tool.

This module keeps a small ambient set visible and puts the rest behind a
tool_search / tool_describe / tool_call bridge. Bindings for every Iris tool
stay installed so an unwrapped ``tool_call`` still routes natively.

Assembly is self-contained (no snowballstemmer / tools.tool_search import) so
workspace self-checks and the product sidecar share one path.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

TOOL_SEARCH_NAME = "tool_search"
TOOL_DESCRIBE_NAME = "tool_describe"
TOOL_CALL_NAME = "tool_call"
BRIDGE_TOOL_NAMES = frozenset(
    {TOOL_SEARCH_NAME, TOOL_DESCRIBE_NAME, TOOL_CALL_NAME}
)

# Ambient model-visible tools. File discovery stays deferred — measured FPR13
# l04 competitor under tool_choice=required on gpt-oss:20b.
IRIS_EAGER_MODEL_TOOLS = frozenset(
    {
        "terminal",
        "ping",
        "get_catalog",
        "get_state",
        "settings_get",
        "process_manage",
        "write_file",
        "read_file",
        "apply_patch",
        "web_search",
        "web_extract",
        "wiki_list_notes",
        "wiki_search",
        "wiki_write_user_note",
        "wiki_open_note",
        "calendar_list_events",
        "email_list_accounts",
        "chat_search_past",
        "chat_new_session",
    }
)


def _tool_name(tool_def: dict[str, Any]) -> str:
    fn = tool_def.get("function") if isinstance(tool_def, dict) else None
    if isinstance(fn, dict):
        return str(fn.get("name") or "").strip()
    return ""


def _tool_description(tool_def: dict[str, Any]) -> str:
    fn = tool_def.get("function") if isinstance(tool_def, dict) else None
    if isinstance(fn, dict):
        return str(fn.get("description") or "")
    return ""


def _bridge_schema(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def _bridge_tools(deferred_count: int, listing: str) -> list[dict[str, Any]]:
    search_desc = (
        f"Find deferred tools ({deferred_count} hidden). "
        "Search by capability keywords, then tool_describe before tool_call. "
        "Prefer an already-visible tool (e.g. terminal) when the user named it."
    )
    if listing:
        search_desc += (
            "\n\nEvery tool listed below exists: never call it unavailable, and go "
            f"straight to `{TOOL_DESCRIBE_NAME}` when you see the exact name.\n\n"
            + listing
        )
    return [
        _bridge_schema(
            TOOL_SEARCH_NAME,
            search_desc,
            {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Capability keywords (e.g. ['search files', 'open browser']).",
                },
                "limit": {"type": "integer", "description": "Max matches per query (default 5)."},
            },
            ["queries"],
        ),
        _bridge_schema(
            TOOL_DESCRIBE_NAME,
            f"Load JSON schemas for tools returned by `{TOOL_SEARCH_NAME}`.",
            {
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Exact deferred tool names.",
                },
            },
            ["names"],
        ),
        _bridge_schema(
            TOOL_CALL_NAME,
            "Invoke deferred tools as {name, arguments} entries after tool_describe.",
            {
                "calls": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "arguments": {"type": "object"},
                        },
                        "required": ["name", "arguments"],
                    },
                },
            },
            ["calls"],
        ),
    ]


def _listing_lines(deferred: list[dict[str, Any]], *, max_chars: int = 3500) -> str:
    lines: list[str] = []
    used = 0
    for row in deferred:
        name = _tool_name(row)
        if not name:
            continue
        desc = _tool_description(row).strip().replace("\n", " ")
        if len(desc) > 60:
            desc = desc[:57] + "…"
        line = f"- {name}: {desc}" if desc else f"- {name}"
        if used + len(line) + 1 > max_chars:
            lines.append(f"- …and {len(deferred) - len(lines)} more via tool_search")
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)


def assemble_iris_model_tools(
    iris_tools: list[dict[str, Any]],
    *,
    context_length: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Return ``(model_visible_tools, deferred_tools, activated)``.

    ``context_length`` is accepted for call-site compatibility; activation is
    driven by whether any non-eager Iris tools exist.
    """
    _ = context_length
    eager: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    for row in iris_tools:
        name = _tool_name(row)
        if not name or name in BRIDGE_TOOL_NAMES:
            continue
        if name in IRIS_EAGER_MODEL_TOOLS:
            eager.append(row)
        else:
            deferred.append(row)
    if not deferred:
        return list(eager or iris_tools), [], False
    listing = _listing_lines(deferred)
    visible = list(eager) + _bridge_tools(len(deferred), listing)
    logger.info(
        "iris tool surface: eager=%d deferred=%d activated=True visible=%d",
        len(eager),
        len(deferred),
        len(visible),
    )
    return visible, deferred, True


def _string_list(args: dict[str, Any], key: str, *, max_items: int) -> tuple[list[str] | None, str | None]:
    raw = args.get(key)
    raw = [raw] if isinstance(raw, str) else raw
    if not isinstance(raw, list):
        return None, json.dumps({"error": f"{key} is required and must be an array of strings"})
    out: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    if not out:
        return None, json.dumps({"error": f"{key} must contain at least one non-empty string"})
    if len(out) > max_items:
        return None, json.dumps({"error": f"too many {key}: {len(out)} > max {max_items}"})
    return out, None


def _search_deferred(deferred_defs: list[dict[str, Any]], query: str, *, limit: int) -> list[str]:
    tokens = [part for part in query.lower().replace("_", " ").split() if part]
    scored: list[tuple[int, str]] = []
    for row in deferred_defs:
        name = _tool_name(row)
        if not name:
            continue
        hay = f"{name} {_tool_description(row)}".lower()
        score = sum(1 for token in tokens if token in hay) if tokens else 0
        if not tokens and query.strip():
            score = 1 if query.lower() in hay else 0
        if score > 0:
            scored.append((score, name))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [name for _score, name in scored[:limit]]


def dispatch_iris_bridge(
    name: str,
    args: dict[str, Any] | None,
    *,
    deferred_defs: list[dict[str, Any]],
) -> str | None:
    """Handle tool_search / tool_describe against Iris deferred defs.

    ``tool_call`` returns a hint JSON (executor unwrap normally peels it first).
    Returns None when *name* is not a bridge tool.
    """
    if name not in BRIDGE_TOOL_NAMES:
        return None
    payload = dict(args or {})
    if name == TOOL_CALL_NAME:
        return json.dumps(
            {
                "error": "call the underlying tool name directly after tool_describe",
                "hint": "Iris routes deferred tools after tool_call unwrap",
            },
            ensure_ascii=False,
        )
    if name == TOOL_SEARCH_NAME:
        queries, err = _string_list(payload, "queries", max_items=7)
        if err:
            return err
        raw_limit = payload.get("limit")
        try:
            limit = 5 if raw_limit is None else max(1, min(25, int(raw_limit)))
        except (TypeError, ValueError):
            limit = 5
        tools_map: dict[str, dict[str, Any]] = {}
        results: list[dict[str, Any]] = []
        by_name = {_tool_name(row): row for row in deferred_defs if _tool_name(row)}
        for query in queries or []:
            matches = _search_deferred(deferred_defs, query, limit=limit)
            for match in matches:
                row = by_name.get(match)
                tools_map.setdefault(
                    match,
                    {
                        "source": "iris",
                        "source_name": "iris",
                        "description": (_tool_description(row) if row else "")[:500],
                        "required": [],
                    },
                )
            results.append({"query": query, "matches": matches})
        return json.dumps(
            {
                "queries": queries,
                "total_available": len(by_name),
                "results": results,
                "tools": tools_map,
            },
            ensure_ascii=False,
        )
    if name == TOOL_DESCRIBE_NAME:
        names, err = _string_list(payload, "names", max_items=10)
        if err:
            return err
        by_name = {
            _tool_name(row): (row.get("function") or {})
            for row in deferred_defs
            if _tool_name(row)
        }
        tools: dict[str, dict[str, Any]] = {}
        not_found: list[str] = []
        for tool_name in names or []:
            fn = by_name.get(tool_name)
            if isinstance(fn, dict):
                tools[tool_name] = {
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {}),
                }
            else:
                not_found.append(tool_name)
        body: dict[str, Any] = {"tools": tools}
        if not_found:
            body["not_found"] = not_found
            body["hint"] = "Names in not_found are not currently deferred. Re-run tool_search."
        return json.dumps(body, ensure_ascii=False)
    return None
