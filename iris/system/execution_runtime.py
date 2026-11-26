"""U05 — Unified Execution Runtime (Local Subprocess backend).

Process-centric runs with run_id + status machine. Headless authority for
process_manage; project.run may keep the IDE terminal bridge for GUI UX.

ponytail: thin IRIS ProcessRegistry — vendor pin has no upstream registry tree.
Ceiling: Local Subprocess only; ConPTY / Docker / WSL marked unsupported stubs.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from iris.system.execution_context import (
    ExecutionContext,
    strip_trust_fields,
)
from iris.system.execution_policy import (
    WAIT_MAX_TIMEOUT_S,
    cap_wait_timeout,
)
from iris.system.process_start_plan import (
    FinalizeStartFailure,
    finalize_process_start_plan,
    normalize_process_start_args,
)
from iris.system.run_env import build_child_env
from iris.system.win_subprocess import no_window_kwargs

MANAGE_ACTIONS = frozenset(
    {
        "start",
        "list",
        "status",
        "read_output",
        "wait",
        "cancel",
    }
)

_SESSION_SCOPED_ACTIONS = frozenset(
    {
        "status",
        "read_output",
        "wait",
        "cancel",
    }
)

# Model/control start launch: exactly one of argv:list[str] XOR shell:str.
_START_XOR_HINT = (
    "Provide exactly one of argv (list of strings) or shell (string; command alias ok)"
)
_RUN_ID_HINT = "Pass run_id from a successful start (status|read_output|wait|cancel)"


def _manage_err(
    error: str,
    *,
    error_code: str,
    hint: str,
    data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(data or {})
    payload.setdefault("error_code", error_code)
    payload.setdefault("hint", hint)
    return {
        "ok": False,
        "action": "process.manage",
        "error": error,
        "data": payload,
    }

_TERMINAL = frozenset(
    {
        "completed",
        "failed",
        "cancelled",
        "timed_out",
        "interrupted",
    }
)


class ProcessStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    AWAITING_APPROVAL = "awaiting_approval"
    INTERRUPTED = "interrupted"


@dataclass
class ProcessRecord:
    run_id: str
    status: ProcessStatus
    exit_code: int | None = None
    cwd: str = ""
    interpreter: str = ""
    environment_id: str = ""
    stdout_ref: str = ""
    stderr_ref: str = ""
    pid: int | None = None
    argv: list[str] = field(default_factory=list)
    shell: str = ""
    error: str = ""
    started_at: float = 0.0
    finished_at: float | None = None
    session_id: str = ""
    workspace_id: str = ""
    owner: str = ""

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value if isinstance(self.status, ProcessStatus) else str(self.status)
        return d


class BackendKind(str, Enum):
    LOCAL_SUBPROCESS = "local_subprocess"
    CONPTY = "conpty"  # stub — unsupported this unit
    DOCKER = "docker"  # stub — unsupported
    WSL = "wsl"  # stub — unsupported


def default_runs_root(*, project_root: str | Path | None = None) -> Path:
    if project_root:
        root = Path(project_root).expanduser().resolve() / ".iris" / "runs"
        root.mkdir(parents=True, exist_ok=True)
        return root
    root = Path.home() / ".iris-light" / "runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _pid_still_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
        )
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return bool(ok) and int(code.value) == STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _kill_process_tree(proc: subprocess.Popen[Any]) -> None:
    """Kill the started process and its descendants when possible.

    Windows: ``taskkill /T /F`` walks the process tree (verified by cancel child test).
    Unix: children are started in a new session (``start_new_session=True``); we
    ``killpg`` the group, then fall back to terminate/kill on the Popen handle.
    Not a sandbox — best-effort tree cleanup only.
    """
    if proc.poll() is not None:
        return
    pid = int(proc.pid or 0)
    if sys.platform == "win32" and pid > 0:
        # Hidden taskkill — no console flash (CREATE_NO_WINDOW via no_window_kwargs).
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=10,
                **no_window_kwargs(),
            )
        except Exception:
            pass
        # Fallback: TerminateProcess on the Popen handle if tree still up.
        if _pid_still_alive(pid):
            try:
                proc.kill()
            except Exception:
                pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass
        return
    # Unix: prefer process-group kill (paired with start_new_session on Popen).
    if pid > 0:
        try:
            import signal

            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (OSError, ProcessLookupError, AttributeError):
            try:
                proc.terminate()
            except Exception:
                pass
        try:
            proc.wait(timeout=2)
            return
        except Exception:
            pass
        try:
            import signal

            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (OSError, ProcessLookupError, AttributeError):
            try:
                proc.kill()
            except Exception:
                pass
        try:
            proc.wait(timeout=2)
        except Exception:
            pass
        return
    try:
        proc.terminate()
        proc.wait(timeout=2)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


class _RunSlot:
    def __init__(self, record: ProcessRecord, run_dir: Path) -> None:
        self.record = record
        self.run_dir = run_dir
        self.proc: subprocess.Popen[Any] | None = None
        self.lock = threading.Lock()
        self.done = threading.Event()
        self._pump: threading.Thread | None = None


# Retention defaults — not a sandbox quota; keeps runs_root from growing forever.
DEFAULT_MAX_RUNS = 200
DEFAULT_MAX_AGE_S = 7 * 24 * 3600.0
DEFAULT_MAX_BYTES = 512 * 1024 * 1024


class ProcessRegistry:
    """In-process registry of Local Subprocess runs."""

    def __init__(
        self,
        *,
        runs_root: Path | None = None,
        project_root: str | Path | None = None,
        backend: BackendKind = BackendKind.LOCAL_SUBPROCESS,
        max_runs: int = DEFAULT_MAX_RUNS,
        max_age_s: float = DEFAULT_MAX_AGE_S,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self.backend = backend
        self.runs_root = Path(runs_root) if runs_root else default_runs_root(project_root=project_root)
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self.max_runs = max(1, int(max_runs))
        self.max_age_s = max(1.0, float(max_age_s))
        self.max_bytes = max(1024, int(max_bytes))
        self._slots: dict[str, _RunSlot] = {}
        self._lock = threading.RLock()
        self._latest_run_id: str | None = None
        self._human_confirm: Any = None
        self._prune_runs_root()

    def set_human_confirm(self, fn: Any) -> None:
        """Wire Control Surface human_confirm into manage start approval."""
        self._human_confirm = fn

    def start(
        self,
        *,
        argv: list[str] | None = None,
        shell: str | None = None,
        cwd: str | Path | None = None,
        env_id: str = "",
        env: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
        session_id: str = "",
        workspace_id: str = "",
        owner: str = "",
    ) -> str:
        if self.backend != BackendKind.LOCAL_SUBPROCESS:
            raise NotImplementedError(f"backend {self.backend.value} unsupported")
        use_shell = bool(shell and str(shell).strip())
        use_argv = bool(argv)
        if use_shell == use_argv:
            raise ValueError("start requires exactly one of argv or shell")
        work = Path(cwd).expanduser().resolve() if cwd else Path.cwd()
        if not work.is_dir():
            raise ValueError(f"cwd is not a directory: {work}")

        self._prune_runs_root()
        run_id = uuid.uuid4().hex
        run_dir = self.runs_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = run_dir / "stdout.log"
        stderr_path = run_dir / "stderr.log"
        meta_path = run_dir / "meta.json"

        interpreter = ""
        cmd_argv: list[str] = []
        shell_cmd = ""
        if use_argv:
            cmd_argv = [str(x) for x in (argv or [])]
            if not cmd_argv:
                raise ValueError("argv empty")
            interpreter = cmd_argv[0]
        else:
            shell_cmd = str(shell).strip()

        rec = ProcessRecord(
            run_id=run_id,
            status=ProcessStatus.QUEUED,
            cwd=str(work),
            interpreter=interpreter,
            environment_id=str(env_id or ""),
            stdout_ref=str(stdout_path),
            stderr_ref=str(stderr_path),
            argv=list(cmd_argv),
            shell=shell_cmd,
            started_at=time.time(),
            session_id=str(session_id or ""),
            workspace_id=str(workspace_id or ""),
            owner=str(owner or ""),
        )
        slot = _RunSlot(rec, run_dir)
        with self._lock:
            self._slots[run_id] = slot
            self._latest_run_id = run_id

        extra: dict[str, str] = {}
        if env:
            extra.update({str(k): str(v) for k, v in env.items()})
        if env_id:
            extra["IRIS_ENVIRONMENT_ID"] = str(env_id)
        popen_env = build_child_env(None, extra or None)

        kw: dict[str, Any] = {
            "cwd": str(work),
            "env": popen_env,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "stdin": subprocess.DEVNULL,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "bufsize": 1,
        }
        kw.update(no_window_kwargs())
        # Unix: new session so cancel can killpg the whole tree (see _kill_process_tree).
        if sys.platform != "win32":
            kw["start_new_session"] = True

        try:
            if use_argv:
                proc = subprocess.Popen(cmd_argv, shell=False, **kw)
            else:
                proc = subprocess.Popen(shell_cmd, shell=True, **kw)
        except OSError as exc:
            rec.status = ProcessStatus.FAILED
            rec.error = str(exc)
            rec.finished_at = time.time()
            slot.done.set()
            self._write_meta(slot)
            self._refresh_last_run_compat(slot)
            raise

        slot.proc = proc
        rec.pid = int(proc.pid or 0)
        rec.status = ProcessStatus.RUNNING
        self._write_meta(slot)
        self._refresh_last_run_compat(slot)

        def _pump() -> None:
            assert slot.proc is not None
            out_f = open(stdout_path, "w", encoding="utf-8", errors="replace", newline="")
            err_f = open(stderr_path, "w", encoding="utf-8", errors="replace", newline="")
            try:
                def _reader(stream: Any, dest: Any) -> None:
                    try:
                        for line in iter(stream.readline, ""):
                            dest.write(line)
                            dest.flush()
                    except Exception:
                        pass

                t_out = threading.Thread(
                    target=_reader, args=(slot.proc.stdout, out_f), daemon=True
                )
                t_err = threading.Thread(
                    target=_reader, args=(slot.proc.stderr, err_f), daemon=True
                )
                t_out.start()
                t_err.start()
                try:
                    if timeout_s is not None and timeout_s > 0:
                        try:
                            code = slot.proc.wait(timeout=float(timeout_s))
                        except subprocess.TimeoutExpired:
                            with slot.lock:
                                if slot.record.status == ProcessStatus.RUNNING:
                                    _kill_process_tree(slot.proc)
                                    slot.record.status = ProcessStatus.TIMED_OUT
                                    slot.record.exit_code = None
                                    slot.record.finished_at = time.time()
                            code = slot.proc.poll()
                    else:
                        code = slot.proc.wait()
                finally:
                    t_out.join(timeout=2)
                    t_err.join(timeout=2)
            finally:
                out_f.close()
                err_f.close()

            with slot.lock:
                if slot.record.status == ProcessStatus.RUNNING:
                    slot.record.exit_code = int(code) if code is not None else None
                    slot.record.finished_at = time.time()
                    # Process exited ≠ task success: non-zero → FAILED for callers.
                    if code == 0:
                        slot.record.status = ProcessStatus.COMPLETED
                    else:
                        slot.record.status = ProcessStatus.FAILED
                elif slot.record.status in (
                    ProcessStatus.CANCELLED,
                    ProcessStatus.INTERRUPTED,
                    ProcessStatus.TIMED_OUT,
                ):
                    if slot.record.exit_code is None:
                        slot.record.exit_code = (
                            int(code) if code is not None else slot.proc.poll()
                        )
                    if slot.record.finished_at is None:
                        slot.record.finished_at = time.time()
            self._write_meta(slot)
            self._refresh_last_run_compat(slot)
            slot.done.set()

        slot._pump = threading.Thread(target=_pump, daemon=True, name=f"iris-run-{run_id[:8]}")
        slot._pump.start()
        return run_id

    def status(self, run_id: str) -> ProcessRecord:
        slot = self._require(run_id)
        with slot.lock:
            return ProcessRecord(**{**slot.record.as_dict(), "status": ProcessStatus(slot.record.status)})

    def list_runs(self, *, session_id: str | None = None) -> list[ProcessRecord]:
        with self._lock:
            ids = list(self._slots.keys())
        runs = [self.status(i) for i in ids]
        sid = str(session_id or "").strip()
        if sid:
            runs = [r for r in runs if str(r.session_id or "") == sid]
        return runs

    def read_output(
        self,
        run_id: str,
        *,
        stream: str = "stdout",
        offset: int = 0,
        limit: int | None = None,
    ) -> dict[str, Any]:
        slot = self._require(run_id)
        path = Path(slot.record.stdout_ref if stream != "stderr" else slot.record.stderr_ref)
        if not path.is_file():
            return {"run_id": run_id, "stream": stream, "text": "", "offset": 0, "path": str(path)}
        raw = path.read_text(encoding="utf-8", errors="replace")
        start = max(0, int(offset or 0))
        chunk = raw[start:]
        if limit is not None:
            chunk = chunk[: max(0, int(limit))]
        return {
            "run_id": run_id,
            "stream": stream,
            "text": chunk,
            "offset": start,
            "path": str(path),
            "total": len(raw),
        }

    def wait(self, run_id: str, *, timeout_s: float | None = None) -> ProcessRecord:
        slot = self._require(run_id)
        # Hard cap — None / unbounded no longer waits forever (cancel still available).
        capped = cap_wait_timeout(timeout_s)
        ok = slot.done.wait(timeout=capped)
        if not ok:
            with slot.lock:
                if slot.record.status == ProcessStatus.RUNNING:
                    # soft timeout on wait only — do not kill unless cancel
                    snap = ProcessRecord(
                        **{**slot.record.as_dict(), "status": ProcessStatus(slot.record.status)}
                    )
                    snap.error = "wait timed out"
                    return snap
        return self.status(run_id)

    def cancel(self, run_id: str) -> ProcessRecord:
        slot = self._require(run_id)
        with slot.lock:
            if slot.record.status.value in _TERMINAL:
                return ProcessRecord(
                    **{**slot.record.as_dict(), "status": ProcessStatus(slot.record.status)}
                )
            slot.record.status = ProcessStatus.CANCELLED
            slot.record.finished_at = time.time()
            proc = slot.proc
        if proc is not None:
            _kill_process_tree(proc)
        slot.done.set()
        self._write_meta(slot)
        self._refresh_last_run_compat(slot)
        # Prefer cancelled; interrupted if kill raced with natural exit
        with slot.lock:
            if (
                slot.record.exit_code not in (None, 0)
                and slot.record.status == ProcessStatus.CANCELLED
                and proc is not None
                and proc.poll() is not None
            ):
                # still cancelled — kill path
                pass
            return ProcessRecord(
                **{**slot.record.as_dict(), "status": ProcessStatus(slot.record.status)}
            )

    def write_stdin(self, run_id: str, data: str) -> dict[str, Any]:
        # Optional stub — Local Subprocess starts with stdin=DEVNULL this unit.
        _ = (run_id, data)
        return {
            "ok": False,
            "unsupported": True,
            "error": "write_stdin not supported on local_subprocess (stdin closed)",
        }

    def _session_acl_allows(
        self,
        record: ProcessRecord,
        ctx: ExecutionContext | None,
    ) -> bool:
        """Compare trusted ExecutionContext vs record. Model args never consulted.

        Legacy runs with empty session_id remain readable (pre-U02). Surface labels
        like project.run / shell.run are telemetry only — not ACL tokens.
        """
        rec_sid = str(record.session_id or "").strip()
        if not rec_sid:
            return True
        if ctx is None:
            return False
        if ctx.is_admin():
            return True
        caller_sid = ctx.effective_session_id()
        if caller_sid and caller_sid == rec_sid:
            return True
        return False

    def manage(
        self,
        args: Mapping[str, Any] | None,
        *,
        ctx: ExecutionContext | None = None,
    ) -> dict[str, Any]:
        """process.manage / process_manage dispatcher.

        Ownership / ACL / workspace_root come from ``ctx`` only. Trust fields in
        ``args`` are stripped so Speak payloads cannot forge privilege.
        """
        raw = strip_trust_fields(args)
        action = str(raw.get("action") or "").strip()
        if action not in MANAGE_ACTIONS:
            return _manage_err(
                f"unknown or missing action: {action!r}",
                error_code="unknown_action",
                hint="action must be one of: " + ", ".join(sorted(MANAGE_ACTIONS)),
                data={"allowed": sorted(MANAGE_ACTIONS)},
            )
        try:
            if action == "list":
                if ctx is not None and ctx.is_admin():
                    runs = [r.as_dict() for r in self.list_runs(session_id=None)]
                    return {"ok": True, "action": "process.manage", "data": {"runs": runs}}
                sid = ctx.effective_session_id() if ctx is not None else ""
                if not sid:
                    return {
                        "ok": False,
                        "action": "process.manage",
                        "error": "session scope required (admin policy for unscoped list)",
                        "data": {"runs": []},
                    }
                runs = [r.as_dict() for r in self.list_runs(session_id=sid)]
                return {"ok": True, "action": "process.manage", "data": {"runs": runs}}
            if action == "start":
                # Finalize plan BEFORE ledger consume so card grant and consume
                # share one fingerprint (cwd resolved, argv bound XOR shell).
                from iris.system.request_approval import default_approval_ledger

                ws_root = ""
                if ctx is not None and str(ctx.workspace_root or "").strip():
                    ws_root = str(ctx.workspace_root).strip()
                plan = finalize_process_start_plan(
                    raw, workspace_root=ws_root if ws_root else None
                )
                if isinstance(plan, FinalizeStartFailure):
                    return _manage_err(
                        plan.error,
                        error_code=plan.error_code,
                        hint=plan.hint,
                        data=plan.data,
                    )

                # HF-04: manage(start) consumes RequestApprovalLedger only.
                # Product process.manage must not call set_human_confirm.
                approval_ref = ""
                if ctx is not None:
                    approval_ref = str(
                        getattr(ctx, "approval_reference", "") or ""
                    ).strip()
                if not approval_ref:
                    return {
                        "ok": False,
                        "action": "process.manage",
                        "error": "human confirm required",
                        "data": {"confirm_required": True, "risk": "high"},
                    }
                ok_c, reason_c = default_approval_ledger().consume(
                    request_id=approval_ref,
                    fingerprint=plan.fingerprint(),
                    session_id=ctx.effective_session_id() if ctx is not None else "",
                    workspace_id=str(getattr(ctx, "workspace_id", "") or ""),
                    tool_call_id=str(getattr(ctx, "tool_call_id", "") or ""),
                )
                if not ok_c:
                    return {
                        "ok": False,
                        "action": "process.manage",
                        "error": reason_c or "human confirm required",
                        "data": {"confirm_required": True, "risk": "high"},
                    }
                session_id = ctx.effective_session_id() if ctx is not None else ""
                workspace_id = str(ctx.workspace_id or "") if ctx is not None else ""
                # Telemetry owner from trusted principal/surface — never model args.
                owner = ""
                if ctx is not None:
                    owner = str(ctx.principal or ctx.surface or "").strip()
                run_id = self.start(
                    argv=list(plan.argv) if plan.argv else None,
                    shell=plan.shell,
                    cwd=plan.cwd,
                    env_id=str(raw.get("environment_id") or raw.get("env_id") or ""),
                    timeout_s=float(raw["timeout_s"]) if raw.get("timeout_s") is not None else None,
                    session_id=session_id,
                    workspace_id=workspace_id,
                    owner=owner,
                )
                if not str(run_id or "").strip():
                    return _manage_err(
                        "start did not return run_id",
                        error_code="run_id_missing",
                        hint=_RUN_ID_HINT,
                    )
                return {
                    "ok": True,
                    "action": "process.manage",
                    "data": self.status(run_id).as_dict(),
                }
            run_id = str(raw.get("run_id") or "").strip()
            if not run_id:
                return _manage_err(
                    "run_id required",
                    error_code="run_id_required",
                    hint=_RUN_ID_HINT,
                )
            if action in _SESSION_SCOPED_ACTIONS:
                slot = self._require(run_id)
                with slot.lock:
                    rec_snap = ProcessRecord(
                        **{
                            **slot.record.as_dict(),
                            "status": ProcessStatus(slot.record.status),
                        }
                    )
                if not self._session_acl_allows(rec_snap, ctx):
                    return {
                        "ok": False,
                        "action": "process.manage",
                        "error": "session denied",
                        "data": {"run_id": run_id},
                    }
            if action == "status":
                return {
                    "ok": True,
                    "action": "process.manage",
                    "data": self.status(run_id).as_dict(),
                }
            if action == "read_output":
                out = self.read_output(
                    run_id,
                    stream=str(raw.get("stream") or "stdout"),
                    offset=int(raw.get("offset") or 0),
                    limit=int(raw["limit"]) if raw.get("limit") is not None else None,
                )
                return {"ok": True, "action": "process.manage", "data": out}
            if action == "wait":
                timeout = raw.get("timeout_s")
                rec = self.wait(
                    run_id,
                    timeout_s=float(timeout) if timeout is not None else None,
                )
                return {"ok": True, "action": "process.manage", "data": rec.as_dict()}
            if action == "cancel":
                rec = self.cancel(run_id)
                return {"ok": True, "action": "process.manage", "data": rec.as_dict()}
        except KeyError as exc:
            return {
                "ok": False,
                "action": "process.manage",
                "error": str(exc),
                "data": {"error_code": "unknown_run_id", "hint": _RUN_ID_HINT},
            }
        except ValueError as exc:
            msg = str(exc) or type(exc).__name__
            if "exactly one of argv or shell" in msg:
                return _manage_err(
                    msg,
                    error_code="start_xor_required",
                    hint=_START_XOR_HINT,
                )
            return {
                "ok": False,
                "action": "process.manage",
                "error": msg,
                "data": {"error_code": "invalid_arguments", "hint": msg},
            }
        except Exception as exc:  # noqa: BLE001 — control boundary
            return {
                "ok": False,
                "action": "process.manage",
                "error": str(exc) or type(exc).__name__,
                "data": {},
            }
        return {
            "ok": False,
            "action": "process.manage",
            "error": f"unhandled action: {action}",
            "data": {},
        }

    def _require(self, run_id: str) -> _RunSlot:
        with self._lock:
            slot = self._slots.get(run_id)
        if slot is None:
            raise KeyError(f"unknown run_id: {run_id}")
        return slot

    def _write_meta(self, slot: _RunSlot) -> None:
        meta = slot.run_dir / "meta.json"
        try:
            with slot.lock:
                payload = slot.record.as_dict()
            meta.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _dir_bytes(self, path: Path) -> int:
        total = 0
        try:
            for root, _dirs, files in os.walk(path):
                for name in files:
                    try:
                        total += (Path(root) / name).stat().st_size
                    except OSError:
                        pass
        except OSError:
            pass
        return total

    def _prune_runs_root(self) -> None:
        """Drop oldest run dirs under max_runs / max_age_s / max_bytes.

        Skips still-active (non-terminal) slots so a live pump is not deleted mid-run.
        Terminal slots may lose their on-disk dir; in-memory status remains.
        """
        root = self.runs_root
        if not root.is_dir():
            return
        with self._lock:
            active = {
                rid
                for rid, slot in self._slots.items()
                if str(slot.record.status.value if hasattr(slot.record.status, "value") else slot.record.status)
                not in _TERMINAL
            }
        now = time.time()
        entries: list[tuple[float, Path, int]] = []
        try:
            children = list(root.iterdir())
        except OSError:
            return
        for path in children:
            if not path.is_dir():
                continue
            name = path.name
            if name in active:
                continue
            # Prefer meta-bearing run dirs; still allow oversized pads without meta.
            has_meta = (path / "meta.json").is_file()
            if not has_meta and len(name) < 8:
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            age = now - mtime
            size = self._dir_bytes(path)
            if age > self.max_age_s:
                try:
                    shutil.rmtree(path, ignore_errors=True)
                except OSError:
                    pass
                continue
            entries.append((mtime, path, size))
        entries.sort(key=lambda t: t[0])  # oldest first
        # Leave room for a soon-to-be-created run dir (start calls prune first).
        while len(entries) >= self.max_runs:
            _mtime, path, _sz = entries.pop(0)
            try:
                shutil.rmtree(path, ignore_errors=True)
            except OSError:
                pass
        total = sum(sz for _m, _p, sz in entries)
        while entries and total > self.max_bytes:
            _mtime, path, sz = entries.pop(0)
            try:
                shutil.rmtree(path, ignore_errors=True)
            except OSError:
                pass
            total -= sz

    def _refresh_last_run_compat(self, slot: _RunSlot) -> None:
        """Compat view of *latest* run only — not completion authority for new API.

        Always writes ``run_id=…`` header. Late finish of an older run must not
        overwrite a newer run's compat content.
        """
        try:
            with slot.lock:
                rec = ProcessRecord(
                    **{**slot.record.as_dict(), "status": ProcessStatus(slot.record.status)}
                )
            with self._lock:
                if self._latest_run_id is not None and rec.run_id != self._latest_run_id:
                    return
            compat = self.runs_root / "last_run.log"
            parts: list[str] = [f"run_id={rec.run_id} status={rec.status.value}\n"]
            for path in (Path(rec.stdout_ref), Path(rec.stderr_ref)):
                if path.is_file():
                    parts.append(path.read_text(encoding="utf-8", errors="replace"))
            if rec.exit_code is not None:
                parts.append(f"\nIRIS_EXIT:{rec.exit_code}\n")
            text = "".join(parts)
            with self._lock:
                # Re-check: a newer start may have won between read and write.
                if self._latest_run_id is not None and rec.run_id != self._latest_run_id:
                    return
                compat.write_text(text, encoding="utf-8", errors="replace")
            # Also mirror under project .iris/last_run.log when cwd looks like a project
            if rec.cwd:
                proj = Path(rec.cwd) / ".iris" / "last_run.log"
                try:
                    proj.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(compat, proj)
                except OSError:
                    pass
        except OSError:
            pass


# Alias used by checks / docs.
ExecutionRuntime = ProcessRegistry

_DEFAULT: ProcessRegistry | None = None
_DEFAULT_LOCK = threading.Lock()


def default_runtime() -> ProcessRegistry:
    global _DEFAULT
    with _DEFAULT_LOCK:
        if _DEFAULT is None:
            _DEFAULT = ProcessRegistry()
        return _DEFAULT


def reset_default_runtime_for_tests() -> None:
    global _DEFAULT
    with _DEFAULT_LOCK:
        _DEFAULT = None
