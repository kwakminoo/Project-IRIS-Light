"""Phase 5 Prove 0: agent-loop stand-in on a worker thread, no QWidget.

Fails if the agent path (``agent_runtime`` stand-in) imports UI widgets.
Does not start Merge and does not remove the :8642 product path.
"""

from __future__ import annotations

import ast
import inspect
import sys
import threading
from pathlib import Path

from iris.infrastructure import agent_runtime as ar
from iris.infrastructure.agent_runtime import (
    AgentLoopStandinResult,
    load_pinned_sha,
    run_agent_loop_standin,
    vendor_runtime_root,
)


_FORBIDDEN_WIDGET_NAMES = frozenset(
    {
        "QWidget",
        "QMainWindow",
        "QDialog",
        "QApplication",
        "QtWidgets",
    }
)


def _ast_imports_forbidden_widgets(source: str) -> list[str]:
    tree = ast.parse(source)
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "QtWidgets" in alias.name or alias.name.endswith(".QtWidgets"):
                    hits.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if "QtWidgets" in mod:
                hits.append(mod)
            for alias in node.names:
                if alias.name in _FORBIDDEN_WIDGET_NAMES:
                    hits.append(f"{mod}.{alias.name}")
        elif isinstance(node, ast.Name) and node.id in _FORBIDDEN_WIDGET_NAMES:
            hits.append(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_WIDGET_NAMES:
            hits.append(node.attr)
    return hits


def _check_agent_path_source_has_no_widgets() -> None:
    src = Path(ar.__file__).read_text(encoding="utf-8")
    hits = _ast_imports_forbidden_widgets(src)
    assert not hits, f"agent_runtime must not reference UI widgets: {hits}"
    # Function body only — docstrings may name the forbid list for humans.
    body = ast.parse(inspect.getsource(run_agent_loop_standin))
    assert not _ast_imports_forbidden_widgets(ast.unparse(body))
    standin_src = inspect.getsource(run_agent_loop_standin)
    assert "8642" not in standin_src


def _check_standin_on_worker_thread() -> AgentLoopStandinResult:
    pin = load_pinned_sha()
    assert pin == (vendor_runtime_root() / "PIN").read_text(encoding="utf-8").strip().split()[0]

    widgets_before = "PyQt6.QtWidgets" in sys.modules
    box: dict[str, AgentLoopStandinResult | BaseException | None] = {"result": None}

    def _target() -> None:
        try:
            box["result"] = run_agent_loop_standin(prompt="phase5-prove0")
        except BaseException as exc:  # noqa: BLE001 — surface to joiner
            box["result"] = exc

    worker = threading.Thread(target=_target, name="iris-agent-phase5-prove0", daemon=True)
    worker.start()
    worker.join(timeout=30.0)
    assert not worker.is_alive(), "stand-in worker thread did not finish"
    out = box["result"]
    assert isinstance(out, AgentLoopStandinResult), f"stand-in failed: {out!r}"
    assert out.ok
    assert out.mode == "stub"
    assert out.pin == pin
    assert out.home == ar.iris_agent_home()
    assert out.thread_name == "iris-agent-phase5-prove0"
    if not widgets_before:
        assert "PyQt6.QtWidgets" not in sys.modules, (
            "run_agent_loop_standin imported PyQt6.QtWidgets"
        )
    return out


def _check_qthread_worker_contract() -> None:
    from iris.ui.workers import hermes_workers as hw

    assert hasattr(hw, "IrisAgentLoopStandinWorker")
    run_src = inspect.getsource(hw.IrisAgentLoopStandinWorker.run)
    assert "run_agent_loop_standin" in run_src
    assert "QWidget" not in run_src
    assert "QtWidgets" not in run_src
    # Product speak still owns :8642 via HermesChatWorker — Prove 0 must not delete it.
    chat_src = inspect.getsource(hw.HermesChatWorker)
    assert "8642" in chat_src or "ensure_hermes_gateway" in chat_src or "_ensure_gateway" in chat_src


def main() -> None:
    _check_agent_path_source_has_no_widgets()
    result = _check_standin_on_worker_thread()
    _check_qthread_worker_contract()
    print(
        "iris_agent_phase5_prove0 ok",
        result.mode,
        result.pin[:7],
        result.thread_name,
        f"http8642=not_used",
    )


if __name__ == "__main__":
    main()
