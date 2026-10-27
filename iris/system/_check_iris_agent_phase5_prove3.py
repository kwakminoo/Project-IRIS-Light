"""Phase 5 Prove 3: hot-restart substitute (host survives; worker replace) + pin.

Does not start Merge and does not remove the :8642 product path.
"""

from __future__ import annotations

import inspect
import sys

from iris.infrastructure import agent_runtime as ar
from iris.ui.workers import hermes_workers as hw


def _qcore_app():
    from PyQt6.QtCore import QCoreApplication

    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    return app


def _run_standin_worker(prompt: str) -> ar.AgentLoopStandinResult:
    from PyQt6.QtCore import QTimer

    app = _qcore_app()
    box: dict[str, object | None] = {"ok": None, "failed": None}

    def on_ok(result: object) -> None:
        box["ok"] = result
        app.quit()

    def on_failed(msg: str) -> None:
        box["failed"] = msg
        app.quit()

    worker = hw.IrisAgentLoopStandinWorker(prompt=prompt)
    ar.attach_agent_loop_worker(worker)
    worker.finished_ok.connect(on_ok)
    worker.failed.connect(on_failed)
    worker.start()
    QTimer.singleShot(15_000, app.quit)
    app.exec()
    worker.wait(5_000)
    assert box["failed"] is None, box["failed"]
    out = box["ok"]
    assert isinstance(out, ar.AgentLoopStandinResult)
    assert out.ok
    return out


def _check_reset_coverage_table() -> None:
    cov = ar.AGENT_LOOP_RESET_COVERAGE
    assert cov["gateway_hang"] == ar.AGENT_LOOP_RESET_COVERED
    assert cov["config_reload"] == ar.AGENT_LOOP_RESET_COVERED
    assert cov["soft_hang"] == ar.AGENT_LOOP_RESET_COVERED
    assert cov["mcp_skill_resync"] == ar.AGENT_LOOP_RESET_COVERED
    assert cov["pin_code_swap"] == ar.AGENT_LOOP_RESET_PROCESS
    assert cov["ollama_down"] == ar.AGENT_LOOP_RESET_OUT_OF_SCOPE


def _check_pin_matches_vendor() -> None:
    assert ar.pin_matches_vendor_pin()
    loaded = ar.load_pinned_sha()
    pin_file = ar.vendor_runtime_root() / "PIN"
    assert pin_file.is_file()
    file_sha = pin_file.read_text(encoding="utf-8").strip().splitlines()[0].strip().split()[0]
    assert loaded == file_sha
    assert len(loaded) >= 7


def _check_host_survives_reset_and_standin_reruns() -> None:
    ar.clear_agent_loop_handle_for_tests()
    host = ar.AgentLoopHost(label="prove3-host")
    handle = ar.ensure_agent_loop_handle(host)
    assert handle.host is host
    host_id = id(host)

    first = _run_standin_worker("prove3-before-reset")
    assert first.mode == "stub"
    gen_before = ar.ensure_agent_loop_handle().generation

    reset = ar.reset_agent_loop()
    assert reset.ok
    assert reset.host_same
    assert reset.host_id == host_id
    assert reset.pin_matches_vendor
    assert ar.ensure_agent_loop_handle().host is host
    assert id(ar.ensure_agent_loop_handle().host) == host_id
    assert reset.generation == gen_before + 1
    assert ar.ensure_agent_loop_handle().worker is None
    assert ar.ensure_agent_loop_handle().ephemeral == {}

    second = _run_standin_worker("prove3-after-reset")
    assert second.ok and second.mode == "stub"
    assert ar.ensure_agent_loop_handle().host is host

    # Idempotent idle reset: host still same, generation advances.
    idle = ar.reset_agent_loop()
    assert idle.ok and idle.host_same
    assert id(ar.ensure_agent_loop_handle().host) == host_id
    assert idle.generation >= reset.generation + 1


def _check_replace_api_attaches_new_worker() -> None:
    ar.clear_agent_loop_handle_for_tests()
    host = ar.AgentLoopHost(label="prove3-replace")
    ar.ensure_agent_loop_handle(host)
    w1 = hw.IrisAgentLoopStandinWorker(prompt="prove3-w1")
    ar.attach_agent_loop_worker(w1)
    w2 = hw.IrisAgentLoopStandinWorker(prompt="prove3-w2")
    result = ar.replace_agent_loop_worker(w2)
    assert result.ok and result.host_same
    assert ar.ensure_agent_loop_handle().host is host
    assert ar.ensure_agent_loop_handle().worker is w2


def _check_api_surface_and_8642() -> None:
    for name in (
        "reset_agent_loop",
        "replace_agent_loop_worker",
        "ensure_agent_loop_handle",
        "attach_agent_loop_worker",
        "pin_matches_vendor_pin",
    ):
        assert callable(getattr(ar, name))
    # Worker module re-exports reset for UI-side callers (lazy, no new hermes_*).
    assert callable(hw.reset_agent_loop)
    assert callable(hw.replace_agent_loop_worker)
    chat_src = inspect.getsource(hw.HermesChatWorker)
    assert (
        "8642" in chat_src
        or "ensure_hermes_gateway" in chat_src
        or "_ensure_gateway" in chat_src
    )


def main() -> None:
    _check_reset_coverage_table()
    _check_pin_matches_vendor()
    _check_api_surface_and_8642()
    _check_replace_api_attaches_new_worker()
    _check_host_survives_reset_and_standin_reruns()
    print(
        "iris_agent_phase5_prove3 ok",
        "host_survives_reset",
        "standin_after_reset",
        "pin_matches_vendor",
        "reset_coverage=gateway_hang,config_reload,soft_hang,mcp_skill_resync",
        "process_restart=pin_code_swap",
        "http8642=product_path_kept",
        "merge_allowed=YES",
        "merge_chat=not_started",
    )


if __name__ == "__main__":
    main()
