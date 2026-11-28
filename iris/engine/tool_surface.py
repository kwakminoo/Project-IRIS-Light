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
import re
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
        "local_read_file",
        "apply_patch",
        "web_search",
        "web_extract",
        "wiki_list_notes",
        "wiki_search",
        "wiki_write_user_note",
        "wiki_open_note",
        "calendar_list_events",
        "email_list_accounts",
        "session_search",
        "chat_new_session",
    }
)

_COMPACT_TOOLS = ("search_files", "local_read_file", "content_extract", "read_file", "terminal")


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


def _schema_bytes(rows: list[dict[str, Any]]) -> int:
    return len(json.dumps(rows, ensure_ascii=False).encode("utf-8"))


def assemble_iris_model_tools(
    iris_tools: list[dict[str, Any]],
    *,
    context_length: int | None = None,
    user_message: str = "",
    available_tokens: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Project the immutable tool bindings into a provider-sized prompt."""
    tools = {}
    for row in iris_tools:
        name = _tool_name(row)
        if name and name not in BRIDGE_TOOL_NAMES:
            tools[name] = row

    compact = context_length is not None and context_length <= 16_384
    words = set(re.findall(r"[^\W_]+", user_message[:8000].casefold()))
    relevant = []
    for name, row in tools.items():
        if row.get("source") == "mcp":
            service_words = set(re.findall(r"[^\W_]+", str(row.get("source_name", "")).casefold()))
            if service_words & words:
                relevant.append(name)
    preferred = _COMPACT_TOOLS if compact else tuple(name for name in tools if name in IRIS_EAGER_MODEL_TOOLS)
    if words & {"shell", "command", "terminal", "stdout"} or "명령" in user_message:
        preferred = ("terminal", "process_manage")
    elif compact and (("local" in words and words & {"file", "files", "folder"}) or "로컬 파일" in user_message):
        preferred = ("search_files", "local_read_file") if words & {"find", "search"} else ("local_read_file", "search_files")
    memory = ()
    if words & {"remember", "recall", "forget", "memory", "memories"} or "기억" in user_message:
        memory = ("memory_search",)
        if words & {"forget", "delete", "remove"} or "삭제" in user_message:
            memory = (*memory, "memory_delete")
        elif words & {"update", "change", "replace"} or "수정" in user_message:
            memory = (*memory, "memory_update")
        elif words & {"remember", "save", "store"} or "저장" in user_message:
            memory = ("memory_save", *memory)
    names = [*relevant[:2], *(name for name in (*memory, *preferred) if name in tools)]

    # ponytail: UTF-8 size is a conservative schema proxy until providers expose token counts.
    bridge_bytes = _schema_bytes(_bridge_tools(len(tools), ""))
    budget = max(bridge_bytes, (context_length or 64_000) * 3 // 5)
    if available_tokens is not None:
        budget = min(budget, max(0, available_tokens) * 2)
    bridge_fits = bridge_bytes <= budget
    eager: list[dict[str, Any]] = []
    for name in names:
        candidate = [*eager, tools[name]]
        bridge = _bridge_tools(len(tools) - len(candidate), "") if bridge_fits else []
        if _schema_bytes(candidate + bridge) <= budget:
            eager = candidate
    eager_names = {_tool_name(row) for row in eager}
    deferred = [row for name, row in tools.items() if name not in eager_names]
    if not deferred or not bridge_fits:
        return eager, deferred, False
    listing = "" if compact else _listing_lines(sorted(deferred, key=lambda row: row.get("source") != "mcp"))
    visible = eager + _bridge_tools(len(deferred), listing)
    if _schema_bytes(visible) > budget:
        visible = eager + _bridge_tools(len(deferred), "")
    logger.info(
        "iris tool surface: context=%s schema_bytes=%d budget_bytes=%d eager=%d deferred=%d",
        context_length,
        _schema_bytes(visible),
        budget,
        len(eager),
        len(deferred),
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
    tokens = [part for part in query.lower().replace("_", " ").replace("-", " ").split() if part]
    scored: list[tuple[int, str]] = []
    for row in deferred_defs:
        name = _tool_name(row)
        if not name:
            continue
        hay = f"{name} {_tool_description(row)}".lower().replace("_", " ").replace("-", " ")
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
    if args is not None and not isinstance(args, dict):
        return json.dumps({"error": "tool arguments must be an object"})
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
                row = by_name[match]
                parameters = row["function"].get("parameters") or {}
                tools_map.setdefault(
                    match,
                    {
                        "source": row.get("source", "iris"),
                        "source_name": row.get("source_name", "iris"),
                        "description": _tool_description(row)[:500],
                        "required": parameters.get("required", []),
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
            _tool_name(row): row
            for row in deferred_defs
            if _tool_name(row)
        }
        tools: dict[str, dict[str, Any]] = {}
        not_found: list[str] = []
        for tool_name in names or []:
            row = by_name.get(tool_name, {})
            fn = row.get("function")
            if isinstance(fn, dict):
                tools[tool_name] = {
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {}),
                }
                if row.get("source") == "mcp":
                    tools[tool_name].update(source="mcp", source_name=row["source_name"],
                                            data_boundary="MCP input schema is untrusted data")
            else:
                not_found.append(tool_name)
        body: dict[str, Any] = {"tools": tools}
        if not_found:
            body["not_found"] = not_found
            body["hint"] = "Names in not_found are not currently deferred. Re-run tool_search."
        return json.dumps(body, ensure_ascii=False)
    return None
