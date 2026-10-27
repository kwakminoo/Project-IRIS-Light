"""Hermes-interpreter sidecar entry.

Agent-readable:
- Owns: logging reservation, the GuiPython refuse check, and the stdin loop.
- Does not: import run_agent, hermes_cli, iris, or PyQt6.
- Talks to: the host through NDJSON on stdout. Inbound commands are turn and stop.
- Extend via: later units replace the turn fail with the AIAgent loop.
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


def _handle_turn(_raw: dict) -> bool:
    _fail("unknown", "agent loop is not wired")
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
