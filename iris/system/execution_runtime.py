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

from iris.system.win_subprocess import no_window_kwargs

MANAGE_ACTIONS = frozenset(
    {
        "start",
        "list",
        "status",
        "read_output",
        "wait",
        "cancel",
        "write_stdin",
    }
)

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


class ProcessRegistry:
    """In-process registry of Local Subprocess runs."""

    def __init__(
        self,
        *,
        runs_root: Path | None = None,
        project_root: str | Path | None = None,
        backend: BackendKind = BackendKind.LOCAL_SUBPROCESS,
    ) -> None:
        self.backend = backend
        self.runs_root = Path(runs_root) if runs_root else default_runs_root(project_root=project_root)
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self._slots: dict[str, _RunSlot] = {}
        self._lock = threading.RLock()
        self._latest_run_id: str | None = None

    def start(
        self,
        *,
        argv: list[str] | None = None,
        shell: str | None = None,
        cwd: str | Path | None = None,
        env_id: str = "",
        env: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
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
        )
        slot = _RunSlot(rec, run_dir)
        with self._lock:
            self._slots[run_id] = slot
            self._latest_run_id = run_id

        popen_env = os.environ.copy()
        if env:
            popen_env.update({str(k): str(v) for k, v in env.items()})
        if env_id:
            popen_env["IRIS_ENVIRONMENT_ID"] = str(env_id)

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
                    if code == 0:
                        slot.record.status = ProcessStatus.COMPLETED
                    else:
                        # Non-zero still "completed" for wait semantics (real exit_code).
                        # failed reserved for spawn/OS errors; keep completed + exit_code.
                        slot.record.status = ProcessStatus.COMPLETED
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

    def list_runs(self) -> list[ProcessRecord]:
        with self._lock:
            ids = list(self._slots.keys())
        return [self.status(i) for i in ids]

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
        ok = slot.done.wait(timeout=None if timeout_s is None else float(timeout_s))
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

    def manage(self, args: Mapping[str, Any] | None) -> dict[str, Any]:
        """process.manage / process_manage dispatcher."""
        raw = dict(args or {})
        action = str(raw.get("action") or "").strip()
        if action not in MANAGE_ACTIONS:
            return {
                "ok": False,
                "action": "process.manage",
                "error": f"unknown or missing action: {action!r}",
                "data": {"allowed": sorted(MANAGE_ACTIONS)},
            }
        try:
            if action == "list":
                runs = [r.as_dict() for r in self.list_runs()]
                return {"ok": True, "action": "process.manage", "data": {"runs": runs}}
            if action == "start":
                argv = raw.get("argv")
                shell = raw.get("shell") or raw.get("command")
                run_id = self.start(
                    argv=list(argv) if isinstance(argv, list) else None,
                    shell=str(shell) if shell and not argv else None,
                    cwd=raw.get("cwd"),
                    env_id=str(raw.get("environment_id") or raw.get("env_id") or ""),
                    timeout_s=float(raw["timeout_s"]) if raw.get("timeout_s") is not None else None,
                )
                return {
                    "ok": True,
                    "action": "process.manage",
                    "data": self.status(run_id).as_dict(),
                }
            run_id = str(raw.get("run_id") or "").strip()
            if not run_id:
                return {
                    "ok": False,
                    "action": "process.manage",
                    "error": "run_id required",
                    "data": {},
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
            if action == "write_stdin":
                stub = self.write_stdin(run_id, str(raw.get("data") or raw.get("text") or ""))
                return {
                    "ok": bool(stub.get("ok")),
                    "action": "process.manage",
                    "error": stub.get("error") or "",
                    "data": stub,
                }
        except KeyError as exc:
            return {
                "ok": False,
                "action": "process.manage",
                "error": str(exc),
                "data": {},
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

    def _refresh_last_run_compat(self, slot: _RunSlot) -> None:
        """Compat view of latest run only — not completion authority for new API."""
        try:
            with slot.lock:
                rec = ProcessRecord(
                    **{**slot.record.as_dict(), "status": ProcessStatus(slot.record.status)}
                )
            compat = self.runs_root / "last_run.log"
            parts: list[str] = [f"run_id={rec.run_id} status={rec.status.value}\n"]
            for path in (Path(rec.stdout_ref), Path(rec.stderr_ref)):
                if path.is_file():
                    parts.append(path.read_text(encoding="utf-8", errors="replace"))
            if rec.exit_code is not None:
                parts.append(f"\nIRIS_EXIT:{rec.exit_code}\n")
            compat.write_text("".join(parts), encoding="utf-8", errors="replace")
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
