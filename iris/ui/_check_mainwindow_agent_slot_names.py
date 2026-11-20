"""MainWindow/settings private product slots must be agent_*, not hermes_*.

AST-scrapes ``main_window.py`` and ``settings_dialog.py``. Fails if any
``def _on_agent_``, ``def _agent_``, ``def _section_agent_``,
``def _build_agent_``, ``def _run_agent_``, or ``def _sync_agent_``
remains (comments allowed). Asserts mapped ``_on_agent_*`` / ``_agent_*``
and section/sync helper defs exist.

Run:
  .venv\\Scripts\\python.exe -m iris.ui._check_mainwindow_agent_slot_names
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_UI = Path(__file__).resolve().parent
_MAIN = _UI / "window" / "main_window.py"
_SETTINGS = _UI / "settings" / "settings_dialog.py"

_FORBIDDEN_PREFIXES = (
    "_on_agent_",
    "_agent_",
    "_section_agent_",
    "_build_agent_",
    "_run_agent_",
    "_sync_agent_",
)

_REQUIRED_DEFS = (
    "_on_agent_gateway_notice",
    "_on_agent_health",
    "_on_agent_health_failed",
    "_on_agent_model_synced",
    "_on_agent_model_sync_failed",
    "_agent_fallback_attempts",
    "_on_agent_tool_progress_for_turn",
    "_on_agent_tool_progress",
    "_on_agent_app_ui_for_turn",
    "_on_agent_app_ui",
    "_on_agent_reasoning_for_turn",
    "_on_agent_reasoning",
    "_on_agent_control_sync_done",
    "_section_agent_login_warm",
    "_section_agent_control",
    "_build_agent_control_box",
    "_run_agent_control_sync",
    "_sync_agent_model",
    "_sync_agent_login_warm",
)


def _function_defs(path: Path) -> list[tuple[str, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append((node.name, getattr(node, "lineno", 0)))
    return out


def find_forbidden_agent_defs(path: Path) -> list[str]:
    hits: list[str] = []
    for name, lineno in _function_defs(path):
        if any(name.startswith(prefix) for prefix in _FORBIDDEN_PREFIXES):
            rel = path.relative_to(_UI.parent.parent)
            hits.append(f"{rel}:{lineno}:def {name}")
    return hits


def find_missing_agent_defs(paths: list[Path]) -> list[str]:
    found: set[str] = set()
    for path in paths:
        for name, _ in _function_defs(path):
            found.add(name)
    return [name for name in _REQUIRED_DEFS if name not in found]


def main() -> int:
    paths = [_MAIN, _SETTINGS]
    missing_files = [p for p in paths if not p.is_file()]
    if missing_files:
        for p in missing_files:
            print(f"FAIL missing file: {p}", file=sys.stderr)
        return 1

    forbidden: list[str] = []
    for path in paths:
        forbidden.extend(find_forbidden_agent_defs(path))
    missing = find_missing_agent_defs(paths)

    ok = True
    if forbidden:
        ok = False
        print("FAIL leftover hermes product slot defs:", file=sys.stderr)
        for hit in forbidden:
            print(f"  {hit}", file=sys.stderr)
    if missing:
        ok = False
        print("FAIL missing required agent_* slot defs:", file=sys.stderr)
        for name in missing:
            print(f"  {name}", file=sys.stderr)
    if ok:
        print("ok: MainWindow/settings product slots use agent_* names")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
