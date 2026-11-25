"""W11-C — project.run / shell.run wired to Execution Runtime.

Fails when:
- Runtime start is invisible to process.manage list/status
- project.run still uses min(timeout, 12) or wait_for_run_log as sole completion
- ordinary project.run mutates tasks.json via upsert_iris_run_task
- shell path does not register a run_id on default_runtime

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_run_path_runtime_wire
"""

from __future__ import annotations

import ast
import sys
import tempfile
import time
from pathlib import Path

from iris.system import execution_runtime as rtmod
from iris.system.execution_context import make_execution_context
from iris.system.execution_runtime import (
    ExecutionRuntime,
    ProcessStatus,
    default_runtime,
    reset_default_runtime_for_tests,
)
from iris.system.project_ops import start_managed_run, wait_managed_run


ROOT = Path(__file__).resolve().parents[2]
PROJECT_PY = ROOT / "iris" / "ui" / "control_actions" / "project.py"
SHELL_PY = ROOT / "iris" / "system" / "iris_shell.py"


def _install_temp_default(tmp: Path) -> ExecutionRuntime:
    reset_default_runtime_for_tests()
    rt = ExecutionRuntime(runs_root=tmp / "runs")
    rtmod._DEFAULT = rt
    return rt


def _check_manage_sees_started_run() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        rt = _install_temp_default(root)
        try:
            run_id = start_managed_run(
                argv=[sys.executable, "-c", "print('W11C'); import sys; sys.exit(0)"],
                cwd=root,
                timeout_s=15.0,
                session_id="sess-w11c",
                workspace_id=str(root),
                owner="project.run",
            )
            ctx = make_execution_context(session_id="sess-w11c")
            listed = rt.manage({"action": "list"}, ctx=ctx)
            assert listed.get("ok") is True, listed
            runs = (listed.get("data") or {}).get("runs") or []
            assert any(r.get("run_id") == run_id for r in runs), (run_id, runs)
            st = rt.manage({"action": "status", "run_id": run_id}, ctx=ctx)
            assert st.get("ok") is True, st
            data = st.get("data") or {}
            assert data.get("run_id") == run_id, data
            rec = wait_managed_run(run_id, timeout_s=15.0)
            assert rec.status == ProcessStatus.COMPLETED, rec
            assert rec.exit_code == 0, rec
            assert rec.stdout_ref and Path(rec.stdout_ref).is_file(), rec
            out = Path(rec.stdout_ref).read_text(encoding="utf-8", errors="replace")
            assert "W11C" in out, out
        finally:
            reset_default_runtime_for_tests()


def _check_project_run_source_no_12s_log_wait() -> None:
    src = PROJECT_PY.read_text(encoding="utf-8")
    assert "min(timeout_sec, 12.0)" not in src, "project.run must not cap wait at 12s"
    assert "min(timeout_sec, 12)" not in src
    # Sole completion via wait_for_run_log forbidden in project_run body.
    tree = ast.parse(src)
    project_run_fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "project_run":
            project_run_fn = node
            break
    assert project_run_fn is not None, "project_run missing"
    body_src = ast.get_source_segment(src, project_run_fn) or ""
    assert "wait_for_run_log" not in body_src, "project_run must not wait_for_run_log"
    assert "upsert_iris_run_task" not in body_src, (
        "ordinary project.run must not upsert tasks.json"
    )
    assert "start_managed_run" in body_src or "default_runtime" in body_src, (
        "project_run must start via Execution Runtime"
    )
    assert "wait_managed_run" in body_src or ".wait(" in body_src


def _check_shell_registers_runtime() -> None:
    shell_src = SHELL_PY.read_text(encoding="utf-8")
    assert "default_runtime" in shell_src or "start_managed_run" in shell_src, (
        "iris_shell must register runs on Execution Runtime"
    )
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        rt = _install_temp_default(root)
        try:
            from iris.system.iris_shell import ShellJob, stream_shell_job

            job = ShellJob(command="echo W11C-SHELL", cwd=root, timeout_s=15.0)
            chunks: list[str] = []
            outcome = stream_shell_job(
                job,
                chunks.append,
                session_id="sess-shell",
                workspace_id=str(root),
            )
            assert outcome.ok, outcome
            assert outcome.run_id, outcome
            assert outcome.exit_code == 0, outcome
            assert outcome.stdout_ref and Path(outcome.stdout_ref).is_file(), outcome
            st = rt.manage(
                {"action": "status", "run_id": outcome.run_id},
                ctx=make_execution_context(session_id="sess-shell"),
            )
            assert st.get("ok") is True, st
            assert (st.get("data") or {}).get("run_id") == outcome.run_id
            joined = "".join(chunks) + (outcome.stdout or "")
            file_text = Path(outcome.stdout_ref).read_text(encoding="utf-8", errors="replace")
            assert "W11C-SHELL" in joined or "W11C-SHELL" in file_text, (
                joined,
                outcome.stdout,
                file_text,
            )
        finally:
            reset_default_runtime_for_tests()


def _check_nonzero_exit_not_ok() -> None:
    from iris.system.project_ops import result_from_runtime_record

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _install_temp_default(root)
        try:
            run_id = start_managed_run(
                argv=[sys.executable, "-c", "import sys; sys.exit(3)"],
                cwd=root,
                timeout_s=15.0,
                session_id="sess-nz",
                owner="project.run",
            )
            rec = wait_managed_run(run_id, timeout_s=15.0)
            assert rec.exit_code == 3, rec
            assert rec.status == ProcessStatus.FAILED, rec
            helper = result_from_runtime_record(
                rec,
                argv=[sys.executable, "-c", "import sys; sys.exit(3)"],
                cwd=str(root),
                elapsed_sec=0.1,
            )
            assert helper.get("ok") is False, helper
            assert helper.get("exit_code") == 3, helper
        finally:
            reset_default_runtime_for_tests()


def main() -> None:
    _check_manage_sees_started_run()
    _check_project_run_source_no_12s_log_wait()
    _check_shell_registers_runtime()
    _check_nonzero_exit_not_ok()
    print("run_path_runtime_wire ok")


if __name__ == "__main__":
    main()
