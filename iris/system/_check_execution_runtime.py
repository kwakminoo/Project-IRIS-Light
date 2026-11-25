"""U05 / W11-G — Unified Execution Runtime (process-centric runs).

Fails when:
- start/wait does not yield real exit_code; non-zero reported as success
- cancel leaves the process (tree) alive or wrong terminal status
- concurrent runs share one last_run.log as sole authority
- late finish of an older run poisons newer last_run compat
- retention does not prune under runs_root limits
- process.manage SpeakGrant action enum lacks list|status|read_output|wait|cancel
- process.manage start bypasses approval / cwd policy / session ACL
- wait ignores hard timeout cap

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_execution_runtime
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

from iris.infrastructure.speak_capability import PHASE4_ALLOWLIST
from iris.system.execution_context import (
    TRUST_FIELD_KEYS,
    execution_context_from_control,
    make_execution_context,
)
from iris.system.execution_runtime import (
    MANAGE_ACTIONS,
    WAIT_MAX_TIMEOUT_S,
    ExecutionRuntime,
    ProcessStatus,
    default_runtime,
)
from iris.system.project_ops import result_from_runtime_record
from iris.system.request_approval import (
    default_approval_ledger,
    fingerprint_from_manage_args,
)


def _pid_alive(pid: int) -> bool:
    from iris.system.execution_runtime import _pid_still_alive

    return _pid_still_alive(pid)


def _grant_start_ctx(
    args: dict,
    *,
    session_id: str,
    workspace_id: str = "",
    workspace_root: str = "",
    principal: str = "",
    permission_scope: str = "session",
):
    """HF-04: manage(start) uses ledger approval_reference — not set_human_confirm."""
    rec = default_approval_ledger().grant(
        fingerprint=fingerprint_from_manage_args(args),
        session_id=session_id,
        workspace_id=workspace_id,
    )
    return make_execution_context(
        session_id=session_id,
        workspace_id=workspace_id,
        workspace_root=workspace_root,
        principal=principal,
        permission_scope=permission_scope,
        approval_reference=rec.request_id,
    )


def _check_start_wait_exit() -> None:
    with tempfile.TemporaryDirectory() as td:
        rt = _fresh_rt(Path(td))
        run_id = rt.start(argv=[sys.executable, "-c", "import sys; sys.exit(42)"])
        assert run_id, run_id
        rec = rt.wait(run_id, timeout_s=15.0)
        # W11-G: process exited, but non-zero ≠ task success.
        assert rec.status == ProcessStatus.FAILED, rec
        assert rec.exit_code == 42, rec
        assert rec.stdout_ref and Path(rec.stdout_ref).is_file(), rec
        assert rec.stderr_ref and Path(rec.stderr_ref).is_file(), rec
        helper = result_from_runtime_record(
            rec, argv=[sys.executable, "-c", "x"], cwd=str(td), elapsed_sec=0.1
        )
        assert helper.get("ok") is False, helper
        assert helper.get("exit_code") == 42, helper
        waited = rt.manage({"action": "wait", "run_id": run_id, "timeout_s": 1})
        data = waited.get("data") or {}
        assert data.get("status") == ProcessStatus.FAILED.value, waited
        assert data.get("exit_code") == 42, waited
        # Transport may be ok; payload must not look like success to helpers.
        assert result_from_runtime_record(
            rt.status(run_id),
            argv=["x"],
            cwd=str(td),
            elapsed_sec=0.0,
        ).get("ok") is False


def _check_zero_exit_completed_ok() -> None:
    with tempfile.TemporaryDirectory() as td:
        rt = _fresh_rt(Path(td))
        run_id = rt.start(argv=[sys.executable, "-c", "import sys; sys.exit(0)"])
        rec = rt.wait(run_id, timeout_s=15.0)
        assert rec.status == ProcessStatus.COMPLETED, rec
        assert rec.exit_code == 0, rec
        helper = result_from_runtime_record(
            rec, argv=[sys.executable], cwd=str(td), elapsed_sec=0.1
        )
        assert helper.get("ok") is True, helper


def _check_cancel_sleep() -> None:
    with tempfile.TemporaryDirectory() as td:
        rt = _fresh_rt(Path(td))
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


def _check_cancel_kills_child_tree() -> None:
    """Windows: taskkill /T; parent that spawns a sleeper child must both die."""
    if sys.platform != "win32":
        return
    child_marker = Path(tempfile.gettempdir()) / f"iris-w11g-child-{time.time_ns()}.pid"
    try:
        if child_marker.exists():
            child_marker.unlink()
    except OSError:
        pass
    # Parent writes child pid then sleeps; cancel must kill both.
    code = (
        "import subprocess, sys, time, pathlib\n"
        f"marker = pathlib.Path({str(child_marker)!r})\n"
        "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        "marker.write_text(str(c.pid), encoding='utf-8')\n"
        "time.sleep(120)\n"
    )
    with tempfile.TemporaryDirectory() as td:
        rt = _fresh_rt(Path(td))
        run_id = rt.start(argv=[sys.executable, "-c", code])
        deadline = time.time() + 8.0
        child_pid = 0
        while time.time() < deadline:
            if child_marker.is_file():
                try:
                    child_pid = int(child_marker.read_text(encoding="utf-8").strip())
                except (OSError, ValueError):
                    child_pid = 0
                if child_pid > 0:
                    break
            time.sleep(0.05)
        assert child_pid > 0, "child pid marker not written"
        parent = int(rt.status(run_id).pid or 0)
        assert parent > 0 and _pid_alive(parent), parent
        assert _pid_alive(child_pid), child_pid
        cancelled = rt.cancel(run_id)
        assert cancelled.status in (
            ProcessStatus.CANCELLED,
            ProcessStatus.INTERRUPTED,
        ), cancelled
        end = time.time() + 8.0
        while time.time() < end and (_pid_alive(parent) or _pid_alive(child_pid)):
            time.sleep(0.1)
        assert not _pid_alive(parent), f"parent {parent} still alive"
        assert not _pid_alive(child_pid), f"child {child_pid} still alive after tree kill"
    try:
        child_marker.unlink(missing_ok=True)
    except OSError:
        pass


def _check_concurrent_log_isolation() -> None:
    with tempfile.TemporaryDirectory() as td:
        rt = _fresh_rt(Path(td))
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


def _check_last_run_compat_not_poisoned() -> None:
    """Older run finishing after a newer one must not overwrite last_run for newer."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        rt = _fresh_rt(root)
        # Slow older run
        older = rt.start(
            argv=[
                sys.executable,
                "-c",
                "import time; time.sleep(1.2); print('OLDER'); import sys; sys.exit(0)",
            ]
        )
        time.sleep(0.15)
        newer = rt.start(
            argv=[sys.executable, "-c", "print('NEWER'); import sys; sys.exit(0)"]
        )
        rn = rt.wait(newer, timeout_s=15.0)
        assert rn.status == ProcessStatus.COMPLETED, rn
        compat = root / "runs" / "last_run.log"
        assert compat.is_file(), compat
        mid = compat.read_text(encoding="utf-8", errors="replace")
        assert f"run_id={newer}" in mid, mid
        assert "NEWER" in mid, mid
        ro = rt.wait(older, timeout_s=15.0)
        assert ro.status == ProcessStatus.COMPLETED, ro
        # Give late pump a beat to attempt poison write
        time.sleep(0.3)
        final = compat.read_text(encoding="utf-8", errors="replace")
        assert f"run_id={newer}" in final, final
        assert f"run_id={older}" not in final.splitlines()[0], final
        assert "NEWER" in final, final


