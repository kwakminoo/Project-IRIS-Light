"""Hermes-interpreter sidecar entry.

Agent-readable:
- Owns: logging reservation, the GuiPython refuse check, the stdin loop, and one AIAgent turn.
- Does not: import iris, PyQt6, or run_agent before logging. Does not bind :8642.
- Talks to: the host through NDJSON on stdout. Inbound commands are turn and stop.
- Extend via: cancel interrupt and tool callbacks. Persist stays off.
"""

from __future__ import annotations

import os
import sys

# File-path spawn puts this directory on sys.path[0]. iris/engine/types.py then
# shadows the stdlib types module. Strip it before any other import.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path = [
    part
    for part in sys.path
    if os.path.normcase(os.path.abspath(part or ".")) != os.path.normcase(_SCRIPT_DIR)
]

import importlib
import inspect
import json
import logging
from pathlib import Path


def _configure_logging() -> None:
    kwargs = {
        "level": logging.INFO,
        "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        "force": True,
    }
    log_path = os.environ.get("IRIS_ENGINE_LOG", "").strip()
    if log_path:
        logging.basicConfig(filename=log_path, **kwargs)
        return
    logging.basicConfig(stream=sys.stderr, **kwargs)


def _is_gui_python() -> bool:
    if "--refuse-gui" in sys.argv:
        return True
    marked = os.environ.get("IRIS_ENGINE_GUI_PYTHON", "").strip()
    if not marked:
        return False
    return Path(sys.executable).resolve() == Path(marked).resolve()


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _fail(code: str, detail: str) -> None:
    _emit({"t": "fail", "code": code, "detail": detail})


_AGENT_CLS: type | None = None
_AGENT_MISSING = False


def _import_agent_class() -> type:
    name = os.environ.get("IRIS_ENGINE_AGENT_MODULE", "").strip() or "run_agent"
    module = importlib.import_module(name)
    cls = getattr(module, "AIAgent", None)
    if cls is None:
        raise ImportError("AIAgent is missing")
    return cls


def _agent_class() -> type | None:
    global _AGENT_CLS, _AGENT_MISSING
    if _AGENT_MISSING:
        return None
    if _AGENT_CLS is not None:
        return _AGENT_CLS
    try:
        _AGENT_CLS = _import_agent_class()
        return _AGENT_CLS
    except ImportError:
        _AGENT_MISSING = True
        return None


def _init_kwargs(cls: type, wanted: dict) -> dict:
    try:
        params = inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):
        return wanted
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return wanted
    return {key: value for key, value in wanted.items() if key in params}


def _split_for_agent(raw: object) -> tuple[list, str] | None:
    if not isinstance(raw, list) or not raw:
        _fail("no_user_utterance", "last message must be a user utterance")
        return None
    last = raw[-1]
    if not isinstance(last, dict) or last.get("role") != "user":
        _fail("no_user_utterance", "last message must be a user utterance")
        return None
    content = last.get("content")
    user = "" if content is None else str(content)
    history = [row for row in raw[:-1] if isinstance(row, dict)]
    return history, user


def _on_delta(text: object) -> None:
    if text is None:
        return
    chunk = str(text)
    if not chunk:
        return
    _emit({"t": "delta", "text": chunk})


def _on_tool(label: object = None, *args: object, **kwargs: object) -> None:
    text = label
    if text is None and args:
        text = args[0]
    if text is None:
        text = kwargs.get("label", "")
    _emit({"t": "tool", "label": "" if text is None else str(text)})


def _done_text(result: object) -> str:
    if isinstance(result, dict):
        return str(result.get("final_response") or "")
    if result is None:
        return ""
    return str(result)


def _run_agent_turn(cls: type, history: list, user: str, raw: dict) -> None:
    wanted = {
        "skip_memory": True,
        "session_db": None,
        "load_soul_identity": True,
        "stream_delta_callback": _on_delta,
        "tool_progress_callback": _on_tool,
    }
    model = raw.get("model")
    if isinstance(model, str) and model:
        wanted["model"] = model
    provider = raw.get("provider")
    if isinstance(provider, str) and provider:
        wanted["provider"] = provider
    base_url = raw.get("base_url")
    if isinstance(base_url, str) and base_url:
        wanted["base_url"] = base_url
    api_key = raw.get("api_key")
    if isinstance(api_key, str) and api_key:
        wanted["api_key"] = api_key
    agent = cls(**_init_kwargs(cls, wanted))
    agent._persist_disabled = True
    result = agent.run_conversation(
        user_message=user,
        conversation_history=history,
    )
    _emit({"t": "done", "text": _done_text(result)})


def _handle_turn(raw: dict) -> bool:
    cls = _agent_class()
    if cls is None:
        _fail("unknown", "agent loop is not wired")
        return True
    split = _split_for_agent(raw.get("messages"))
    if split is None:
        return True
    history, user = split
    try:
        _run_agent_turn(cls, history, user, raw)
    except Exception as exc:
        _fail("unknown", str(exc) or "agent loop failed")
    return True


def _handle_stop(_raw: dict) -> bool:
    return False


_COMMANDS = {
    "turn": _handle_turn,
    "stop": _handle_stop,
}


def _handle_line(line: str) -> bool:
    text = line.strip()
    if not text:
        return True
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        _fail("protocol", "command must be JSON")
        return True
    if not isinstance(raw, dict):
        _fail("protocol", "command must be a dict")
        return True
    kind = raw.get("t")
    handler = _COMMANDS.get(kind) if isinstance(kind, str) else None
    if handler is None:
        _fail("protocol", f"unknown command: {kind!r}")
        return True
    return handler(raw)


def _serve() -> None:
    while True:
        line = sys.stdin.readline()
        if line == "":
            return
        if not _handle_line(line):
            return


def main() -> None:
    _configure_logging()
    if _is_gui_python():
        logging.warning("refusing to start under GuiPython")
        raise SystemExit(2)
    print(json.dumps({"t": "hello", "ok": True}), flush=True)
    _serve()


if __name__ == "__main__":
    main()
