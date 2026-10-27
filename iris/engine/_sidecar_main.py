"""Hermes-interpreter sidecar entry.

Agent-readable:
- Owns: logging reservation and the GuiPython refuse check.
- Does not: import run_agent, hermes_cli, iris, or PyQt6.
- Talks to: the host through one NDJSON hello on stdout.
- Extend via: later units add the AIAgent loop after this hello.
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


def main() -> None:
    _configure_logging()
    if _is_gui_python():
        logging.warning("refusing to start under GuiPython")
        raise SystemExit(2)
    print(json.dumps({"t": "hello", "ok": True}), flush=True)


if __name__ == "__main__":
    main()
