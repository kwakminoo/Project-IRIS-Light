"""Iris product speak capability — SpeakAllowlist / SpeakTools (Unit2).

One name space: Control action ids. Speak path is always ``call_path=native``.
No MCP stdio / Control HTTP on the product speak path.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shlex
import time
from dataclasses import dataclass, field
from enum import Enum
from subprocess import list2cmdline
from typing import Any, Callable, Literal, Mapping, Protocol

from iris.apps.directory import AppDirectory, entries_as_dicts
from iris.infrastructure.absorbed_tool_aliases import (
    action_to_model_name,
    model_names,
    resolve_action,
)

# Model-facing default when SpeakGrant.parameters is unset (no free-form open object).
EMPTY_OBJECT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


def _params(
    properties: Mapping[str, Any],
    *,
    required: list[str] | None = None,
    additional: bool = False,
    any_of: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """JSON-Schema object body for SpeakGrant.parameters."""
    out: dict[str, Any] = {
        "type": "object",
        "properties": dict(properties),
        "additionalProperties": additional,
    }
    if required:
        out["required"] = list(required)
    if any_of:
        out["anyOf"] = list(any_of)
    return out


# True zero-arg tools only. Anything else with EMPTY/None fails _check_tool_contract.
EMPTY_SCHEMA_ACTIONS: frozenset[str] = frozenset(
    {
        "ping",
        "get_catalog",
        "get_state",
        "settings.get",
        "wiki.list_notes",
        "email.list_accounts",
        "calendar.list_events",
        "chat.new_session",
        "app.demo_ping",
        "ide.enter_companion",
        "ide.exit_companion",
        "ide.diagnostics",
        "learning.list",
        "learning.start",
        "learning.stop",
        "learning.status",
        "skill.list",
        "voice.mic_off",
        "voice.mic_on",
        "voice.toggle_mic",
        "voice.mic_status",
        "workspace.open_assistant",
        "workspace.open_calendar",
        "workspace.open_email",
        "workspace.open_obsidian",
        "workspace.open_mobile",
        "browser.back",
        "browser.forward",
        "browser.reload",
        "browser.open",
        "browser.snapshot",
        "calendar.refresh_holidays",
        "calendar.status",
        "email.open_compose",
        "emulator.kill",
        "emulator.launch",
        "emulator.screenshot",
        "emulator.status",
        "emulator.wait_ready",
        "emulator.ui_texts",
        "emulator.logcat_tail",
        "routine.list",
        "project.list_files",
        "project.list_parents",
        "wiki.reload",
    }
)


class ExecKind(str, Enum):
    """How SpeakTools reaches the ActionRegistry body (or a pure stand-in)."""

    PURE = "pure"
    SURFACE = "surface"


@dataclass(frozen=True)
class SpeakGrant:
    """One agent-callable Control action. Name == ActionRegistry action id."""

    action: str
    kind: ExecKind
    summary: str = ""
    parameters: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class SpeakToolRow:
    """Catalog row derived from SpeakGrant + ActionSpec."""

    name: str
    summary: str
    domain: str
    needs_ui: bool
    confirm_required: bool
    risk: str


@dataclass(frozen=True)
class ToolResult:
    """Domain result. Not HTTP/MCP wire."""

    ok: bool
    action: str
    data: dict[str, Any]
    error: str = ""
    call_path: str = "native"
    bridge: str = "none"
    call_id: str | None = None
    tool_name: str | None = None
    status: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool | None = None
    duration_ms: int | None = None
    truncated: bool | None = None
    artifact_ref: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ok": self.ok,
            "action": self.action,
            "tool": self.action,
            "call_path": self.call_path,
            "bridge": self.bridge,
            "data": self.data,
        }
        if not self.ok:
            out["error"] = self.error
        for key in (
            "call_id",
            "tool_name",
            "status",
            "error_code",
            "error_message",
            "retryable",
            "duration_ms",
            "truncated",
            "artifact_ref",
        ):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        return out


@dataclass(frozen=True)
class IrisToolContract:
    """Unified tool contract projection over SpeakGrant (+ optional ActionSpec)."""

    canonical_name: str
    control_action: str
    description: str
    input_schema: Mapping[str, Any]
    risk: str = "low"
    confirm_required: bool = False
    profiles: frozenset[str] = field(default_factory=frozenset)
    # Conservative defaults — optimistic only when explicitly known.
    parallel_safe: bool = False
    headless_supported: bool = False
    side_effects: bool = False
    aliases: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class EngineToolBinding:
    """Read-only product projection used by both sides of the native bridge."""

    model_name: str
    canonical_action: str
    description: str
    input_schema: Mapping[str, Any]
    fingerprint: str
    source: str = "iris"
    source_name: str = "iris"


class ActionCatalogView(Protocol):
    def spec(self, name: str) -> Any | None: ...

    def catalog(self) -> list[dict[str, Any]]: ...


class SurfaceInvoker(Protocol):
    def invoke(self, action: str, args: dict[str, Any]) -> dict[str, Any] | None: ...


PureHandler = Callable[[dict[str, Any]], ToolResult]


def validate_tool_arguments(
    schema: Mapping[str, Any] | None, args: Mapping[str, Any] | None
) -> None:
    """Validate ``args`` against a JSON-Schema-like object. Raises TypeError/ValueError.

    ``schema is None`` means the grant has not declared parameters yet — only require a
    mapping. Declared schemas (including EMPTY_OBJECT_SCHEMA) are enforced.
    """
    if args is not None and not isinstance(args, Mapping):
        raise TypeError("tool arguments must be an object")
    payload = dict(args or {})
    if schema is None:
        return
    if not isinstance(schema, Mapping):
        raise TypeError("tool schema must be an object")
    schema_type = schema.get("type", "object")
    if schema_type != "object":
        raise ValueError(f"unsupported tool schema type: {schema_type!r}")
    props = schema.get("properties") or {}
    if props is not None and not isinstance(props, Mapping):
        raise TypeError("schema properties must be an object")
    props_map: Mapping[str, Any] = props if isinstance(props, Mapping) else {}
    required = schema.get("required") or []
    if not isinstance(required, (list, tuple)):
        raise TypeError("schema required must be a list")
    for key in required:
        if key not in payload:
            raise ValueError(f"missing required argument: {key}")
    any_of = schema.get("anyOf")
    if any_of is not None:
        if not isinstance(any_of, (list, tuple)) or not any_of:
            raise TypeError("schema anyOf must be a non-empty list")
        matched = False
        for branch in any_of:
            if not isinstance(branch, Mapping):
                continue
            branch_req = branch.get("required") or []
            if not isinstance(branch_req, (list, tuple)):
                continue
            if all(k in payload for k in branch_req):
                matched = True
                break
        if not matched:
            raise ValueError("arguments do not satisfy anyOf")
    additional = schema.get("additionalProperties", True)
    for key, value in payload.items():
        if key in props_map:
            _validate_schema_value(key, value, props_map[key])
        elif additional is False:
            raise ValueError(f"unexpected argument: {key}")
        elif isinstance(additional, Mapping):
            _validate_schema_value(key, value, additional)


def _validate_schema_value(key: str, value: Any, node: Mapping[str, Any] | Any) -> None:
    if not isinstance(node, Mapping):
        return
    expected = node.get("type")
    if expected is None:
        return
    ok = True
    if expected == "string":
        ok = isinstance(value, str)
    elif expected == "integer":
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif expected == "number":
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif expected == "boolean":
        ok = isinstance(value, bool)
    elif expected == "object":
        ok = isinstance(value, Mapping)
    elif expected == "array":
        ok = isinstance(value, list)
    if not ok:
        raise TypeError(f"argument {key!r} must be {expected}")
    if expected == "integer" and "minimum" in node and value < node["minimum"]:
        raise ValueError(f"argument {key!r} below minimum")
    if expected == "integer" and "maximum" in node and value > node["maximum"]:
        raise ValueError(f"argument {key!r} above maximum")


# One-release shim: product iris.* seed ids → Control action ids.
_LEGACY_TO_ACTION: dict[str, str] = {
    "iris.tools.ping": "ping",
    "iris.tools.catalog": "get_catalog",
    "iris.session.get_state": "get_state",
    "iris.wiki.list_notes": "wiki.list_notes",
    "iris.wiki.search": "wiki.search",
    "iris.mail.list_accounts": "email.list_accounts",
    "iris.calendar.list_events": "calendar.list_events",
    "iris.ide.open_folder": "ide.open_folder",
    "iris.project.open_similar": "project.open_similar",
}


def resolve_legacy_name(name: str) -> str:
    """Map deprecated iris.* seed ids to Control action names."""
    key = (name or "").strip()
    return _LEGACY_TO_ACTION.get(key, key)


# Model often sends cmd/shell; SpeakGrant requires command (Final Gate measured).
_COMMAND_ALIAS_ACTIONS = frozenset({"shell.run", "project.run"})
_COMMAND_ALIAS_KEYS = ("cmd", "shell")
_SHELL_LIST_EXES = frozenset({"bash", "sh", "zsh", "dash"})


def _parse_string_list_literal(raw: str) -> list[str] | None:
    """JSON or Python-literal list of strings, else None."""
    text = (raw or "").strip()
    if not (text.startswith("[") and text.endswith("]")):
        return None
    for loader in (json.loads, ast.literal_eval):
        try:
            parsed = loader(text)
        except (TypeError, ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if (
            isinstance(parsed, list)
            and parsed
            and all(isinstance(item, str) for item in parsed)
        ):
            return [str(item) for item in parsed]
    return None


def _basename_token(token: str) -> str:
    cleaned = token.replace("\\", "/").rstrip("/")
    return cleaned.rsplit("/", 1)[-1].lower()


def _script_from_shell_argv(items: list[str]) -> str | None:
    """bash/sh -c / -lc SCRIPT → SCRIPT. Ambiguous forms stay None."""
    if len(items) < 3:
        return None
    if _basename_token(items[0]) not in _SHELL_LIST_EXES:
        return None
    flag = items[1]
    if flag in ("-c", "-lc") or (
        flag.startswith("-")
        and not flag.startswith("--")
        and "c" in flag
        and "=" not in flag
        and len(flag) <= 4
    ):
        script = items[2].strip()
        return script or None
    if (
        len(items) >= 4
        and items[1] in ("-l", "--login")
        and items[2] == "-c"
    ):
        script = items[3].strip()
        return script or None
    return None


def _join_argv_command(items: list[str]) -> str:
    """Plain argv list → one string for cmd /c or sh -c."""
    if os.name == "nt":
        return list2cmdline(items)
    return shlex.join(items)


def _command_from_argv_items(items: list[str]) -> str:
    """bash/sh -lc SCRIPT → SCRIPT; else join argv for the host shell."""
    script = _script_from_shell_argv(items)
    if script is not None:
        return script
    return _join_argv_command(items)


def _coerce_list_literal_command(command: str) -> str:
    """Unwrap model stringified argv lists at the Speak boundary (FIG-05)."""
    items = _parse_string_list_literal(command)
    if items is None:
        return command
    return _command_from_argv_items(items)


def _as_command_string(raw: Any) -> str | None:
    """Model command value → canonical string (list argv or stringified list)."""
    if raw is None:
        return None
    if isinstance(raw, list):
        if not raw or not all(isinstance(item, str) for item in raw):
            return None
        return _command_from_argv_items([str(item) for item in raw])
    text = str(raw).strip()
    if not text:
        return None
    return _coerce_list_literal_command(text)


def normalize_speak_invoke(
    action: str, args: Mapping[str, Any] | None
) -> tuple[str, dict[str, Any]]:
    """Coerce model arg aliases at the Speak/grant boundary (before validate).

    - shell.run / project.run: cmd|shell → command (canonical wins); drop alias keys
    - shell.run / project.run: stringified or real bash/sh -lc argv list → script
    - shell.run / project.run: plain argv list (e.g. ["echo","X"]) → joined command
    - browser.open + url → browser.navigate (open grant/handler has no url field)
    """
    key = (action or "").strip()
    payload = dict(args or {})
    if key in _COMMAND_ALIAS_ACTIONS:
        chosen = _as_command_string(payload.get("command"))
        if not chosen:
            for alias in _COMMAND_ALIAS_KEYS:
                chosen = _as_command_string(payload.get(alias))
                if chosen:
                    break
        for alias in _COMMAND_ALIAS_KEYS:
            payload.pop(alias, None)
        if chosen:
            payload["command"] = chosen
        return key, payload
    if key == "browser.open":
        url = str(payload.get("url") or "").strip()
        if url:
            # Open control cannot navigate (_parse_open → Open with no url).
            return "browser.navigate", payload
    return key, payload


def aliases_for_action(action: str) -> frozenset[str]:
    """Legacy iris.* seed ids + absorbed model name for one Control action."""
    key = (action or "").strip()
    found = {legacy for legacy, target in _LEGACY_TO_ACTION.items() if target == key}
    model = action_to_model_name(key)
    if model and model != key:
        found.add(model)
    return frozenset(found)


def iris_tool_contract_from_grant(
    grant: SpeakGrant,
    actions: ActionCatalogView | None = None,
) -> IrisToolContract:
    """Build IrisToolContract from SpeakGrant and optional ActionCatalogView."""
    risk = "low"
    confirm = False
    description = grant.summary or grant.action
    if actions is not None:
        spec = actions.spec(grant.action)
        if spec is not None:
            description = description or str(getattr(spec, "summary", "") or "")
            confirm = bool(getattr(spec, "confirm_required", False))
            risk = str(getattr(spec, "risk", None) or "low")
    schema = (
        dict(grant.parameters)
        if grant.parameters is not None
        else dict(EMPTY_OBJECT_SCHEMA)
    )
    surface_kind = grant.kind is ExecKind.SURFACE
    # Conservative: never assume parallel-safe; headless only for non-UI, non-confirm.
    headless = (not surface_kind) and (not confirm)
    return IrisToolContract(
        canonical_name=grant.action,
        control_action=grant.action,
        description=description,
        input_schema=schema,
        risk=risk,
        confirm_required=confirm,
        profiles=frozenset(),
        parallel_safe=False,
        headless_supported=headless,
        side_effects=surface_kind or confirm,
        aliases=aliases_for_action(grant.action),
    )


def _domain_of(action: str) -> str:
    if action in ("ping", "get_catalog", "get_state"):
        return "session"
    if "." in action:
        return action.split(".", 1)[0]
    return "session"


@dataclass(frozen=True)
class SpeakAllowlist:
    """Single hand-maintained product list. Catalog/engine names derive from this."""

    grants: tuple[SpeakGrant, ...]

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(g.action for g in self.grants))

    def grant(self, action: str) -> SpeakGrant | None:
        key = (action or "").strip()
        for g in self.grants:
            if g.action == key:
                return g
        return None


PHASE4_ALLOWLIST = SpeakAllowlist(
    grants=(
        SpeakGrant("ping", ExecKind.PURE, "Iris Agent alive check"),
        SpeakGrant("get_catalog", ExecKind.PURE, "List speak/control catalog projection"),
        SpeakGrant("get_state", ExecKind.SURFACE, "Current Iris UI/session state"),
        SpeakGrant("settings.get", ExecKind.SURFACE, "Get Ollama and Iris Agent version"),
        SpeakGrant("wiki.list_notes", ExecKind.PURE, "List Iris Wiki note paths"),
        SpeakGrant(
            "wiki.search",
            ExecKind.PURE,
            "Search Iris Wiki notes",
            _params(
                {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                required=["query"],
            ),
        ),
        SpeakGrant(
            "wiki.write_user_note",
            ExecKind.SURFACE,
            "Save markdown into Iris Wiki; title and content required",
            _params(
                {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "body": {"type": "string"},
                    "source_url": {"type": "string"},
                    "url": {"type": "string"},
                    "rel_path": {"type": "string"},
                    "path": {"type": "string"},
                    "open": {"type": "boolean"},
                },
                required=["title"],
                any_of=[{"required": ["content"]}, {"required": ["body"]}],
            ),
        ),
        SpeakGrant("email.list_accounts", ExecKind.PURE, "List email accounts"),
        SpeakGrant("calendar.list_events", ExecKind.PURE, "List calendar events"),
        SpeakGrant(
            "local.read_file",
            ExecKind.SURFACE,
            "Read an attached or absolute local text file within the configured read scope "
            "(optional start_line/end_line 1-based inclusive; max_bytes truncation)",
            _params(
                {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                    "max_bytes": {"type": "integer", "minimum": 1, "maximum": 1048576},
                },
                required=["path"],
            ),
        ),
        SpeakGrant(
            "local.search_files",
            ExecKind.SURFACE,
            "Search under one absolute root; mode=name matches paths, mode=content matches file text",
            _params(
                {
                    "root": {"type": "string"},
                    "query": {"type": "string"},
                    "mode": {"type": "string", "enum": ["name", "content"]},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                },
                required=["root", "query"],
            ),
        ),
        SpeakGrant(
            "ide.open_folder",
            ExecKind.SURFACE,
            "Open a folder in the IDE Companion",
            _params(
                {
                    "path": {"type": "string"},
                    "folder": {"type": "string"},
                    "new_window": {"type": "boolean"},
                },
            ),
        ),
        SpeakGrant(
            "project.open_similar",
            ExecKind.SURFACE,
            "Find and open a similar project folder",
            _params(
                {
                    "query": {"type": "string"},
                    "name": {"type": "string"},
                    "new_window": {"type": "boolean"},
                },
            ),
        ),
        SpeakGrant(
            "attachment.copy_to",
            ExecKind.SURFACE,
            "Copy an attached original to an absolute destination",
            _params(
                {
                    "attachment_id": {"type": "string"},
                    "destination": {"type": "string"},
                    "overwrite": {"type": "boolean", "default": False},
                },
                required=["attachment_id", "destination"],
            ),
        ),
        SpeakGrant(
            "attachment.move_to",
            ExecKind.SURFACE,
            "Move an attached original after explicit human confirmation",
            _params(
                {
                    "attachment_id": {"type": "string"},
                    "destination": {"type": "string"},
                    "overwrite": {"type": "boolean", "default": False},
                },
                required=["attachment_id", "destination"],
            ),
        ),
        SpeakGrant(
            "project.import_attachment",
            ExecKind.SURFACE,
            "Copy an attached original into the bound IDE workspace",
            _params(
                {
                    "attachment_id": {"type": "string"},
                    "rel_path": {"type": "string"},
                },
                required=["attachment_id", "rel_path"],
            ),
        ),
        SpeakGrant(
            "project.run",
            ExecKind.SURFACE,
            "Sync simple command in the bound IDE terminal (model name: terminal). "
            "Prefer this for short one-shot commands like echo — not process_manage. "
            "Required: command and/or file (rel_path) as a plain string "
            "(not a Python/JSON list literal, not an unnecessary bash -lc wrapper). "
            "Optional timeout_sec, open_browser, reveal_terminal. Home surface uses shell.run. "
            "For long-running or background jobs that need run_id, use process.manage. "
            "Session/workspace ACL come from Control context (not tool args).",
            _params(
                {
                    "command": {
                        "type": "string",
                        "description": "Plain sync simple command string (not bash -lc list literal)",
                    },
                    "file": {"type": "string"},
                    "rel_path": {"type": "string"},
                    "cwd": {"type": "string"},
                    "project_root": {"type": "string"},
                    "timeout_sec": {"type": "number", "minimum": 1},
                    "timeout_s": {"type": "number", "minimum": 1},
                    "open_browser": {"type": "boolean"},
                    "reveal_terminal": {"type": "boolean"},
                },
                any_of=[
                    {"required": ["command"]},
                    {"required": ["file"]},
                    {"required": ["rel_path"]},
                ],
            ),
        ),
        SpeakGrant(
            "process.manage",
            ExecKind.SURFACE,
            "Long-running or background Iris Execution Runtime Local Subprocess "
            "(headless; not a sandbox). Track with run_id (status|read_output|wait|cancel). "
            "Not for sync simple one-shot shell/echo — use terminal "
            "(shell.run on home, project.run in IDE Companion) instead. "
            "Required: action (start|list|status|read_output|wait|cancel). "
            "start: exactly one of argv (list of strings) XOR shell (string; command alias ok); "
            "returns run_id on success (never ok without a started process). "
            "run_id required for status|read_output|wait|cancel. "
            "write_stdin is not supported. "
            "ACL/list scoped by trusted Control ExecutionContext (not model session_id). "
            "start needs human confirm + cwd under trusted workspace/home.",
            _params(
                {
                    "action": {
                        "type": "string",
                        "enum": [
                            "list",
                            "status",
                            "read_output",
                            "wait",
                            "cancel",
                            "start",
                        ],
                    },
                    "run_id": {
                        "type": "string",
                        "description": "Background run id from start; required after start",
                    },
                    "argv": {"type": "array", "items": {"type": "string"}},
                    "shell": {"type": "string"},
                    "command": {"type": "string"},
                    "cwd": {"type": "string"},
                    "environment_id": {"type": "string"},
                    "env_id": {"type": "string"},
                    "stream": {"type": "string", "enum": ["stdout", "stderr"]},
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 0},
                    "timeout_s": {"type": "number", "minimum": 0},
                },
                required=["action"],
            ),
        ),
        SpeakGrant(
            "shell.run",
            ExecKind.SURFACE,
            "Sync simple home-surface shell command (model name: terminal; "
            "no console window; chat Iris Shell card). "
            "Prefer this for short one-shot commands like echo — not process_manage. "
            "Required: command as a plain string (Windows example: echo HELLO) — "
            "not a Python/JSON list literal and not an unnecessary bash -lc wrapper. "
            "Optional cwd under user home. Use project.run in IDE Companion. "
            "For long-running or background jobs that need run_id, use process.manage.",
            _params(
                {
                    "command": {
                        "type": "string",
                        "description": "Plain sync simple command string (not bash -lc list literal)",
                    },
                    "cwd": {"type": "string"},
                    "timeout_s": {"type": "number", "minimum": 1, "maximum": 300},
                },
                required=["command"],
            ),
        ),
        SpeakGrant(
            "chat.search_past",
            ExecKind.SURFACE,
            "Search prior chat conversations (not wiki notes)",
            _params(
                {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 3},
                },
                required=["query"],
            ),
        ),
        SpeakGrant("chat.new_session", ExecKind.SURFACE, "Start a new chat session"),
        SpeakGrant(
            "app.demo_ping",
            ExecKind.SURFACE,
            "Open the App Host demo (app_host_ping.html)",
        ),
        SpeakGrant(
            "app.directory_list",
            ExecKind.PURE,
            "List or search App Host directory apps",
            _params({"query": {"type": "string"}}),
        ),
        SpeakGrant(
            "note.export_pdf",
            ExecKind.SURFACE,
            "Create a verified PDF from content and/or source files.",
            _params(
                {
                    "content": {"type": "string", "description": "Text to write into the PDF."},
                    "sources": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional source file paths to append.",
                    },
                    "path": {
                        "type": "string",
                        "description": "Optional output .pdf path.",
                    },
                },
                any_of=[{"required": ["content"]}, {"required": ["sources"]}],
            ),
        ),
        SpeakGrant(
            "diagram.render",
            ExecKind.SURFACE,
            "Render typed JSON IR to an interactive diagram in the Iris chat column "
            "(kind=architecture|workflow|sequence|dataflow|lifecycle). "
            "Do not write standalone HTML diagram files.",
            _params(
                {
                    "kind": {
                        "type": "string",
                        "enum": [
                            "architecture",
                            "workflow",
                            "sequence",
                            "dataflow",
                            "lifecycle",
                        ],
                    },
                    "ir": {
                        "description": "Diagram IR object or JSON string for the chosen kind",
                    },
                    "title": {"type": "string"},
                },
                required=["kind", "ir"],
            ),
        ),
        SpeakGrant(
            "email.list_messages",
            ExecKind.SURFACE,
            "Fetch inbox summaries; optional since, today, limit, cached, refresh",
            _params(
                {
                    "since": {"type": "string"},
                    "today": {"type": "boolean"},
                    "limit": {"type": "integer", "minimum": 1},
                    "cached": {"type": "boolean"},
                    "refresh": {"type": "boolean"},
                    "account": {"type": "string"},
                },
            ),
        ),
        SpeakGrant(
            "email.read_message",
            ExecKind.SURFACE,
            "Read and open an email message; uid required",
            _params(
                {
                    "uid": {"type": "string"},
                    "id": {"type": "string"},
                    "account": {"type": "string"},
                },
                any_of=[{"required": ["uid"]}, {"required": ["id"]}],
            ),
        ),
        SpeakGrant(
            "extension.install_github",
            ExecKind.SURFACE,
            "Install a GitHub MCP or skill; url required, optional kind and scope",
            _params(
                {
                    "url": {"type": "string"},
                    "kind": {"type": "string"},
                    "scope": {"type": "string"},
                },
                required=["url"],
            ),
        ),
        SpeakGrant(
            "ide.debug",
            ExecKind.SURFACE,
            "Start an IDE debug session",
            _params(
                {
                    "config": {"type": "string"},
                    "name": {"type": "string"},
                    "path": {"type": "string"},
                },
            ),
        ),
        SpeakGrant(
            "ide.definition",
            ExecKind.SURFACE,
            "Find definition at the IDE cursor or path, line and column",
            _params(
                {
                    "path": {"type": "string"},
                    "line": {"type": "integer", "minimum": 1},
                    "column": {"type": "integer", "minimum": 1},
                    "symbol": {"type": "string"},
                },
            ),
        ),
        SpeakGrant(
            "ide.diagnostics",
            ExecKind.SURFACE,
            "Get IDE diagnostics; check reported before claiming clean",
        ),
        SpeakGrant(
            "ide.edit",
            ExecKind.SURFACE,
            "Edit the open IDE buffer. Supported op only: "
            "insert|replace_selection|replace_range|apply (not replace). "
            "text required; optional path/range.",
            _params(
                {
                    "op": {
                        "type": "string",
                        "enum": [
                            "insert",
                            "replace_selection",
                            "replace_range",
                            "apply",
                        ],
                        "description": "Supported ops only; bare replace is rejected",
                    },
                    "text": {"type": "string"},
                    "path": {"type": "string"},
                    "range": {"type": "object"},
                },
                required=["op", "text"],
            ),
        ),
        SpeakGrant("ide.enter_companion", ExecKind.SURFACE, "Enter IDE Companion"),
        SpeakGrant("ide.exit_companion", ExecKind.SURFACE, "Exit IDE Companion"),
        SpeakGrant(
            "ide.marketplace_install",
            ExecKind.SURFACE,
            "Install an Open VSX extension; publisher.name id required",
            _params(
                {"id": {"type": "string"}, "extension": {"type": "string"}},
                any_of=[{"required": ["id"]}, {"required": ["extension"]}],
            ),
        ),
        SpeakGrant(
            "ide.marketplace_search",
            ExecKind.SURFACE,
            "Search Open VSX extensions; query required",
            _params(
                {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1},
                },
                required=["query"],
            ),
        ),
        SpeakGrant(
            "ide.project_log",
            ExecKind.SURFACE,
            "Record an IDE project plan, decision, issue or progress",
            _params(
                {
                    "kind": {"type": "string"},
                    "text": {"type": "string"},
                    "message": {"type": "string"},
                },
            ),
        ),
        SpeakGrant(
            "ide.references",
            ExecKind.SURFACE,
            "Find references at the IDE cursor or path, line and column",
            _params(
                {
                    "path": {"type": "string"},
                    "line": {"type": "integer", "minimum": 1},
                    "column": {"type": "integer", "minimum": 1},
                    "symbol": {"type": "string"},
                },
            ),
        ),
        SpeakGrant(
            "ide.save",
            ExecKind.SURFACE,
            "Save the open IDE buffer; optional path or all=true",
            _params(
                {
                    "path": {"type": "string"},
                    "all": {"type": "boolean"},
                },
            ),
        ),
        SpeakGrant(
            "ide.symbols",
            ExecKind.SURFACE,
            "Get IDE document symbols; optional symbol filter and path",
            _params(
                {
                    "path": {"type": "string"},
                    "query": {"type": "string"},
                    "symbol": {"type": "string"},
                },
            ),
        ),
        SpeakGrant(
            "ide.task",
            ExecKind.SURFACE,
            "Run an IDE tasks.json task by name",
            _params(
                {"name": {"type": "string"}, "task": {"type": "string"}},
                any_of=[{"required": ["name"]}, {"required": ["task"]}],
            ),
        ),
        SpeakGrant("learning.list", ExecKind.SURFACE, "List learned computer-use workflows"),
        SpeakGrant(
            "learning.run",
            ExecKind.SURFACE,
            "Run a learned workflow; id and params from learning.list required",
            _params(
                {
                    "id": {"type": "string"},
                    "params": {"type": "object"},
                },
                required=["id"],
            ),
        ),
        SpeakGrant("learning.start", ExecKind.SURFACE, "Start demonstration recording"),
        SpeakGrant("learning.stop", ExecKind.SURFACE, "Stop demonstration recording"),
        SpeakGrant(
            "project.rename_file",
            ExecKind.SURFACE,
            "Rename a bound-project file; path and new_path required",
            _params(
                {
                    "path": {"type": "string"},
                    "rel_path": {"type": "string"},
                    "new_path": {"type": "string"},
                    "project_root": {"type": "string"},
                },
                required=["new_path"],
                any_of=[{"required": ["path"]}, {"required": ["rel_path"]}],
            ),
        ),
        SpeakGrant(
            "project.write_file",
            ExecKind.SURFACE,
            "Write a requested file in the bound IDE project; rel_path and content required",
            _params(
                {
                    "rel_path": {"type": "string"},
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "project_root": {"type": "string"},
                    "open": {"type": "boolean"},
                },
                required=["content"],
                any_of=[{"required": ["rel_path"]}, {"required": ["path"]}],
            ),
        ),
        SpeakGrant(
            "project.write_image_code",
            ExecKind.SURFACE,
            "Write code from an image; image path and rel_path required",
            _params(
                {
                    "image": {"type": "string"},
                    "path": {"type": "string"},
                    "rel_path": {"type": "string"},
                    "project_root": {"type": "string"},
                },
                required=["rel_path"],
                any_of=[{"required": ["image"]}, {"required": ["path"]}],
            ),
        ),
        SpeakGrant(
            "routine.create",
            ExecKind.SURFACE,
            "Create a routine; task must be the user's exact request, kind and schedule required",
            _params(
                {
                    "task": {"type": "string"},
                    "kind": {"type": "string"},
                    "schedule": {"type": "string"},
                    "name": {"type": "string"},
                },
                required=["task", "kind", "schedule"],
            ),
        ),
        SpeakGrant(
            "routine.delete",
            ExecKind.SURFACE,
            "Delete a routine by id or name",
            _params(
                {"id": {"type": "string"}, "name": {"type": "string"}},
                any_of=[{"required": ["id"]}, {"required": ["name"]}],
            ),
        ),
        SpeakGrant("routine.list", ExecKind.SURFACE, "List registered routines"),
        SpeakGrant(
            "routine.run",
            ExecKind.SURFACE,
            "Run a registered routine once",
            _params(
                {"id": {"type": "string"}, "name": {"type": "string"}},
                any_of=[{"required": ["id"]}, {"required": ["name"]}],
            ),
        ),
        SpeakGrant(
            "routine.update",
            ExecKind.SURFACE,
            "Update a routine by id or name; enabled=false pauses it",
            _params(
                {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "enabled": {"type": "boolean"},
                    "task": {"type": "string"},
                    "schedule": {"type": "string"},
                },
                any_of=[{"required": ["id"]}, {"required": ["name"]}],
            ),
        ),
        SpeakGrant("voice.mic_off", ExecKind.SURFACE, "Turn microphone listening off"),
        SpeakGrant("voice.mic_on", ExecKind.SURFACE, "Turn microphone listening on"),
        SpeakGrant("voice.toggle_mic", ExecKind.SURFACE, "Toggle microphone listening"),
        SpeakGrant(
            "wiki.import_content",
            ExecKind.SURFACE,
            "Import and summarize one PDF, URL or file into Iris Wiki; source required",
            _params(
                {
                    "source": {"type": "string"},
                    "path": {"type": "string"},
                    "url": {"type": "string"},
                    "attachment_id": {"type": "string"},
                    "title": {"type": "string"},
                    "rel_path": {"type": "string"},
                    "open": {"type": "boolean"},
                    "mode": {"type": "string"},
                },
                any_of=[
                    {"required": ["source"]},
                    {"required": ["path"]},
                    {"required": ["url"]},
                    {"required": ["attachment_id"]},
                ],
            ),
        ),
        SpeakGrant(
            "wiki.import_pages",
            ExecKind.SURFACE,
            "Import and summarize multiple pages into Iris Wiki; sources required",
            _params(
                {
                    "sources": {"type": "array", "items": {"type": "string"}},
                    "mode": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1},
                },
                required=["sources"],
            ),
        ),
        SpeakGrant("workspace.open_assistant", ExecKind.SURFACE, "Open the assistant home workspace"),
        SpeakGrant("workspace.open_calendar", ExecKind.SURFACE, "Open the calendar workspace"),
        SpeakGrant("workspace.open_email", ExecKind.SURFACE, "Open the email inbox workspace"),
        SpeakGrant("workspace.open_obsidian", ExecKind.SURFACE, "Open the Iris Wiki workspace"),
        SpeakGrant("browser.back", ExecKind.SURFACE, "Go back in the visible Iris browser"),
        SpeakGrant(
            "browser.click",
            ExecKind.SURFACE,
            "Click a browser element by snapshot ref",
            _params(
                {
                    "ref": {"type": "string"},
                    "target": {"type": "object"},
                    "source": {"type": "string"},
                },
                any_of=[{"required": ["ref"]}, {"required": ["target"]}],
            ),
        ),
        SpeakGrant(
            "browser.extract",
            ExecKind.SURFACE,
            "Extract visible page article or document text",
            _params(
                {
                    "scope": {"type": "string", "enum": ["article", "document"]},
                    "ref": {"type": "string"},
                    "max_chars": {"type": "integer", "minimum": 1},
                    "source": {"type": "string"},
                },
            ),
        ),
        SpeakGrant("browser.forward", ExecKind.SURFACE, "Go forward in the visible Iris browser"),
        SpeakGrant(
            "browser.media",
            ExecKind.SURFACE,
            "Play, pause or resume visible browser media",
            _params(
                {
                    "media": {"type": "string", "enum": ["play", "pause", "resume"]},
                    "op": {"type": "string", "enum": ["play", "pause", "resume"]},
                    "action": {"type": "string"},
                    "source": {"type": "string"},
                },
                any_of=[{"required": ["media"]}, {"required": ["op"]}],
            ),
        ),
        SpeakGrant(
            "browser.mini_player",
            ExecKind.SURFACE,
            "Toggle the visible browser mini player",
            _params(
                {"on": {"type": "boolean"}, "source": {"type": "string"}},
                required=["on"],
            ),
        ),
        SpeakGrant(
            "browser.navigate",
            ExecKind.SURFACE,
            "Navigate the visible Iris browser; url required",
            _params(
                {"url": {"type": "string"}, "source": {"type": "string"}},
                required=["url"],
            ),
        ),
        SpeakGrant("browser.open", ExecKind.SURFACE, "Open the Iris browser workspace"),
        SpeakGrant("browser.reload", ExecKind.SURFACE, "Reload the visible Iris browser page"),
        SpeakGrant(
            "browser.scroll",
            ExecKind.SURFACE,
            "Scroll the visible Iris browser page or a ref",
            _params(
                {
                    "page": {"type": "string", "enum": ["up", "down"]},
                    "dx": {"type": "integer"},
                    "dy": {"type": "integer"},
                    "delta_x": {"type": "integer"},
                    "delta_y": {"type": "integer"},
                    "ref": {"type": "string"},
                    "source": {"type": "string"},
                },
            ),
        ),
        SpeakGrant(
            "browser.search",
            ExecKind.SURFACE,
            "Search the web or YouTube in the visible Iris browser; query required",
            _params(
                {
                    "query": {"type": "string"},
                    "q": {"type": "string"},
                    "engine": {"type": "string"},
                    "play": {"type": "boolean"},
                    "autoplay": {"type": "boolean"},
                    "source": {"type": "string"},
                },
                any_of=[{"required": ["query"]}, {"required": ["q"]}],
            ),
        ),
        SpeakGrant(
            "browser.snapshot",
            ExecKind.SURFACE,
            "Read the visible Iris browser controls and refs",
        ),
        SpeakGrant(
            "browser.type",
            ExecKind.SURFACE,
            "Type into a browser element by ref; text required",
            _params(
                {
                    "ref": {"type": "string"},
                    "text": {"type": "string"},
                    "clear": {"type": "boolean"},
                    "target": {"type": "object"},
                    "source": {"type": "string"},
                },
                required=["ref", "text"],
            ),
        ),
        SpeakGrant(
            "web.run_search",
            ExecKind.SURFACE,
            "Search the web (Iris Control; model name web_search).",
            _params(
                {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                required=["query"],
            ),
        ),
        SpeakGrant(
            "web.run_extract",
            ExecKind.SURFACE,
            "Extract page text from URLs (Iris Control; model name web_extract).",
            _params(
                {
                    "urls": {"type": "array", "items": {"type": "string"}},
                    "format": {"type": "string"},
                    "char_limit": {"type": "integer", "minimum": 1},
                },
                required=["urls"],
            ),
        ),
        SpeakGrant(
            "calendar.add_event",
            ExecKind.SURFACE,
            "Add a calendar event; title and start_at required",
            _params(
                {
                    "title": {"type": "string"},
                    "start_at": {"type": "string"},
                    "end_at": {"type": "string"},
                    "all_day": {"type": "boolean"},
                    "remind_minutes": {"type": "integer"},
                },
                required=["title", "start_at"],
            ),
        ),
        SpeakGrant(
            "calendar.delete_event",
            ExecKind.SURFACE,
            "Delete a calendar event by id",
            _params({"id": {"type": "string"}}, required=["id"]),
        ),
        SpeakGrant(
            "calendar.refresh_holidays",
            ExecKind.SURFACE,
            "Refresh Korean public holidays",
        ),
        SpeakGrant(
            "calendar.select_day",
            ExecKind.SURFACE,
            "Select calendar day by date",
            _params(
                {
                    "date": {"type": "string"},
                    "day": {"type": "string"},
                },
                any_of=[{"required": ["date"]}, {"required": ["day"]}],
            ),
        ),
        SpeakGrant(
            "calendar.set_month",
            ExecKind.SURFACE,
            "Set calendar year and month",
            _params(
                {
                    "year": {"type": "integer", "minimum": 1970},
                    "month": {"type": "integer", "minimum": 1, "maximum": 12},
                },
                required=["year", "month"],
            ),
        ),
        SpeakGrant("calendar.status", ExecKind.SURFACE, "Get selected calendar day and events"),
        SpeakGrant("skill.list", ExecKind.SURFACE, "List installed IRIS skills"),
        SpeakGrant(
            "skill.view", ExecKind.SURFACE, "Read an installed skill and its relative text resources",
            _params({"name": {"type": "string"}, "resource": {"type": "string"}}, required=["name"]),
        ),
        SpeakGrant(
            "skill.manage", ExecKind.SURFACE, "Create, update, enable, disable, or archive a skill with user approval",
            _params({"operation": {"type": "string", "enum": ["create", "update", "enable", "disable", "remove"]},
                     "name": {"type": "string"}, "text": {"type": "string"}}, required=["operation", "name"]),
        ),
        SpeakGrant(
            "content.extract",
            ExecKind.SURFACE,
            "Read a chat attachment by attachment_id and optional relative_path, or an authorized file or URL. Optional page_from/page_to.",
            _params(
                {
                    "source": {"type": "string"},
                    "path": {"type": "string"},
                    "url": {"type": "string"},
                    "attachment_id": {"type": "string"},
                    "relative_path": {"type": "string"},
                    "page_from": {"type": "integer", "minimum": 1},
                    "page_to": {"type": "integer", "minimum": 1},
                    "ocr_language": {"type": "string", "enum": ["kor+eng", "kor", "eng"]},
                },
                additional=True,
            ),
        ),
        SpeakGrant(
            "vision.analyze_attachment", ExecKind.SURFACE,
            "Analyze an image attachment or one PDF page with the local vision model",
            _params({"attachment_id": {"type": "string"}, "relative_path": {"type": "string"},
                     "page": {"type": "integer", "minimum": 1}, "question": {"type": "string"}},
                    required=["attachment_id"]),
        ),
        SpeakGrant("email.open_compose", ExecKind.SURFACE, "Open the email compose screen"),
        SpeakGrant(
            "email.send",
            ExecKind.SURFACE,
            "Send email; to, subject and body required; human confirmation required",
            _params(
                {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "cc": {"type": "string"},
                    "bcc": {"type": "string"},
                    "account": {"type": "string"},
                },
                required=["to", "subject", "body"],
            ),
        ),
        SpeakGrant(
            "emulator.input_text",
            ExecKind.SURFACE,
            "Type ASCII text into the Iris Android emulator",
            _params({"text": {"type": "string"}}, required=["text"]),
        ),
        SpeakGrant(
            "emulator.install",
            ExecKind.SURFACE,
            "Install an APK by absolute apk path",
            _params(
                {"apk": {"type": "string"}, "path": {"type": "string"}},
                any_of=[{"required": ["apk"]}, {"required": ["path"]}],
            ),
        ),
        SpeakGrant(
            "emulator.key",
            ExecKind.SURFACE,
            "Press an Android emulator key",
            _params(
                {"key": {"type": "string"}, "keycode": {"type": "string"}},
                any_of=[{"required": ["key"]}, {"required": ["keycode"]}],
            ),
        ),
        SpeakGrant("emulator.kill", ExecKind.SURFACE, "Stop the Iris Android emulator"),
        SpeakGrant("emulator.launch", ExecKind.SURFACE, "Start the Iris Android emulator"),
        SpeakGrant(
            "emulator.logcat_tail",
            ExecKind.SURFACE,
            "Read the Android emulator logcat tail",
        ),
        SpeakGrant(
            "emulator.play_install",
            ExecKind.SURFACE,
            "Install an Android app through Play Store UI",
            _params(
                {
                    "query": {"type": "string"},
                    "package": {"type": "string"},
                    "name": {"type": "string"},
                },
            ),
        ),
        SpeakGrant(
            "emulator.screenshot",
            ExecKind.SURFACE,
            "Capture the Iris Android emulator screenshot",
        ),
        SpeakGrant(
            "emulator.start_app",
            ExecKind.SURFACE,
            "Start an installed Android app by package",
            _params({"package": {"type": "string"}}, required=["package"]),
        ),
        SpeakGrant("emulator.status", ExecKind.SURFACE, "Get Iris Android emulator status"),
        SpeakGrant(
            "emulator.swipe",
            ExecKind.SURFACE,
            "Swipe the Android emulator between coordinates",
            _params(
                {
                    "x1": {"type": "number"},
                    "y1": {"type": "number"},
                    "x2": {"type": "number"},
                    "y2": {"type": "number"},
                },
                required=["x1", "y1", "x2", "y2"],
            ),
        ),
        SpeakGrant(
            "emulator.tap",
            ExecKind.SURFACE,
            "Tap Android emulator coordinates",
            _params(
                {"x": {"type": "number"}, "y": {"type": "number"}},
                required=["x", "y"],
            ),
        ),
        SpeakGrant(
            "emulator.tap_text",
            ExecKind.SURFACE,
            "Tap visible text in the Android emulator",
            _params({"text": {"type": "string"}}, required=["text"]),
        ),
        SpeakGrant("emulator.ui_texts", ExecKind.SURFACE, "List visible Android emulator text"),
        SpeakGrant(
            "emulator.wait_ready",
            ExecKind.SURFACE,
            "Wait for the Android emulator to finish booting",
        ),
        SpeakGrant("learning.status", ExecKind.SURFACE, "Get demonstration recording status"),
        SpeakGrant(
            "project.create_scaffold",
            ExecKind.SURFACE,
            "Create and open a project folder; name and parent required",
            _params(
                {
                    "name": {"type": "string"},
                    "parent": {"type": "string"},
                    "template": {"type": "string"},
                    "new_window": {"type": "boolean"},
                },
                required=["name", "parent"],
            ),
        ),
        SpeakGrant("project.list_files", ExecKind.SURFACE, "List files in the bound IDE project"),
        SpeakGrant(
            "project.list_parents",
            ExecKind.SURFACE,
            "List permitted parent folders for new projects",
        ),
        SpeakGrant(
            "project.read_file",
            ExecKind.SURFACE,
            "Read a UTF-8 file relative to the bound IDE project (rel_path or path; "
            "optional start_line/end_line/max_bytes). For an attachment, use local_read_file.",
            _params(
                {
                    "rel_path": {"type": "string"},
                    "path": {"type": "string"},
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                    "max_bytes": {"type": "integer", "minimum": 1, "maximum": 1048576},
                },
                any_of=[{"required": ["rel_path"]}, {"required": ["path"]}],
            ),
        ),
        SpeakGrant(
            "project.apply_patch",
            ExecKind.SURFACE,
            "Apply a Hermes-style or unified-diff patch under the bound IDE project. "
            "Required: patch_text. Conflicts when expected context or disk fingerprint missing. "
            "Model name apply_patch (Hermes patch is an internal alias — not dual-exposed).",
            _params(
                {
                    "patch_text": {"type": "string"},
                    "patch": {"type": "string"},
                    "project_root": {"type": "string"},
                    "expected_sha256": {"type": "object"},
                    "expected_mtime_ns": {"type": "object"},
                },
                any_of=[{"required": ["patch_text"]}, {"required": ["patch"]}],
            ),
        ),
        SpeakGrant(
            "wiki.move_notes",
            ExecKind.SURFACE,
            "Move Wiki notes by sources and dest_folder",
            _params(
                {
                    "sources": {"type": "array", "items": {"type": "string"}},
                    "dest_folder": {"type": "string"},
                    "from": {"type": "string"},
                    "rel_path": {"type": "string"},
                },
                required=["dest_folder"],
            ),
        ),
        SpeakGrant(
            "wiki.open_note",
            ExecKind.SURFACE,
            "Open a Wiki note by rel_path",
            _params(
                {
                    "rel_path": {"type": "string"},
                    "path": {"type": "string"},
                },
                any_of=[{"required": ["rel_path"]}, {"required": ["path"]}],
            ),
        ),
        SpeakGrant("wiki.reload", ExecKind.SURFACE, "Reload the Iris Wiki workspace"),
        SpeakGrant(
            "workspace.open_mobile",
            ExecKind.SURFACE,
            "Open the Iris Android emulator workspace",
        ),
        SpeakGrant(
            "chat.exec_python",
            ExecKind.SURFACE,
            "Run Python for a chat plot and return chat_markdown",
            _params(
                {
                    "code": {"type": "string"},
                    "source": {"type": "string"},
                },
                any_of=[{"required": ["code"]}, {"required": ["source"]}],
            ),
        ),
        SpeakGrant(
            "content.dump_lab_scripts",
            ExecKind.SURFACE,
            "Create lab scripts from an attached lecture PDF",
            _params(
                {
                    "source": {"type": "string"},
                    "path": {"type": "string"},
                    "attachment_id": {"type": "string"},
                    "project_root": {"type": "string"},
                    "relative_path": {"type": "string"},
                    "out_dir": {"type": "string"},
                },
            ),
        ),
        SpeakGrant(
            "ide.open_file",
            ExecKind.SURFACE,
            "Open an existing file in the bound IDE workspace",
            _params(
                {
                    "path": {"type": "string"},
                    "rel_path": {"type": "string"},
                },
                any_of=[{"required": ["path"]}, {"required": ["rel_path"]}],
            ),
        ),
        SpeakGrant(
            "project.delete",
            ExecKind.SURFACE,
            "Delete a project folder or relative path after confirmation",
            _params(
                {
                    "path": {"type": "string"},
                    "rel_path": {"type": "string"},
                    "project_root": {"type": "string"},
                },
            ),
        ),
        SpeakGrant("voice.mic_status", ExecKind.SURFACE, "Read microphone listening status"),
    )
)

_BOUND_SURFACE: Any | None = None
_ENGINE_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")

SpeakSurface = Literal["home", "ide_companion", "gateway"]
HOME_ONLY_SPEAK_ACTIONS = frozenset({"shell.run"})
GATEWAY_SPEAK_ACTIONS = frozenset({"ping", "get_catalog"})
_SPEAK_SURFACE: SpeakSurface = "home"


def normalize_speak_surface(raw: object) -> SpeakSurface:
    value = str(raw or "").strip().lower()
    if value in {"ide_companion", "companion", "ide"}:
        return "ide_companion"
    if value == "gateway":
        return "gateway"
    return "home"


def set_speak_surface(surface: SpeakSurface | str) -> None:
    global _SPEAK_SURFACE
    _SPEAK_SURFACE = normalize_speak_surface(surface)


def current_speak_surface() -> SpeakSurface:
    from iris.system.execution_context import host_execution_context

    context = host_execution_context()
    if context is not None and context.surface in ("home", "ide_companion", "gateway"):
        return normalize_speak_surface(context.surface)
    return _SPEAK_SURFACE


def grants_for_surface(
    allowlist: SpeakAllowlist, surface: SpeakSurface | str
) -> tuple[SpeakGrant, ...]:
    surf = normalize_speak_surface(surface)
    if surf == "home":
        return allowlist.grants
    if surf == "gateway":
        return tuple(grant for grant in allowlist.grants if grant.action in GATEWAY_SPEAK_ACTIONS)
    return tuple(
        grant
        for grant in allowlist.grants
        if grant.action not in HOME_ONLY_SPEAK_ACTIONS
    )


def engine_tool_name(action: str) -> str:
    """Provider-visible name: absorbed Hermes alias, else underscored action id."""
    act = (action or "").strip()
    return action_to_model_name(act) or act.replace(".", "_")


def engine_tool_action(name: str) -> str:
    """Map a provider-visible function name back to its Control action id.

    Surface-routed absorbed names (``terminal``) use ``current_speak_surface()``.
    Sidecar install prefers ``resolve_action(name, surface)`` with the known surface.
    Internal aliases (``patch`` → ``apply_patch``) resolve without a second schema.
    """
    from iris.infrastructure.absorbed_tool_aliases import INTERNAL_ALIASES

    key = (name or "").strip()
    if key in model_names() or key in INTERNAL_ALIASES:
        resolved = resolve_action(key, current_speak_surface())
        if resolved:
            return resolved
    return next(
        (
            grant.action
            for grant in PHASE4_ALLOWLIST.grants
            if engine_tool_name(grant.action) == key
        ),
        key,
    )


def bind_live_control_surface(surface: Any | None) -> None:
    """Bind the GUI-owned surface so worker threads never enumerate Qt widgets."""
    global _BOUND_SURFACE
    _BOUND_SURFACE = surface


def engine_tool_schemas(
    surface: SpeakSurface | str | None = None,
) -> tuple[dict[str, Any], ...]:
    """OpenAI function bodies for engine-visible SpeakTools on one surface.

    Absorbed actions use Hermes-familiar names (``terminal``, ``write_file``, …).
    Surface-routed ``terminal`` emits only ``resolve_action('terminal', surface)``.
    """
    surf = (
        current_speak_surface()
        if surface is None
        else normalize_speak_surface(surface)
    )
    default_parameters = dict(EMPTY_OBJECT_SCHEMA)
    terminal_action = resolve_action("terminal", surf)
    ordered: dict[str, dict[str, Any]] = {}
    for grant in grants_for_surface(PHASE4_ALLOWLIST, surf):
        if action_to_model_name(grant.action) == "terminal":
            if grant.action != terminal_action:
                continue
        name = engine_tool_name(grant.action)
        if name in ordered:
            continue
        ordered[name] = {
            "name": name,
            "description": grant.summary or grant.action,
            "parameters": dict(grant.parameters or default_parameters),
        }
    schemas = tuple(ordered.values())
    names = [str(schema["name"]) for schema in schemas]
    if len(names) != len(set(names)) or not all(_ENGINE_TOOL_NAME_RE.fullmatch(n) for n in names):
        raise AssertionError("engine tool names must be unique provider-safe identifiers")
    return schemas


def engine_tool_bindings(
    surface: SpeakSurface | str | None = None,
) -> tuple[EngineToolBinding, ...]:
    """Trusted model-name/action bindings derived from the engine schema projection."""
    surf = (
        current_speak_surface()
        if surface is None
        else normalize_speak_surface(surface)
    )
    absorbed = model_names()
    rows: list[EngineToolBinding] = []
    for schema in engine_tool_schemas(surf):
        model_name = str(schema["name"])
        canonical_action = (
            resolve_action(model_name, surf)
            if model_name in absorbed
            else engine_tool_action(model_name)
        )
        if not canonical_action:
            raise AssertionError(f"engine tool has no canonical action: {model_name}")
        description = str(schema["description"])
        input_schema = dict(schema["parameters"])
        material = {
            "contract": "iris-native-tool-v1",
            "model_name": model_name,
            "canonical_action": canonical_action,
            "description": description,
            "input_schema": input_schema,
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                material,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        rows.append(
            EngineToolBinding(
                model_name=model_name,
                canonical_action=canonical_action,
                description=description,
                input_schema=input_schema,
                fingerprint=fingerprint,
            )
        )
    return tuple(rows)


def _live_control_surface() -> Any | None:
    if _BOUND_SURFACE is not None:
        return _BOUND_SURFACE
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        return None
    app = QApplication.instance()
    if app is None:
        return None
    for widget in app.topLevelWidgets():
        surface = getattr(widget, "_control_surface", None)
        if surface is not None:
            return surface
    return None


def _invoke_live_control(action: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """In-process Control invoke (no HTTP). None when Iris UI surface is absent."""
    surface = _live_control_surface()
    if surface is None:
        return None
    from iris.system.control_surface import call_registered

    return call_registered(surface, action, dict(args or {}), timeout=30.0)


class _LiveSurfaceInvoker:
    def invoke(self, action: str, args: dict[str, Any]) -> dict[str, Any] | None:
        return _invoke_live_control(action, args)


class _LiveActionCatalog:
    def spec(self, name: str) -> Any | None:
        surface = _live_control_surface()
        if surface is None:
            return None
        reg = getattr(surface, "registry", None)
        if reg is None:
            return None
        return reg.spec(name)

    def catalog(self) -> list[dict[str, Any]]:
        surface = _live_control_surface()
        if surface is None:
            return []
        reg = getattr(surface, "registry", None)
        if reg is None:
            return []
        return list(reg.catalog())


def _from_control(
    action: str,
    control_out: dict[str, Any],
    *,
    duration_ms: int | None = None,
) -> ToolResult:
    result = control_out.get("result")
    data = dict(result) if isinstance(result, dict) else {}
    data.setdefault("bridge", "none")
    call_id = control_out.get("call_id")
    call_id_s = str(call_id) if call_id is not None else None
    status_raw = control_out.get("status")
    status = str(status_raw) if status_raw is not None else None
    tool_name = engine_tool_name(action)
    if control_out.get("ok"):
        return ToolResult(
            ok=True,
            action=action,
            data=data,
            bridge="none",
            call_id=call_id_s,
            tool_name=tool_name,
            status=status or "success",
            duration_ms=duration_ms,
        )
    err = str(control_out.get("error") or "control invoke failed")
    error_code = control_out.get("error_code")
    if error_code is None:
        if status == "timeout":
            error_code = "timeout"
        elif status == "invalid":
            error_code = "invalid"
        else:
            error_code = "failed"
    return ToolResult(
        ok=False,
        action=action,
        data=data,
        error=err,
        bridge="none",
        call_id=call_id_s,
        tool_name=tool_name,
        status=status or "error",
        error_code=str(error_code),
        error_message=err,
        retryable=status == "timeout",
        duration_ms=duration_ms,
    )


def _requires_iris_ui(action: str) -> ToolResult:
    return ToolResult(
        ok=False,
        action=action,
        data={"bridge": "none"},
        error="requires_iris_ui",
        bridge="none",
    )


def _wrap_registry_handler(
    registry: Any, iris_name: str, action: str
) -> PureHandler:
    def handler(args: dict[str, Any]) -> ToolResult:
        out = registry.invoke(iris_name, args)
        data = out.get("data") if isinstance(out.get("data"), dict) else {}
        data = dict(data)
        bridge = str(data.get("bridge") or "none")
        if out.get("ok"):
            return ToolResult(ok=True, action=action, data=data, bridge=bridge)
        return ToolResult(
            ok=False,
            action=action,
            data=data,
            error=str(out.get("error") or "invoke failed"),
            bridge=bridge,
        )

    return handler


def _app_directory_list_handler(args: dict[str, Any]) -> ToolResult:
    query = str((args or {}).get("query") or "").strip()
    directory = AppDirectory()
    entries = directory.search(query) if query else directory.list()
    return ToolResult(
        ok=True,
        action="app.directory_list",
        data={"apps": entries_as_dicts(entries), "query": query, "bridge": "none"},
        bridge="none",
    )


class SpeakTools:
    """Product speak surface: catalog + invoke over PHASE4 allowlist."""

    def __init__(
        self,
        allowlist: SpeakAllowlist,
        *,
        surface: SurfaceInvoker,
        actions: ActionCatalogView | None = None,
        pure_handlers: Mapping[str, PureHandler] | None = None,
    ) -> None:
        self._allowlist = allowlist
        self._surface = surface
        self._actions = actions
        self._pure = dict(pure_handlers or {})

    def catalog(self) -> list[SpeakToolRow]:
        rows: list[SpeakToolRow] = []
        for grant in grants_for_surface(self._allowlist, current_speak_surface()):
            spec = self._actions.spec(grant.action) if self._actions is not None else None
            summary = grant.summary
            confirm = False
            risk = "low"
            if spec is not None:
                summary = summary or str(getattr(spec, "summary", "") or "")
                confirm = bool(getattr(spec, "confirm_required", False))
                risk = str(getattr(spec, "risk", None) or "low")
            elif self._actions is not None and grant.kind is ExecKind.SURFACE:
                # SURFACE with no ActionSpec yet — still list from allowlist grant.
                pass
            rows.append(
                SpeakToolRow(
                    name=grant.action,
                    summary=summary,
                    domain=_domain_of(grant.action),
                    needs_ui=grant.kind is ExecKind.SURFACE,
                    confirm_required=confirm,
                    risk=risk,
                )
            )
        rows.sort(key=lambda r: r.name)
        return rows

    def engine_names(self) -> tuple[str, ...]:
        return self._allowlist.names()

    def invoke(self, action: str, args: dict[str, Any] | None = None) -> ToolResult:
        key = resolve_legacy_name((action or "").strip())
        key, payload = normalize_speak_invoke(key, args)
        grant = self._allowlist.grant(key)
        if grant is None:
            return ToolResult(
                ok=False,
                action=key or (action or ""),
                data={},
                error=f"not_allowed: {key or action}",
            )
        surface = current_speak_surface()
        if (surface != "home" and key in HOME_ONLY_SPEAK_ACTIONS) or (
            surface == "gateway" and key not in GATEWAY_SPEAK_ACTIONS
        ):
            return ToolResult(
                ok=False,
                action=key,
                data={},
                error=f"not_allowed: {key}",
            )
        try:
            # Bare parameters=None → EMPTY (zero-arg). Arg tools must declare schemas.
            schema = (
                grant.parameters
                if grant.parameters is not None
                else EMPTY_OBJECT_SCHEMA
            )
            validate_tool_arguments(schema, payload)
        except (TypeError, ValueError) as exc:
            return ToolResult(
                ok=False,
                action=key,
                data={},
                error=str(exc) or "invalid_arguments",
                tool_name=engine_tool_name(key),
                status="error",
                error_code="invalid_arguments",
                error_message=str(exc) or "invalid_arguments",
                retryable=False,
            )
        if grant.kind is ExecKind.PURE:
            if key == "get_catalog":
                return ToolResult(
                    ok=True,
                    action=key,
                    data={
                        "tools": [
                            {
                                "name": r.name,
                                "summary": r.summary,
                                "domain": r.domain,
                                "needs_ui": r.needs_ui,
                                "confirm_required": r.confirm_required,
                                "risk": r.risk,
                            }
                            for r in self.catalog()
                        ],
                        "bridge": "none",
                    },
                    bridge="none",
                )
            handler = self._pure.get(key)
            if handler is None:
                return ToolResult(
                    ok=False,
                    action=key,
                    data={},
                    error=f"pure handler missing: {key}",
                )
            try:
                return handler(payload)
            except Exception as exc:  # noqa: BLE001 — speak boundary
                return ToolResult(
                    ok=False,
                    action=key,
                    data={},
                    error=str(exc) or type(exc).__name__,
                )

        t0 = time.monotonic()
        control_out = self._surface.invoke(key, payload)
        duration_ms = int((time.monotonic() - t0) * 1000)
        if control_out is None:
            return _requires_iris_ui(key)
        if not isinstance(control_out, dict):
            return ToolResult(
                ok=False,
                action=key,
                data={},
                error="invalid control result",
                tool_name=engine_tool_name(key),
                status="error",
                error_code="invalid",
                error_message="invalid control result",
                duration_ms=duration_ms,
            )
        return _from_control(key, control_out, duration_ms=duration_ms)


def default_speak_tools(*, registry: Any | None = None) -> SpeakTools:
    from iris.infrastructure.agent_tool_registry import default_registry

    reg = registry if registry is not None else default_registry()
    pure: dict[str, PureHandler] = {
        "ping": _wrap_registry_handler(reg, "iris.tools.ping", "ping"),
        "wiki.list_notes": _wrap_registry_handler(
            reg, "iris.wiki.list_notes", "wiki.list_notes"
        ),
        "wiki.search": _wrap_registry_handler(reg, "iris.wiki.search", "wiki.search"),
        "email.list_accounts": _wrap_registry_handler(
            reg, "iris.mail.list_accounts", "email.list_accounts"
        ),
        "calendar.list_events": _wrap_registry_handler(
            reg, "iris.calendar.list_events", "calendar.list_events"
        ),
        "app.directory_list": _app_directory_list_handler,
    }
    return SpeakTools(
        PHASE4_ALLOWLIST,
        surface=_LiveSurfaceInvoker(),
        actions=_LiveActionCatalog(),
        pure_handlers=pure,
    )


def assert_engine_tools_match_allowlist(
    tools: tuple[str, ...] | None = None,
    allowlist: SpeakAllowlist = PHASE4_ALLOWLIST,
) -> None:
    """Boot check. Engine tool tuple must equal allowlist.names() — no MCP triple."""
    expected = allowlist.names()
    if tools is None:
        tools = expected
    mcp_triple = ("iris_get_state", "iris_get_catalog", "iris_invoke")
    if tuple(tools) == mcp_triple:
        raise AssertionError("engine tools must not be the MCP triple")
    if tuple(sorted(tools)) != expected:
        raise AssertionError(
            f"engine tools must match allowlist names: got {tuple(tools)!r} "
            f"expected {expected!r}"
        )
