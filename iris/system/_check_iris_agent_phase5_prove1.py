"""Phase 5 Prove 1: worker→UI is signal-only; no UI block; slot exceptions contained.

Does not start Merge, Prove 2, or remove the :8642 product path.
"""

from __future__ import annotations

import ast
import inspect
import logging
import sys
import textwrap
import threading
from pathlib import Path

from iris.infrastructure import agent_runtime as ar
from iris.ui.workers import hermes_workers as hw


def _silence_agent_slot_log() -> None:
    logging.getLogger(hw.__name__).setLevel(logging.CRITICAL)


_FORBIDDEN_SYNC_UI = frozenset(
    {
        "QWidget",
        "QMainWindow",
        "QDialog",
        "QApplication",
        "QtWidgets",
        "processEvents",
        "show",
        "setGeometry",
        "setParent",
    }
)


def _ast_hits_forbidden(source: str, names: frozenset[str]) -> list[str]:
    tree = ast.parse(textwrap.dedent(source))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in names:
            hits.append(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in names:
            hits.append(node.attr)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if "QtWidgets" in mod:
                hits.append(mod)
            for alias in node.names:
                if alias.name in names:
                    hits.append(f"{mod}.{alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if "QtWidgets" in alias.name:
                    hits.append(alias.name)
    return hits


def _check_agent_path_still_qt_free() -> None:
    src = Path(ar.__file__).read_text(encoding="utf-8")
    hits = _ast_hits_forbidden(src, _FORBIDDEN_SYNC_UI - {"show", "setGeometry", "setParent"})
    assert not hits, f"agent_runtime must stay free of sync UI / widgets: {hits}"
    standin = inspect.getsource(ar.run_agent_loop_standin)
    assert "8642" not in standin
    assert "processEvents" not in standin


def _check_worker_signal_only_source() -> None:
    cls = hw.IrisAgentLoopStandinWorker
    run_src = inspect.getsource(cls.run)
    hits = _ast_hits_forbidden(run_src, _FORBIDDEN_SYNC_UI - {"show"})
    # ``show`` alone is too broad (string/docs); keep processEvents / widgets.
    assert "processEvents" not in run_src
    assert "QWidget" not in run_src
    assert "QtWidgets" not in run_src
    assert "try:" in run_src
    assert "failed.emit" in run_src
    assert "finished_ok.emit" in run_src
    assert "run_agent_loop_standin" in run_src
    assert not hits or set(hits) <= {"show"}, f"worker run sync-UI hits: {hits}"

    signals = {
        name
        for name, val in vars(cls).items()
        if type(val).__name__ == "pyqtSignal"
        or val.__class__.__name__ == "pyqtSignal"
    }
    # PyQt binds descriptors; fall back to documented frozenset.
    expected = set(hw.IRIS_AGENT_LOOP_UI_SIGNALS)
    assert expected == {"finished_ok", "failed"}
    for name in expected:
        assert hasattr(cls, name), f"missing signal {name}"
    # No extra public bridge beyond the contract set.
    for name in signals:
        assert name in expected, f"unexpected worker signal {name}"


def _check_bad_path_not_on_mainwindow() -> None:
    probe = "prove1_ui_abort_if_uncaught"
    assert callable(hw.prove1_ui_abort_if_uncaught)
    ui_root = Path(hw.__file__).resolve().parents[1]  # iris/ui
    offenders: list[str] = []
    for path in ui_root.rglob("*.py"):
        if path.name == "hermes_workers.py":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if probe in text:
            offenders.append(str(path.relative_to(ui_root.parent.parent)))
    assert not offenders, f"{probe} must stay out of live UI modules: {offenders}"


def _check_safe_slot_contains_raise() -> None:
    @hw.safe_agent_ui_slot
    def _boom() -> None:
        hw.prove1_ui_abort_if_uncaught()

    # Must not propagate — would be 0xC0000409 if this were a live slot.
    assert _boom() is None


def _qcore_app():
    from PyQt6.QtCore import QCoreApplication

    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    return app


def _check_worker_failed_signal_no_escape() -> None:
    from PyQt6.QtCore import QTimer

    app = _qcore_app()
    box: dict[str, object | None] = {"failed": None, "ok": None, "slot_exc": None}

    @hw.safe_agent_ui_slot
    def on_failed(msg: str) -> None:
        box["failed"] = msg
        # Intentional raise inside the slot body — wrapper must contain it.
        raise RuntimeError("phase5-prove1 slot body raise (must be contained)")

    def on_ok(result: object) -> None:
        box["ok"] = result
        app.quit()

    worker = hw.IrisAgentLoopStandinWorker(prompt="prove1", force_fail=True)
    worker.failed.connect(on_failed)
    worker.finished_ok.connect(on_ok)

    def _after_fail() -> None:
        # Give the queued slot a tick, then quit.
        app.quit()

    worker.failed.connect(lambda _m: QTimer.singleShot(0, _after_fail))
    worker.start()
    QTimer.singleShot(15_000, app.quit)
    app.exec()
    worker.wait(5_000)
    assert box["ok"] is None, "force_fail must not emit finished_ok"
    assert isinstance(box["failed"], str) and "phase5-prove1 forced" in str(box["failed"])


def _check_ui_thread_not_blocked() -> None:
    from PyQt6.QtCore import QTimer

    app = _qcore_app()
    ticks = {"n": 0}
    done = {"ok": False, "failed": None}

    def on_tick() -> None:
        ticks["n"] += 1

    def on_ok(result: object) -> None:
        done["ok"] = True
        app.quit()

    def on_failed(msg: str) -> None:
        done["failed"] = msg
        app.quit()

    ticker = QTimer()
    ticker.setInterval(10)
    ticker.timeout.connect(on_tick)
    ticker.start()

    # settle_ms keeps the worker busy while the UI timer must keep firing.
    worker = hw.IrisAgentLoopStandinWorker(
        prompt="prove1-noblock", settle_ms=120
    )
    worker.finished_ok.connect(on_ok)
    worker.failed.connect(on_failed)
    worker.start()
    QTimer.singleShot(15_000, app.quit)
    app.exec()
    ticker.stop()
    worker.wait(5_000)
    assert done["failed"] is None, f"unexpected fail: {done['failed']}"
    assert done["ok"] is True
    assert ticks["n"] >= 3, (
        f"UI thread looked blocked during worker settle (ticks={ticks['n']})"
    )


def _check_standin_still_off_ui_thread() -> None:
    box: dict[str, object | None] = {"result": None}

    def _target() -> None:
        box["result"] = ar.run_agent_loop_standin(prompt="phase5-prove1")

    t = threading.Thread(target=_target, name="iris-agent-phase5-prove1", daemon=True)
    t.start()
    t.join(timeout=30.0)
    assert not t.is_alive()
    out = box["result"]
    assert isinstance(out, ar.AgentLoopStandinResult)
    assert out.ok and out.thread_name == "iris-agent-phase5-prove1"


def _check_product_8642_untouched() -> None:
    chat_src = inspect.getsource(hw.HermesChatWorker)
    assert (
        "8642" in chat_src
        or "ensure_hermes_gateway" in chat_src
        or "_ensure_gateway" in chat_src
    )


def main() -> None:
    _silence_agent_slot_log()
    _check_agent_path_still_qt_free()
    _check_worker_signal_only_source()
    _check_bad_path_not_on_mainwindow()
    _check_safe_slot_contains_raise()
    _check_standin_still_off_ui_thread()
    _check_worker_failed_signal_no_escape()
    _check_ui_thread_not_blocked()
    _check_product_8642_untouched()
    print(
        "iris_agent_phase5_prove1 ok",
        "signal-only",
        "ui-not-blocked",
        "slot-contained",
        "http8642=product_path_kept",
    )


if __name__ == "__main__":
    main()