def _check_retention_prunes() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        rt = ExecutionRuntime(
            runs_root=root / "runs",
            max_runs=5,
            max_age_s=3600.0,
            max_bytes=50_000,
        )
        ids: list[str] = []
        for i in range(8):
            rid = rt.start(
                argv=[sys.executable, "-c", f"print({i}); import sys; sys.exit(0)"]
            )
            ids.append(rid)
            rt.wait(rid, timeout_s=15.0)
        run_dirs = [
            p
            for p in (root / "runs").iterdir()
            if p.is_dir() and (p / "meta.json").is_file()
        ]
        assert len(run_dirs) <= 5, (len(run_dirs), [p.name for p in run_dirs])
        # Newest ids should remain
        remaining = {p.name for p in run_dirs}
        for rid in ids[-5:]:
            assert rid in remaining, (rid, remaining)
        for rid in ids[:-5]:
            assert rid not in remaining, (rid, remaining)

        # Oversize: one fat run dir forces prune of older siblings.
        rt2 = ExecutionRuntime(
            runs_root=root / "runs2",
            max_runs=20,
            max_age_s=3600.0,
            max_bytes=8_000,
        )
        small = rt2.start(argv=[sys.executable, "-c", "print('s'); import sys; sys.exit(0)"])
        rt2.wait(small, timeout_s=15.0)
        fat_dir = root / "runs2" / "fatpad"
        fat_dir.mkdir(parents=True, exist_ok=True)
        (fat_dir / "meta.json").write_text(
            '{"run_id":"fatpad","status":"completed","started_at":0}', encoding="utf-8"
        )
        (fat_dir / "blob.bin").write_bytes(b"x" * 20_000)
        # Trigger retention via another start
        keep = rt2.start(argv=[sys.executable, "-c", "print('k'); import sys; sys.exit(0)"])
        rt2.wait(keep, timeout_s=15.0)
        left = [
            p.name
            for p in (root / "runs2").iterdir()
            if p.is_dir() and (p / "meta.json").is_file()
        ]
        # Fat pad and/or oldest pruned so total bytes stay in budget; newest keep remains.
        assert keep in left, left
        assert "fatpad" not in left or small not in left, left


