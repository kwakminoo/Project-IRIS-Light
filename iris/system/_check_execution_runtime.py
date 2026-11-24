"""U05 — Unified Execution Runtime (process-centric runs).

Fails when:
- start/wait does not yield completed + real exit_code
- cancel leaves the process alive or wrong terminal status
- concurrent runs share one last_run.log as sole authority
- process.manage SpeakGrant action enum lacks list|status|read_output|wait|cancel

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_execution_runtime
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from iris.infrastructure.speak_capability import PHASE4_ALLOWLIST
from iris.system.execution_runtime import (
    MANAGE_ACTIONS,
    ExecutionRuntime,
    ProcessStatus,
    default_runtime,
)


def _pid_alive(pid: int) -> bool:
    from iris.system.execution_runtime import _pid_still_alive

    return _pid_still_alive(pid)


def _check_start_wait_exit() -> None:
    rt = ExecutionRuntime(runs_root=Path.home() / ".iris-light" / "runs")
    run_id = rt.start(argv=[sys.executable, "-c", "import sys; sys.exit(42)"])
    assert run_id, run_id
    rec = rt.wait(run_id, timeout_s=15.0)
    assert rec.status == ProcessStatus.COMPLETED, rec
    assert rec.exit_code == 42, rec
    assert rec.stdout_ref and Path(rec.stdout_ref).is_file(), rec
    assert rec.stderr_ref and Path(rec.stderr_ref).is_file(), rec


def _check_cancel_sleep() -> None:
    rt = ExecutionRuntime(runs_root=Path.home() / ".iris-light" / "runs")
    run_id = rt.start(argv=[sys.executable, "-c", "import time; time.sleep(60)"])
    time.sleep(0.3)
    st = rt.status(run_id)
    assert st.status == ProcessStatus.RUNNING, st
    pid = int(st.pid or 0)
    assert pid > 0, st
    cancelled = rt.cancel(run_id)
    assert cancelled.status in (
        ProcessStatus.CANCELLED,
        ProcessStatus.INTERRUPTED,
    ), cancelled
    deadline = time.time() + 5.0
    while time.time() < deadline and _pid_alive(pid):
        time.sleep(0.1)
    assert not _pid_alive(pid), f"pid {pid} still alive after cancel"


def _check_concurrent_log_isolation() -> None:
    rt = ExecutionRuntime(runs_root=Path.home() / ".iris-light" / "runs")
    a = rt.start(argv=[sys.executable, "-c", "print('AAA'); import sys; sys.exit(0)"])
    b = rt.start(argv=[sys.executable, "-c", "print('BBB'); import sys; sys.exit(0)"])
    ra = rt.wait(a, timeout_s=15.0)
    rb = rt.wait(b, timeout_s=15.0)
    assert ra.stdout_ref != rb.stdout_ref, (ra.stdout_ref, rb.stdout_ref)
    assert ra.stderr_ref != rb.stderr_ref, (ra.stderr_ref, rb.stderr_ref)
    text_a = Path(ra.stdout_ref).read_text(encoding="utf-8", errors="replace")
    text_b = Path(rb.stdout_ref).read_text(encoding="utf-8", errors="replace")
    assert "AAA" in text_a and "BBB" not in text_a, text_a
    assert "BBB" in text_b and "AAA" not in text_b, text_b
    # last_run.log may exist as latest-compat view, never sole completion signal
    assert ra.status == ProcessStatus.COMPLETED
    assert rb.status == ProcessStatus.COMPLETED
    assert not (ra.stdout_ref.endswith("last_run.log")), ra.stdout_ref
    assert not (rb.stdout_ref.endswith("last_run.log")), rb.stdout_ref


def _check_process_manage_schema() -> None:
    grant = PHASE4_ALLOWLIST.grant("process.manage")
    assert grant is not None, "SpeakGrant process.manage missing"
    assert grant.parameters is not None
    props = grant.parameters.get("properties") or {}
    action = props.get("action") or {}
    enum = set(action.get("enum") or [])
    required = {"list", "status", "read_output", "wait", "cancel"}
    assert required <= enum, (enum, required)
    assert "action" in (grant.parameters.get("required") or [])
    assert MANAGE_ACTIONS >= required
    # Control-facing manage via default runtime + action dispatch shape
    rt = default_runtime()
    listed = rt.manage({"action": "list"})
    assert listed.get("ok") is True
    assert "runs" in listed.get("data", listed)


def main() -> None:
    _check_start_wait_exit()
    _check_cancel_sleep()
    _check_concurrent_log_isolation()
    _check_process_manage_schema()
    print("execution_runtime ok")


if __name__ == "__main__":
    main()
