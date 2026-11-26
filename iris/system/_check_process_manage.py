"""FPR-02 — process.manage start XOR + run_id round-trip contract.

Fails when:
- non-list argv discards a valid shell (XOR false negative)
- start ok without run_id
- SpeakGrant advertises write_stdin as supported
- status/read_output/wait/cancel break run_id round-trip
- XOR miss / missing run_id lack structured error_code+hint

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_process_manage
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

from iris.infrastructure.speak_capability import PHASE4_ALLOWLIST
from iris.system.execution_context import make_execution_context
from iris.system.execution_runtime import (
    MANAGE_ACTIONS,
    ExecutionRuntime,
    normalize_process_start_args,
)
from iris.system.process_start_plan import (
    FinalizedStartPlan,
    finalize_process_start_plan,
)
from iris.system.request_approval import (
    default_approval_ledger,
    fingerprint_from_manage_args,
    reset_approval_ledger_for_tests,
)


def _grant_ctx(
    args: dict,
    *,
    session_id: str = "sess-pm",
    workspace_id: str = "",
    workspace_root: str = "",
    tool_call_id: str = "",
    fingerprint: str | None = None,
):
    ws_root = str(workspace_root or "").strip() or None
    if fingerprint is None:
        plan = finalize_process_start_plan(args, workspace_root=ws_root)
        assert isinstance(plan, FinalizedStartPlan), plan
        fingerprint = plan.fingerprint()
    rec = default_approval_ledger().grant(
        fingerprint=fingerprint,
        session_id=session_id,
        workspace_id=workspace_id,
        tool_call_id=tool_call_id,
    )
    return make_execution_context(
        session_id=session_id,
        workspace_id=workspace_id,
        workspace_root=workspace_root,
        tool_call_id=tool_call_id,
        approval_reference=rec.request_id,
    )


def _fresh_rt(tmp: Path) -> ExecutionRuntime:
    return ExecutionRuntime(runs_root=tmp / "runs")


def _check_normalize_keeps_shell() -> None:
    argv, shell = normalize_process_start_args(
        {"argv": "echo should-not-be-argv", "shell": "echo kept"}
    )
    assert argv is None, argv
    assert shell == "echo kept", shell

    argv2, shell2 = normalize_process_start_args({"argv": "echo as-shell"})
    assert argv2 is None, argv2
    assert shell2 == "echo as-shell", shell2

    argv3, shell3 = normalize_process_start_args(
        {"argv": [sys.executable, "-c", "pass"], "command": "echo no"}
    )
    assert argv3 == [sys.executable, "-c", "pass"], argv3
    assert shell3 == "echo no", shell3


def _check_schema_no_write_stdin() -> None:
    grant = PHASE4_ALLOWLIST.grant("process.manage")
    assert grant is not None
    props = (grant.parameters or {}).get("properties") or {}
    enum = set((props.get("action") or {}).get("enum") or [])
    assert "write_stdin" not in enum, enum
    assert "write_stdin" not in MANAGE_ACTIONS
    assert "start" in enum
    assert (grant.parameters or {}).get("required") == ["action"]
    assert "data" not in props and "text" not in props
    desc = str(grant.summary or "").lower()
    assert "exactly one" in desc or "xor" in desc
    assert "run_id" in desc
    assert "not supported" in desc


def _check_xor_structured_error() -> None:
    with tempfile.TemporaryDirectory() as td:
        rt = _fresh_rt(Path(td))
        # Finalize fails before ledger consume — no grant required.
        both = {
            "action": "start",
            "argv": [sys.executable, "-c", "pass"],
            "shell": "echo x",
            "cwd": str(Path.home()),
        }
        out = rt.manage(both, ctx=make_execution_context(session_id="sess-pm"))
        assert out.get("ok") is False, out
        data = out.get("data") or {}
        assert data.get("error_code") == "start_xor_required", out
        assert "hint" in data and data["hint"], out

        neither = {"action": "start", "cwd": str(Path.home())}
        out2 = rt.manage(neither, ctx=make_execution_context(session_id="sess-pm"))
        assert out2.get("ok") is False, out2
        data2 = out2.get("data") or {}
        assert data2.get("error_code") == "start_xor_required", out2

        miss = rt.manage({"action": "status"}, ctx=make_execution_context(session_id="sess-pm"))
        assert miss.get("ok") is False, miss
        data3 = miss.get("data") or {}
        assert data3.get("error_code") == "run_id_required", miss
        assert data3.get("hint"), miss


def _check_string_argv_with_shell_starts() -> None:
    """Regression: non-list argv must not discard shell → XOR fail."""
    with tempfile.TemporaryDirectory() as td:
        rt = _fresh_rt(Path(td))
        # Brief python one-liner via shell alias path.
        code = "import sys; print(7); sys.exit(0)"
        shell_cmd = f'"{sys.executable}" -c "{code}"'
        args = {
            "action": "start",
            "argv": "bogus-non-list",
            "shell": shell_cmd,
            "cwd": str(Path.home()),
        }
        started = rt.manage(args, ctx=_grant_ctx(args))
        assert started.get("ok") is True, started
        run_id = str((started.get("data") or {}).get("run_id") or "")
        assert run_id, started
        waited = rt.manage(
            {"action": "wait", "run_id": run_id, "timeout_s": 15},
            ctx=make_execution_context(session_id="sess-pm"),
        )
        assert waited.get("ok") is True, waited
        assert (waited.get("data") or {}).get("run_id") == run_id


def _check_run_id_round_trip() -> None:
    """start → status → read_output → wait/cancel with a ~3s number script."""
    with tempfile.TemporaryDirectory() as td:
        rt = _fresh_rt(Path(td))
        script = (
            "import sys, time\n"
            "for i in range(3):\n"
            "    print(i, flush=True)\n"
            "    time.sleep(1)\n"
            "sys.exit(0)\n"
        )
        args = {
            "action": "start",
            "argv": [sys.executable, "-c", script],
            "cwd": str(Path.home()),
        }
        started = rt.manage(args, ctx=_grant_ctx(args))
        assert started.get("ok") is True, started
        data = started.get("data") or {}
        run_id = str(data.get("run_id") or "")
        assert run_id, started

        st = rt.manage(
            {"action": "status", "run_id": run_id},
            ctx=make_execution_context(session_id="sess-pm"),
        )
        assert st.get("ok") is True, st
        assert (st.get("data") or {}).get("run_id") == run_id, st

        # Let first line land.
        time.sleep(1.2)
        out = rt.manage(
            {"action": "read_output", "run_id": run_id, "stream": "stdout"},
            ctx=make_execution_context(session_id="sess-pm"),
        )
        assert out.get("ok") is True, out
        payload = out.get("data") or {}
        assert payload.get("run_id") == run_id, out
        blob = str(payload.get("text") or "")
        assert "0" in blob, out

        waited = rt.manage(
            {"action": "wait", "run_id": run_id, "timeout_s": 15},
            ctx=make_execution_context(session_id="sess-pm"),
        )
        assert waited.get("ok") is True, waited
        wdata = waited.get("data") or {}
        assert wdata.get("run_id") == run_id, waited
        assert wdata.get("status") in {"completed", "failed", "cancelled"}, waited

        # Fresh short-lived run to exercise cancel.
        sleep_args = {
            "action": "start",
            "argv": [sys.executable, "-c", "import time; time.sleep(30)"],
            "cwd": str(Path.home()),
        }
        sleep_started = rt.manage(sleep_args, ctx=_grant_ctx(sleep_args))
        assert sleep_started.get("ok") is True, sleep_started
        rid2 = str((sleep_started.get("data") or {}).get("run_id") or "")
        assert rid2, sleep_started
        cancelled = rt.manage(
            {"action": "cancel", "run_id": rid2},
            ctx=make_execution_context(session_id="sess-pm"),
        )
        assert cancelled.get("ok") is True, cancelled
        assert (cancelled.get("data") or {}).get("run_id") == rid2, cancelled
        assert (cancelled.get("data") or {}).get("status") == "cancelled", cancelled


def _check_write_stdin_rejected() -> None:
    with tempfile.TemporaryDirectory() as td:
        rt = _fresh_rt(Path(td))
        out = rt.manage(
            {"action": "write_stdin", "run_id": "x", "data": "hi"},
            ctx=make_execution_context(session_id="sess-pm"),
        )
        assert out.get("ok") is False, out
        data = out.get("data") or {}
        assert data.get("error_code") == "unknown_action", out
        assert "write_stdin" not in set(data.get("allowed") or [])


def _check_finalize_before_consume() -> None:
    """cwd/XOR failure must not consume ledger — plan finalizes before consume."""
    reset_approval_ledger_for_tests()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        rt = _fresh_rt(root)
        outside = root.parent / "outside-cwd-not-under-ws"
        outside.mkdir(exist_ok=True)
        args = {
            "action": "start",
            "argv": [sys.executable, "-c", "pass"],
            "cwd": str(outside),
        }
        # Grant a fingerprint that would match if consume ran on raw args.
        raw_fp = fingerprint_from_manage_args(args)
        rec = default_approval_ledger().grant(
            fingerprint=raw_fp, session_id="sess-order"
        )
        out = rt.manage(
            args,
            ctx=make_execution_context(
                session_id="sess-order",
                workspace_root=str(root),
                approval_reference=rec.request_id,
            ),
        )
        assert out.get("ok") is False, out
        held = default_approval_ledger().get(rec.request_id)
        assert held is not None, "approval must remain after finalize fail"
        assert held.used is False, "consume must not run before plan finalization"
    reset_approval_ledger_for_tests()


def _check_grant_consume_share_finalized_plan() -> None:
    """Card grant fingerprint == consume fingerprint == finalized plan."""
    reset_approval_ledger_for_tests()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        rt = _fresh_rt(root)
        # Empty cwd → finalized resolves to workspace_root (≠ raw fingerprint).
        args = {
            "action": "start",
            "argv": [sys.executable, "-c", "import sys; sys.exit(0)"],
            "cwd": "",
        }
        plan = finalize_process_start_plan(args, workspace_root=str(root))
        assert isinstance(plan, FinalizedStartPlan), plan
        raw_fp = fingerprint_from_manage_args(args)
        assert plan.fingerprint() != raw_fp, "empty cwd must change finalized fp"
        assert plan.cwd == str(root.resolve())

        # Raw fingerprint grant must not start (consume uses finalized).
        bad = default_approval_ledger().grant(
            fingerprint=raw_fp, session_id="sess-fp", workspace_id="ws-1"
        )
        denied = rt.manage(
            args,
            ctx=make_execution_context(
                session_id="sess-fp",
                workspace_id="ws-1",
                workspace_root=str(root),
                approval_reference=bad.request_id,
            ),
        )
        assert denied.get("ok") is False, denied
        assert "fingerprint" in str(denied.get("error") or ""), denied
        assert default_approval_ledger().get(bad.request_id).used is False

        # Finalized grant → start ok.
        ctx = _grant_ctx(
            args,
            session_id="sess-fp2",
            workspace_id="ws-1",
            workspace_root=str(root),
        )
        started = rt.manage(args, ctx=ctx)
        assert started.get("ok") is True, started
        run_id = str((started.get("data") or {}).get("run_id") or "")
        assert run_id, started
        rt.manage(
            {"action": "wait", "run_id": run_id, "timeout_s": 15},
            ctx=make_execution_context(session_id="sess-fp2"),
        )
    reset_approval_ledger_for_tests()


def _check_plan_change_and_identity_blocks() -> None:
    """Plan change / double consume / wrong session|workspace|tool_call_id / reject."""
    reset_approval_ledger_for_tests()
    with tempfile.TemporaryDirectory() as td:
        rt = _fresh_rt(Path(td))
        home = str(Path.home())
        args_a = {
            "action": "start",
            "argv": [sys.executable, "-c", "import sys; sys.exit(0)"],
            "cwd": home,
        }
        args_b = {
            "action": "start",
            "argv": [sys.executable, "-c", "print(1)"],
            "cwd": home,
        }
        plan_a = finalize_process_start_plan(args_a)
        plan_b = finalize_process_start_plan(args_b)
        assert isinstance(plan_a, FinalizedStartPlan) and isinstance(
            plan_b, FinalizedStartPlan
        )
        assert plan_a.fingerprint() != plan_b.fingerprint()

        rec = default_approval_ledger().grant(
            fingerprint=plan_a.fingerprint(),
            session_id="sess-id",
            workspace_id="ws-a",
            tool_call_id="call-a",
        )
        # Plan change after grant
        changed = rt.manage(
            args_b,
            ctx=make_execution_context(
                session_id="sess-id",
                workspace_id="ws-a",
                tool_call_id="call-a",
                approval_reference=rec.request_id,
            ),
        )
        assert changed.get("ok") is False, changed
        assert "fingerprint" in str(changed.get("error") or ""), changed
        assert default_approval_ledger().get(rec.request_id).used is False

        # Wrong session
        wrong_sess = rt.manage(
            args_a,
            ctx=make_execution_context(
                session_id="other-sess",
                workspace_id="ws-a",
                tool_call_id="call-a",
                approval_reference=rec.request_id,
            ),
        )
        assert wrong_sess.get("ok") is False, wrong_sess
        assert "session" in str(wrong_sess.get("error") or ""), wrong_sess

        # Wrong workspace
        wrong_ws = rt.manage(
            args_a,
            ctx=make_execution_context(
                session_id="sess-id",
                workspace_id="ws-other",
                tool_call_id="call-a",
                approval_reference=rec.request_id,
            ),
        )
        assert wrong_ws.get("ok") is False, wrong_ws
        assert "workspace" in str(wrong_ws.get("error") or ""), wrong_ws

        # Wrong tool_call_id
        wrong_tc = rt.manage(
            args_a,
            ctx=make_execution_context(
                session_id="sess-id",
                workspace_id="ws-a",
                tool_call_id="call-other",
                approval_reference=rec.request_id,
            ),
        )
        assert wrong_tc.get("ok") is False, wrong_tc
        assert "tool_call" in str(wrong_tc.get("error") or ""), wrong_tc

        # Matching identity → start once
        started = rt.manage(
            args_a,
            ctx=make_execution_context(
                session_id="sess-id",
                workspace_id="ws-a",
                tool_call_id="call-a",
                approval_reference=rec.request_id,
            ),
        )
        assert started.get("ok") is True, started
        run_id = str((started.get("data") or {}).get("run_id") or "")
        assert run_id, started

        # Double consume blocked
        again = rt.manage(
            args_a,
            ctx=make_execution_context(
                session_id="sess-id",
                workspace_id="ws-a",
                tool_call_id="call-a",
                approval_reference=rec.request_id,
            ),
        )
        assert again.get("ok") is False, again
        assert "used" in str(again.get("error") or ""), again

        # Reject path never starts a process
        rej = default_approval_ledger().reject(
            fingerprint=plan_a.fingerprint(),
            session_id="sess-rej",
            workspace_id="ws-a",
            tool_call_id="call-rej",
        )
        before = len(rt.list_runs(session_id="sess-rej"))
        rejected = rt.manage(
            args_a,
            ctx=make_execution_context(
                session_id="sess-rej",
                workspace_id="ws-a",
                tool_call_id="call-rej",
                approval_reference=rej.request_id,
            ),
        )
        assert rejected.get("ok") is False, rejected
        assert "not granted" in str(rejected.get("error") or ""), rejected
        assert len(rt.list_runs(session_id="sess-rej")) == before

        rt.manage(
            {"action": "wait", "run_id": run_id, "timeout_s": 15},
            ctx=make_execution_context(session_id="sess-id"),
        )
    reset_approval_ledger_for_tests()


def main() -> None:
    _check_normalize_keeps_shell()
    _check_schema_no_write_stdin()
    _check_xor_structured_error()
    _check_string_argv_with_shell_starts()
    _check_run_id_round_trip()
    _check_write_stdin_rejected()
    _check_finalize_before_consume()
    _check_grant_consume_share_finalized_plan()
    _check_plan_change_and_identity_blocks()
    print("process_manage ok")


if __name__ == "__main__":
    main()