def _check_process_manage_schema() -> None:
    grant = PHASE4_ALLOWLIST.grant("process.manage")
    assert grant is not None, "SpeakGrant process.manage missing"
    assert grant.parameters is not None
    props = grant.parameters.get("properties") or {}
    action = props.get("action") or {}
    enum = set(action.get("enum") or [])
    required = {"list", "status", "read_output", "wait", "cancel", "start"}
    assert required <= enum, (enum, required)
    assert "write_stdin" not in enum, enum
    assert "write_stdin" not in MANAGE_ACTIONS
    assert "action" in (grant.parameters.get("required") or [])
    assert MANAGE_ACTIONS >= required
    desc = str(grant.summary or "").lower()
    assert "exactly one" in desc or "xor" in desc, grant.summary
    assert "run_id" in desc, grant.summary
    assert "write_stdin" in desc and "not supported" in desc, grant.summary
    # Trust fields must not be model-writable (forgery surface).
    for key in (
        "session_id",
        "workspace_id",
        "workspace_root",
        "owner",
        "owner_token",
        "principal",
        "permission_scope",
    ):
        assert key not in props, f"SpeakGrant process.manage must not expose {key}"
        assert key in TRUST_FIELD_KEYS
    # Unscoped list without trusted admin context is blocked.
    rt = default_runtime()
    listed = rt.manage({"action": "list"})
    assert listed.get("ok") is False, listed
    err = str(listed.get("error") or "").lower()
    assert "session" in err or "admin" in err or "denied" in err or "scope" in err, listed


def _fresh_rt(tmp: Path) -> ExecutionRuntime:
    return ExecutionRuntime(runs_root=tmp / "runs")


def _check_start_requires_approval() -> None:
    with tempfile.TemporaryDirectory() as td:
        rt = _fresh_rt(Path(td))
        ctx = make_execution_context(session_id="sess-a")
        denied = rt.manage(
            {
                "action": "start",
                "argv": [sys.executable, "-c", "pass"],
                "cwd": str(Path.home()),
            },
            ctx=ctx,
        )
        assert denied.get("ok") is False, denied
        err = str(denied.get("error") or "").lower()
        assert "confirm" in err or "human" in err or "approval" in err, denied

        start_args = {
            "action": "start",
            "argv": [sys.executable, "-c", "import sys; sys.exit(0)"],
            "cwd": str(Path.home()),
        }
        ok = rt.manage(
            start_args,
            ctx=_grant_start_ctx(start_args, session_id="sess-a"),
        )
        assert ok.get("ok") is True, ok
        run_id = (ok.get("data") or {}).get("run_id")
        assert run_id
        rt.wait(str(run_id), timeout_s=15.0)


def _check_start_cwd_outside_denied() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        (root / "ws").mkdir(exist_ok=True)
        outside = root.parent / "iris-proc-cwd-outside"
        outside.mkdir(exist_ok=True)
        try:
            rt = _fresh_rt(root)
            start_args = {
                "action": "start",
                "argv": [sys.executable, "-c", "pass"],
                "cwd": str(outside),
                # Forged — must be ignored; trusted ctx workspace_root wins.
                "workspace_root": str(outside),
            }
            ctx = _grant_start_ctx(
                start_args,
                session_id="sess-a",
                workspace_root=str(root / "ws"),
            )
            denied = rt.manage(start_args, ctx=ctx)
            assert denied.get("ok") is False, denied
            assert "cwd" in str(denied.get("error") or "").lower() or "path" in str(
                denied.get("error") or ""
            ).lower() or "root" in str(denied.get("error") or "").lower(), denied
        finally:
            try:
                outside.rmdir()
            except OSError:
                pass


