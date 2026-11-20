"""Model-facing short tool names → Iris Control actions (by surface).

Domain table + OpenAI schema stubs + surface arg adapter.
Home write_file → Control ``local.write_file`` (tool grant + registry).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, TypedDict

Toolset = Literal["file", "terminal", "web", "code"]
Owner = Literal["iris", "hermes"]
Surface = Literal["home", "ide"]

# Registry / agent.tools ownership marker for Iris-backed model names.
IRIS_MODEL_TOOLSET = "iris"


class ModelTool(TypedDict):
    toolset: Toolset
    keep_upstream: bool
    owner: Owner
    control_by_surface: dict[Surface, str | None]


MODEL_TOOL_NAMES: dict[str, ModelTool] = {
    "write_file": {
        "toolset": "file",
        "keep_upstream": False,
        "owner": "iris",
        "control_by_surface": {"home": "local.write_file", "ide": "project.write_file"},
    },
    "read_file": {
        "toolset": "file",
        "keep_upstream": False,
        "owner": "iris",
        "control_by_surface": {"home": "local.read_file", "ide": "project.read_file"},
    },
    "search_files": {
        "toolset": "file",
        "keep_upstream": False,
        "owner": "iris",
        "control_by_surface": {"home": "local.search_files", "ide": "project.list_files"},
    },
    "terminal": {
        "toolset": "terminal",
        "keep_upstream": False,
        "owner": "iris",
        "control_by_surface": {"home": "shell.run", "ide": "project.run"},
    },
    "web_search": {
        "toolset": "web",
        "keep_upstream": False,
        "owner": "iris",
        "control_by_surface": {
            "home": "web.run_search",
            "ide": "web.run_search",
        },
    },
    "web_extract": {
        "toolset": "web",
        "keep_upstream": False,
        "owner": "iris",
        "control_by_surface": {
            "home": "web.run_extract",
            "ide": "web.run_extract",
        },
    },
    "execute_code": {
        "toolset": "code",
        "keep_upstream": False,
        "owner": "iris",
        "control_by_surface": {
            "home": "chat.exec_python",
            "ide": "chat.exec_python",
        },
    },
}

# Minimal Hermes-shaped OpenAI function bodies (path/content/command).
_MODEL_OPENAI: dict[str, dict[str, Any]] = {
    "write_file": {
        "description": "Write content to a file (Iris Control).",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    "read_file": {
        "description": "Read a text file (Iris Control).",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    "search_files": {
        "description": "Search files by pattern or query (Iris Control).",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "query": {"type": "string"},
                "path": {"type": "string"},
            },
        },
    },
    "terminal": {
        "description": "Run a shell command (Iris Control; no console window).",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "cwd": {"type": "string"},
            },
            "required": ["command"],
        },
    },
    "web_search": {
        "description": "Search the web (Iris Control).",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    "web_extract": {
        "description": "Extract page text from URLs (Iris Control).",
        "parameters": {
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "format": {"type": "string"},
                "char_limit": {"type": "integer"},
            },
            "required": ["urls"],
        },
    },
    "execute_code": {
        "description": "Run whitelisted Python (numpy/matplotlib) via Iris Control.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "timeout": {"type": "number"},
                "timeout_s": {"type": "number"},
            },
            "required": ["code"],
        },
    },
}


def lookup(name: str) -> ModelTool | None:
    return MODEL_TOOL_NAMES.get(name)


def iris_backed_model_names() -> tuple[str, ...]:
    return tuple(
        name
        for name, row in MODEL_TOOL_NAMES.items()
        if row["owner"] == "iris" and not row["keep_upstream"]
    )


def upstream_keep_names() -> tuple[str, ...]:
    return tuple(name for name, row in MODEL_TOOL_NAMES.items() if row["keep_upstream"])


def control_action(model_name: str, surface: Surface) -> str | None:
    row = MODEL_TOOL_NAMES[model_name]
    return row["control_by_surface"][surface]


def as_model_surface(raw: object) -> Surface:
    """Map speak_surface / aliases onto the MODEL_TOOL_NAMES surface key."""
    value = str(raw or "").strip().lower()
    if value in {"ide", "ide_companion", "companion"}:
        return "ide"
    return "home"


def openai_schema(name: str) -> dict[str, Any]:
    """OpenAI function body (description + parameters) for one model tool name."""
    return dict(_MODEL_OPENAI[name])


def adapt_control_invoke(
    model_name: str,
    surface: Surface,
    args: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Model OpenAI args → (control_action, Control invoke args).

    Driven by ``MODEL_TOOL_NAMES``; only reshapes keys Control expects.
    """
    action = control_action(model_name, surface)
    if not action:
        raise KeyError(f"no control action for model_name={model_name!r} surface={surface!r}")
    raw = dict(args or {})
    if model_name == "write_file":
        path = str(raw.get("path") or raw.get("rel_path") or "").strip()
        out: dict[str, Any] = {"content": raw.get("content")}
        if surface == "home":
            out["path"] = path
        else:
            out["rel_path"] = path
            for key in ("open", "typewriter", "project_root"):
                if key in raw:
                    out[key] = raw[key]
        return action, out
    if model_name == "read_file":
        path = str(raw.get("path") or raw.get("rel_path") or "").strip()
        out = {"path": path} if surface == "home" else {"rel_path": path}
        if "max_bytes" in raw:
            out["max_bytes"] = raw["max_bytes"]
        return action, out
    if model_name == "search_files":
        query = str(raw.get("query") or raw.get("pattern") or "").strip()
        if surface == "home":
            out = {
                "root": str(raw.get("root") or raw.get("path") or "").strip(),
                "query": query,
            }
        else:
            out = {"query": query}
            if "name" in raw:
                out["name"] = raw["name"]
        if "limit" in raw:
            out["limit"] = raw["limit"]
        return action, out
    if model_name == "terminal":
        out = {"command": str(raw.get("command") or raw.get("cmd") or "").strip()}
        if surface == "home":
            if raw.get("cwd") not in (None, ""):
                out["cwd"] = raw["cwd"]
        else:
            for key in (
                "file",
                "rel_path",
                "timeout_sec",
                "reveal_terminal",
                "open_browser",
                "project_root",
            ):
                if key in raw:
                    out[key] = raw[key]
        return action, out
    if model_name == "web_search":
        out = {"query": str(raw.get("query") or "").strip()}
        if "limit" in raw:
            out["limit"] = raw["limit"]
        return action, out
    if model_name == "web_extract":
        urls = raw.get("urls")
        if urls is None and raw.get("url") is not None:
            urls = [raw.get("url")]
        out = {"urls": urls}
        if "format" in raw:
            out["format"] = raw["format"]
        if "char_limit" in raw:
            out["char_limit"] = raw["char_limit"]
        return action, out
    if model_name == "execute_code":
        out = {"code": str(raw.get("code") or raw.get("source") or "")}
        if raw.get("timeout_s") not in (None, ""):
            out["timeout_s"] = raw["timeout_s"]
        elif raw.get("timeout") not in (None, ""):
            out["timeout_s"] = raw["timeout"]
        return action, out
    raise KeyError(f"unknown model_name={model_name!r}")


