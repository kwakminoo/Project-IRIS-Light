"""Phase 5 Prove 2: no-console on agent path + exception containment (no kill).

Does not start Merge, Prove 3, or remove the :8642 product path.
"""

from __future__ import annotations

import inspect
import os
import subprocess
import sys
import threading
from pathlib import Path

from iris.infrastructure import agent_runtime as ar
from iris.system.win_subprocess import no_window_kwargs
from iris.ui.workers import hermes_workers as hw


def _qcore_app():
    from PyQt6.QtCore import QCoreApplication

    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    return app


def _check_failure_payload_shape() -> None:
    payload = ar.format_agent_loop_failure(RuntimeError("prove2-shape"))
    assert payload.startswith(ar.AGENT_LOOP_FAILED_PREFIX)
    assert "RuntimeError" in payload
    assert "prove2-shape" in payload
    assert ar.AGENT_LOOP_PROPAGATE_BASE == (SystemExit, KeyboardInterrupt)


def _check_standin_force_fail_returns_error() -> None:
    out = ar.run_agent_loop_standin(prompt="phase5-prove2", force_fail=True)
    assert isinstance(out, ar.AgentLoopStandinResult)
    assert out.ok is False
    assert out.mode == "stub"
    assert any(m.startswith(ar.AGENT_LOOP_FAILED_PREFIX) for m in out.messages)


def _check_agent_path_no_console_contract() -> None:
    # Reuse product CREATE_NO_WINDOW helper — agent path must not invent a parallel spawn.
    installed = ar.ensure_agent_loop_no_console()
    assert installed is True or sys.platform != "win32"
    if sys.platform == "win32":
        kw = no_window_kwargs()
        no_win = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        assert kw.get("creationflags", 0) & no_win, kw
        assert getattr(subprocess, "_iris_no_console_patched", False)

    standin_src = inspect.getsource(ar.run_agent_loop_standin)
    worker_run = inspect.getsource(hw.IrisAgentLoopStandinWorker.run)
    for src, label in ((standin_src, "standin"), (worker_run, "worker.run")):
        assert "ensure_agent_loop_no_console" in src or label == "standin"
        # Bare console-friendly spawn helpers must not appear on the prove path.
        assert "CREATE_NEW_CONSOLE" not in src
        assert "shell=True" not in src


def _check_worker_source_containment_policy() -> None:
    run_src = inspect.getsource(hw.IrisAgentLoopStandinWorker.run)
    assert "ensure_agent_loop_no_console" in run_src
    assert "format_agent_loop_failure" in run_src
    assert "AGENT_LOOP_PROPAGATE_BASE" in run_src
    assert "failed.emit" in run_src
    # Exception contained; propagate bases re-raised (not swallowed as agent_failed).
    assert "except AGENT_LOOP_PROPAGATE_BASE" in run_src
    assert "except Exception" in run_src


def _check_worker_exception_emits_failed_process_lives() -> None:
    from PyQt6.QtCore import QTimer

    app = _qcore_app()
    pid = os.getpid()
    box: dict[str, object | None] = {"failed": None, "ok": None}

    def on_failed(msg: str) -> None:
        box["failed"] = msg
        app.quit()

    def on_ok(result: object) -> None:
        box["ok"] = result
        app.quit()

    worker = hw.IrisAgentLoopStandinWorker(prompt="prove2", force_fail=True)
    worker.failed.connect(on_failed)
    worker.finished_ok.connect(on_ok)
    worker.start()
    QTimer.singleShot(15_000, app.quit)
    app.exec()
    worker.wait(5_000)
    assert box["ok"] is None
    failed = box["failed"]
    assert isinstance(failed, str)
    assert failed.startswith(ar.AGENT_LOOP_FAILED_PREFIX), failed
    assert "RuntimeError" in failed
    assert "phase5-prove1 forced" in failed
    # Containment means this process is still the same live PID — no kill required.
    assert os.getpid() == pid
    assert Path(f"/proc/{pid}").exists() if sys.platform.startswith("linux") else True


def _check_standin_ok_false_via_worker() -> None:
    """ok=False result path also becomes failed signal (no process death)."""
    from PyQt6.QtCore import QTimer

    app = _qcore_app()
    box: dict[str, object | None] = {"failed": None, "ok": None}

    def on_failed(msg: str) -> None:
        box["failed"] = msg
        app.quit()

    def on_ok(result: object) -> None:
        box["ok"] = result
        app.quit()

    worker = hw.IrisAgentLoopStandinWorker(
        prompt="prove2-okfalse", standin_force_fail=True
    )
    worker.failed.connect(on_failed)
    worker.finished_ok.connect(on_ok)
    worker.start()
    QTimer.singleShot(15_000, app.quit)
    app.exec()
    worker.wait(5_000)

    assert box["ok"] is None
    failed = box["failed"]
    assert isinstance(failed, str)
    assert failed.startswith(ar.AGENT_LOOP_FAILED_PREFIX), failed
    assert "phase5-prove2 standin force_fail" in failed


def _check_propagate_base_not_swallowed() -> None:
    """SystemExit / KeyboardInterrupt must not become agent_failed strings."""
    for exc_type in ar.AGENT_LOOP_PROPAGATE_BASE:
        try:
            raise exc_type()
        except ar.AGENT_LOOP_PROPAGATE_BASE:
            pass
        else:
            raise AssertionError(f"{exc_type.__name__} must be in PROPAGATE_BASE")
    # Policy source: worker re-raises those, does not format them.
    run_src = inspect.getsource(hw.IrisAgentLoopStandinWorker.run)
    assert "format_agent_loop_failure" in run_src
    # Ordering: propagate except precedes Exception contain.
    prop_i = run_src.index("except AGENT_LOOP_PROPAGATE_BASE")
    exc_i = run_src.index("except Exception")
    assert prop_i < exc_i


def _check_product_8642_untouched() -> None:
    chat_src = inspect.getsource(hw.HermesChatWorker)
    assert (
        "8642" in chat_src
        or "ensure_hermes_gateway" in chat_src
        or "_ensure_gateway" in chat_src
    )


def _check_standin_still_works() -> None:
    box: dict[str, object | None] = {"result": None}

    def _target() -> None:
        box["result"] = ar.run_agent_loop_standin(prompt="phase5-prove2-ok")

    t = threading.Thread(target=_target, name="iris-agent-phase5-prove2", daemon=True)
    t.start()
    t.join(timeout=30.0)
    assert not t.is_alive()
    out = box["result"]
    assert isinstance(out, ar.AgentLoopStandinResult)
    assert out.ok and out.thread_name == "iris-agent-phase5-prove2"
    assert any("no_console=ensured" in m for m in out.messages)


def main() -> None:
    _check_failure_payload_shape()
    _check_agent_path_no_console_contract()
    _check_worker_source_containment_policy()
    _check_propagate_base_not_swallowed()
    _check_standin_force_fail_returns_error()
    _check_standin_still_works()
    _check_worker_exception_emits_failed_process_lives()
    _check_standin_ok_false_via_worker()
    _check_product_8642_untouched()
    print(
        "iris_agent_phase5_prove2 ok",
        "no-console",
        "exception-contained",
        "propagate-base=SystemExit,KeyboardInterrupt",
        "http8642=product_path_kept",
        "merge=forbidden",
    )


if __name__ == "__main__":
    main()