def _check_same_session_status_ok() -> None:
    with tempfile.TemporaryDirectory() as td:
        rt = _fresh_rt(Path(td))
        start_args = {
            "action": "start",
            "argv": [sys.executable, "-c", "import time; time.sleep(30)"],
            "cwd": str(Path.home()),
        }
        ctx = _grant_start_ctx(
            start_args, session_id="session_a", principal="alice"
        )
        started = rt.manage(start_args, ctx=ctx)
        assert started.get("ok") is True, started
        run_id = (started.get("data") or {}).get("run_id")
        assert run_id
        data = started.get("data") or {}
        assert data.get("session_id") == "session_a", data
        # Ownership comes from trusted context, not model owner args.
        assert data.get("owner") != "forged-owner"
        st = rt.manage({"action": "status", "run_id": run_id}, ctx=ctx)
        assert st.get("ok") is True, st
        cancelled = rt.manage({"action": "cancel", "run_id": run_id}, ctx=ctx)
        assert cancelled.get("ok") is True, cancelled


def _check_cross_session_acl() -> None:
    with tempfile.TemporaryDirectory() as td:
        rt = _fresh_rt(Path(td))
        start_args = {
            "action": "start",
            "argv": [sys.executable, "-c", "import time; time.sleep(30)"],
            "cwd": str(Path.home()),
        }
        ctx_a = _grant_start_ctx(
            start_args,
            session_id="session_a",
            workspace_id="ws1",
            principal="alice",
        )
        ctx_b = make_execution_context(session_id="session_b")
        started = rt.manage(start_args, ctx=ctx_a)
        assert started.get("ok") is True, started
        run_id = (started.get("data") or {}).get("run_id")
        assert run_id
        for action in ("status", "cancel", "read_output"):
            denied = rt.manage({"action": action, "run_id": run_id}, ctx=ctx_b)
            assert denied.get("ok") is False, (action, denied)
            assert "session" in str(denied.get("error") or "").lower() or "denied" in str(
                denied.get("error") or ""
            ).lower(), (action, denied)
        cancelled = rt.manage({"action": "cancel", "run_id": run_id}, ctx=ctx_a)
        assert cancelled.get("ok") is True, cancelled


def _check_forged_trust_fields_denied() -> None:
    """Model-forged session_id / owner / workspace_root must not grant privilege."""
    with tempfile.TemporaryDirectory() as td:
        rt = _fresh_rt(Path(td))
        start_args = {
            "action": "start",
            "argv": [sys.executable, "-c", "import time; time.sleep(30)"],
            "cwd": str(Path.home()),
            # Forged ownership args — ignored for ProcessRecord ACL fields.
            "session_id": "session_evil",
            "owner": "project.run",
            "owner_token": "project.run",
        }
        ctx_a = _grant_start_ctx(
            start_args, session_id="session_a", principal="alice"
        )
        started = rt.manage(start_args, ctx=ctx_a)
        assert started.get("ok") is True, started
        run_id = (started.get("data") or {}).get("run_id")
        assert run_id
        data = started.get("data") or {}
        assert data.get("session_id") == "session_a", data
        assert data.get("owner") != "project.run" or data.get("session_id") == "session_a"

        ctx_b = make_execution_context(session_id="session_b")
        # Forge victim session_id / surface owner in args while ctx is wrong session.
        for action in ("status", "cancel", "read_output"):
            denied = rt.manage(
                {
                    "action": action,
                    "run_id": run_id,
                    "session_id": "session_a",
                    "owner": "project.run",
                    "owner_token": "alice",
                },
                ctx=ctx_b,
            )
            assert denied.get("ok") is False, (action, denied)

        # Surface owner label must not ACL-match across sessions.
        forged_owner_ctx = make_execution_context(
            session_id="session_b",
            principal="project.run",
        )
        denied_owner = rt.manage(
            {"action": "status", "run_id": run_id},
            ctx=forged_owner_ctx,
        )
        assert denied_owner.get("ok") is False, denied_owner

        cancelled = rt.manage({"action": "cancel", "run_id": run_id}, ctx=ctx_a)
        assert cancelled.get("ok") is True, cancelled