def iris_model_registrations(
    surface: Surface,
) -> tuple[tuple[str, str, dict[str, Any]], ...]:
    """(model_name, control_action_id, schema) for Iris-backed replace."""
    rows: list[tuple[str, str, dict[str, Any]]] = []
    for name in iris_backed_model_names():
        action = control_action(name, surface)
        if not action:
            continue
        rows.append((name, action, openai_schema(name)))
    return tuple(rows)


# Engine (provider) names → reason. PHASE4 grants stay; model schemas hide overlap.
# Keys match engine_tool_name(action) (dots → underscores).
_NAMES_HIDDEN_FROM_MODEL: dict[str, str] = {
    "project_write_file": "model write_file covers project.write_file",
    "project_read_file": "model read_file covers project.read_file",
    "project_list_files": "model search_files covers project.list_files",
    "project_run": "model terminal covers project.run",
    "shell_run": "model terminal covers shell.run",
    "local_write_file": "model write_file covers local.write_file",
    "local_read_file": "model read_file covers local.read_file",
    "local_search_files": "model search_files covers local.search_files",
    "web_run_search": "model web_search covers web.run_search",
    "web_run_extract": "model web_extract covers web.run_extract",
    "chat_exec_python": "model execute_code covers chat.exec_python",
    "control_invoke": (
        "prefer model names + first-class Iris tools; grant kept for adapters/UI"
    ),
}


def names_hidden_from_model() -> dict[str, str]:
    """Engine tool names to omit from model schemas when model_names are active."""
    return dict(_NAMES_HIDDEN_FROM_MODEL)


def actions_hidden_from_model() -> frozenset[str]:
    """Dotted Control action ids matching ``names_hidden_from_model``."""
    return frozenset(
        name.replace("_", ".", 1) for name in _NAMES_HIDDEN_FROM_MODEL
    )


def catalog_uses_model_tool_names() -> bool:
    """True once `_sidecar_main` loads/uses this module.

    Sidecar must file-location-load via ``_load_local_helper`` so engine venv
    never executes ``iris.engine.__init__`` (PyQt6).
    """
    src = Path(__file__).with_name("_sidecar_main.py").read_text(encoding="utf-8")
    if "model_tool_names" not in src:
        return False
    if '_load_local_helper("model_tool_names")' not in src:
        return False
    if "from iris.engine.model_tool_names" in src:
        return False
    uses = (
        "MODEL_TOOL_NAMES" in src
        or "iris_backed_model_names" in src
        or "upstream_keep_names" in src
        or "control_action" in src
        or "iris_model_registrations" in src
        or "adapt_control_invoke" in src
        or "names_hidden_from_model" in src
    )
    return uses
