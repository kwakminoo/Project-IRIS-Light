"""Hermes stdio MCP bridge → Iris Control Surface HTTP.

Tools: iris_get_state, iris_get_catalog, iris_invoke
ponytail: NDJSON JSON-RPC (MCP Python SDK stdio). No MCP SDK dependency.
천장: Iris가 꺼져 있으면 도구가 명확한 에러를 반환 (조용히 실패 금지).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _state_dir() -> Path:
    return Path.home() / ".iris-light"


def _load_endpoint() -> tuple[str, str]:
    host = (os.environ.get("IRIS_CONTROL_HOST") or "").strip()
    port = (os.environ.get("IRIS_CONTROL_PORT") or "").strip()
    token = (os.environ.get("IRIS_CONTROL_TOKEN") or "").strip()
    base = (os.environ.get("IRIS_CONTROL_URL") or "").strip().rstrip("/")

    if not host:
        hp = _state_dir() / "control_host"
        if hp.is_file():
            host = hp.read_text(encoding="utf-8").strip()
    if not port:
        pp = _state_dir() / "control_port"
        if pp.is_file():
            port = pp.read_text(encoding="utf-8").strip()
    if not token:
        tp = _state_dir() / "control_token"
        if tp.is_file():
            token = tp.read_text(encoding="utf-8").strip()

    if not base:
        host = host or "127.0.0.1"
        port = port or "8765"
        base = f"http://{host}:{port}"
    return base, token


def _http(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    base, token = _load_endpoint()
    if not token:
        return {
            "ok": False,
            "action": "http",
            "result": {},
            "error": "IRIS_CONTROL_TOKEN missing (set env or ~/.iris-light/control_token). Is Iris running?",
        }
    url = f"{base}{path}"
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8")
            return json.loads(raw)
        except Exception:
            return {
                "ok": False,
                "action": "http",
                "result": {},
                "error": f"HTTP {exc.code}: Iris control rejected request",
            }
    except urllib.error.URLError as exc:
        return {
            "ok": False,
            "action": "http",
            "result": {},
            "error": f"Iris control unreachable at {base} ({exc.reason}). Start Iris Light first.",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "action": "http",
            "result": {},
            "error": f"Iris control error: {exc}",
        }
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "action": "http", "result": {}, "error": "invalid JSON from Iris"}
    return parsed if isinstance(parsed, dict) else {"ok": False, "error": "bad response"}


TOOLS = [
    {
        "name": "iris_get_state",
        "description": (
            "Get Iris Light UI session state: ui_mode (normal|ide_companion), workspace_mode "
            "(assistant|obsidian|email|calendar), preferred_ide, project_root, hermes_online, model, "
            "email accounts summary. Use before IDE Companion / coding start / workspace switches."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "iris_get_catalog",
        "description": (
            "List every Iris control action name with summary and risk. "
            "Call this to discover actions for iris_invoke "
            "(ide.enter_companion, workspace.open_email, workspace.open_calendar, "
            "calendar.add_event, calendar.list_events, profile.set, email.send, …)."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "iris_invoke",
        "description": (
            "Invoke an Iris Light UI control action by name (same handlers as sidebar icons / settings). "
            "NOT for opening folders via terminal — use Iris actions so Companion tiling works. "
            "High-risk actions require args.confirm=true (email.send, email.add_account, "
            "email.remove_account, chat.clear_history). "
            "Examples: action=project.open_similar args={query}; action=ide.open_folder args={path}; "
            "action=ide.open_file args={path|rel_path}; "
            "action=project.write_file args={rel_path,content,open,stream}; "
            "action=project.run args={file|command}; "
            "action=ide.enter_companion; action=ide.exit_companion; "
            "action=workspace.open_email; action=workspace.open_calendar; "
            "action=calendar.add_event args={title,start_at,note,place}; "
            "action=calendar.list_events; action=calendar.select_day args={date}; "
            "action=ide.set_project_root args={path}; "
            "action=profile.set args={project_root, preferred_ide, project_parents}."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action name from iris_get_catalog (e.g. ide.enter_companion)",
                },
                "args": {
                    "type": "object",
                    "description": "Action arguments object (optional)",
                    "additionalProperties": True,
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
]


def _tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    is_err = not bool(payload.get("ok", True)) and payload.get("error")
    return {
        "content": [{"type": "text", "text": text}],
        "isError": bool(is_err),
    }


def _handle_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "iris_get_state":
        return _tool_result(_http("GET", "/v1/state"))
    if name == "iris_get_catalog":
        return _tool_result(_http("GET", "/v1/catalog"))
    if name == "iris_invoke":
        action = str(arguments.get("action") or "").strip()
        args = arguments.get("args")
        if not isinstance(args, dict):
            args = {}
        return _tool_result(_http("POST", "/v1/invoke", {"action": action, "args": args}))
    return _tool_result({"ok": False, "action": name, "result": {}, "error": f"unknown tool: {name}"})


# MCP Python SDK (Hermes) speaks newline-delimited JSON on stdio — not Content-Length.
_SUPPORTED_PROTOCOL_VERSIONS = frozenset(
    {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}
)
_DEFAULT_PROTOCOL_VERSION = "2025-11-25"


def _read_message() -> dict[str, Any] | None:
    """MCP stdio framing: one JSON-RPC object per line (NDJSON)."""
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        stripped = line.strip()
        if not stripped:
            continue
        # Legacy LSP-style Content-Length (older probes only)
        if stripped.lower().startswith(b"content-length:"):
            try:
                length = int(stripped.split(b":", 1)[1].strip())
            except ValueError:
                return None
            while True:
                h = sys.stdin.buffer.readline()
                if not h or h in (b"\r\n", b"\n"):
                    break
            body = sys.stdin.buffer.read(length)
            if not body:
                return None
            try:
                msg = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError:
                return None
            return msg if isinstance(msg, dict) else None
        try:
            msg = json.loads(stripped.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        return msg if isinstance(msg, dict) else None


def _write_message(msg: dict[str, Any]) -> None:
    # stdout must stay clean JSON lines — never log here
    # Windows console default (cp949) can't encode tool description dashes; write UTF-8 bytes.
    raw = (json.dumps(msg, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


def _respond(req_id: Any, result: Any = None, error: dict[str, Any] | None = None) -> None:
    if error is not None:
        _write_message({"jsonrpc": "2.0", "id": req_id, "error": error})
    else:
        _write_message({"jsonrpc": "2.0", "id": req_id, "result": result})


def _negotiate_protocol(params: dict[str, Any]) -> str:
    requested = str(params.get("protocolVersion") or "").strip()
    if requested in _SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    return _DEFAULT_PROTOCOL_VERSION


def main() -> int:
    while True:
        msg = _read_message()
        if msg is None:
            break
        method = str(msg.get("method") or "")
        req_id = msg.get("id")
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}

        # notifications (no id) — e.g. notifications/initialized
        if req_id is None:
            continue

        if method == "initialize":
            _respond(
                req_id,
                {
                    "protocolVersion": _negotiate_protocol(params),
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "iris-control", "version": "0.1.1"},
                },
            )
            continue
        if method == "tools/list":
            _respond(req_id, {"tools": TOOLS})
            continue
        if method == "tools/call":
            name = str(params.get("name") or "")
            arguments = params.get("arguments")
            if not isinstance(arguments, dict):
                arguments = {}
            _respond(req_id, _handle_tool(name, arguments))
            continue
        if method == "ping":
            _respond(req_id, {})
            continue
        _respond(req_id, error={"code": -32601, "message": f"Method not found: {method}"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