def _check_list_filters_own_session() -> None:
    with tempfile.TemporaryDirectory() as td:
        rt = _fresh_rt(Path(td))
        for sid, tag in (("session_a", "A"), ("session_b", "B")):
            start_args = {
                "action": "start",
                "argv": [sys.executable, "-c", f"print({tag!r})"],
                "cwd": str(Path.home()),
            }
            out = rt.manage(
                start_args,
                ctx=_grant_start_ctx(start_args, session_id=sid),
            )
            assert out.get("ok") is True, out
            rid = (out.get("data") or {}).get("run_id")
            rt.wait(str(rid), timeout_s=15.0)

        # List without trusted session must not dump all runs.
        unscoped = rt.manage({"action": "list"})
        assert unscoped.get("ok") is False, unscoped
        forged_list = rt.manage(
            {"action": "list", "session_id": "session_a"},
            ctx=make_execution_context(session_id="session_b"),
        )
        assert forged_list.get("ok") is True, forged_list
        forged_runs = (forged_list.get("data") or {}).get("runs") or []
        assert all(r.get("session_id") == "session_b" for r in forged_runs), forged_runs
        assert not any(r.get("session_id") == "session_a" for r in forged_runs), forged_runs

        listed = rt.manage(
            {"action": "list"},
            ctx=make_execution_context(session_id="session_a"),
        )
        assert listed.get("ok") is True, listed
        runs = (listed.get("data") or {}).get("runs") or []
        assert runs, listed
        assert all(r.get("session_id") == "session_a" for r in runs), runs
        assert not any(r.get("session_id") == "session_b" for r in runs), runs

        # Admin policy may list all.
        admin = rt.manage(
            {"action": "list"},
            ctx=execution_context_from_control(
                session_id="ops",
                permission_scope="admin",
            ),
        )
        assert admin.get("ok") is True, admin
        admin_runs = (admin.get("data") or {}).get("runs") or []
        sids = {r.get("session_id") for r in admin_runs}
        assert "session_a" in sids and "session_b" in sids, admin_runs


def _check_wait_timeout_capped() -> None:
    from iris.system import execution_policy as pol
    from iris.system import execution_runtime as rtmod
    from iris.system.execution_policy import cap_wait_timeout

    assert cap_wait_timeout(None) == WAIT_MAX_TIMEOUT_S
    assert cap_wait_timeout(10_000) == WAIT_MAX_TIMEOUT_S
    assert cap_wait_timeout(12) == 12.0

    old_p, old_r = pol.WAIT_MAX_TIMEOUT_S, rtmod.WAIT_MAX_TIMEOUT_S
    try:
        pol.WAIT_MAX_TIMEOUT_S = 0.5
        rtmod.WAIT_MAX_TIMEOUT_S = 0.5
        with tempfile.TemporaryDirectory() as td:
            rt = _fresh_rt(Path(td))
            run_id = rt.start(
                argv=[sys.executable, "-c", "import time; time.sleep(60)"],
                session_id="sess-wait",
            )
            t0 = time.time()
            snap = rt.wait(run_id, timeout_s=None)
            elapsed = time.time() - t0
            assert elapsed < 3.0, elapsed
            assert snap.status == ProcessStatus.RUNNING or "wait timed out" in (
                snap.error or ""
            ), snap
            cancelled = rt.cancel(run_id)
            assert cancelled.status in (
                ProcessStatus.CANCELLED,
                ProcessStatus.INTERRUPTED,
            ), cancelled

            rt2 = _fresh_rt(Path(td) / "w2")
            start_args = {
                "action": "start",
                "argv": [sys.executable, "-c", "import time; time.sleep(60)"],
                "cwd": str(Path.home()),
            }
            ctx_w = _grant_start_ctx(start_args, session_id="sess-wait2")
            started = rt2.manage(start_args, ctx=ctx_w)
            assert started.get("ok") is True, started
            rid2 = (started.get("data") or {}).get("run_id")
            waited = rt2.manage(
                {
                    "action": "wait",
                    "run_id": rid2,
                    "timeout_s": 9999,
                },
                ctx=ctx_w,
            )
            assert waited.get("ok") is True, waited
            # Capped soft-wait returns while still running; cancel must work.
            assert (waited.get("data") or {}).get("status") == ProcessStatus.RUNNING.value
            out = rt2.manage(
                {"action": "cancel", "run_id": rid2},
                ctx=ctx_w,
            )
            assert out.get("ok") is True, out
    finally:
        pol.WAIT_MAX_TIMEOUT_S = old_p
        rtmod.WAIT_MAX_TIMEOUT_S = old_r


def main() -> None:
    _check_start_wait_exit()
    _check_zero_exit_completed_ok()
    _check_cancel_sleep()
    _check_cancel_kills_child_tree()
    _check_concurrent_log_isolation()
    _check_last_run_compat_not_poisoned()
    _check_retention_prunes()
    _check_process_manage_schema()
    _check_start_requires_approval()
    _check_start_cwd_outside_denied()
    _check_same_session_status_ok()
    _check_cross_session_acl()
    _check_forged_trust_fields_denied()
    _check_list_filters_own_session()
    _check_wait_timeout_capped()
    print("execution_runtime ok")


if __name__ == "__main__":
    main()
