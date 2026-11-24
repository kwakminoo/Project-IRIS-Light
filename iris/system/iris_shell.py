"""Iris Shell — scoped subprocess for the home (non-IDE) surface.

No visible console window. Output is for chat ToolShellBlock, not a terminal UI.
IDE-bound project commands stay on project.run.

Runs register on the shared Execution Runtime so process.manage can list/status them.
"""

from __future__ import annotations

import os
import shlex
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from iris.system.execution_runtime import ProcessStatus, default_runtime

_MAX_CAPTURE = 32_768
_DEFAULT_TIMEOUT_S = 60.0
_MAX_TIMEOUT_S = 300.0
_TERMINAL = frozenset(
    {
        ProcessStatus.COMPLETED,
        ProcessStatus.FAILED,
        ProcessStatus.CANCELLED,
        ProcessStatus.TIMED_OUT,
        ProcessStatus.INTERRUPTED,
    }
)


@dataclass(frozen=True)
class ShellJob:
    command: str
    cwd: Path
    timeout_s: float = _DEFAULT_TIMEOUT_S


@dataclass(frozen=True)
class ShellOutcome:
    ok: bool
    command: str
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    via: str = "iris_shell"
    summary: str = ""
    truncated: bool = False
    run_id: str = ""
    status: str = ""
    stdout_ref: str = ""
    stderr_ref: str = ""


def default_shell_cwd() -> Path:
    return Path.home().resolve()


def resolve_shell_cwd(raw: object | None) -> Path:
    """Absolute cwd under the user home. Empty → home."""
    text = str(raw or "").strip()
    if not text:
        return default_shell_cwd()
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise ValueError("cwd는 절대경로여야 합니다.")
    resolved = path.resolve()
    home = Path.home().resolve()
    try:
        resolved.relative_to(home)
    except ValueError as exc:
        raise ValueError("cwd는 사용자 홈 아래만 허용됩니다.") from exc
    if not resolved.is_dir():
        raise NotADirectoryError(str(resolved))
    return resolved


def parse_shell_job(args: dict) -> ShellJob:
    command = str((args or {}).get("command") or (args or {}).get("cmd") or "").strip()
    if not command:
        raise ValueError("command가 필요합니다.")
    try:
        timeout_s = float((args or {}).get("timeout_s") or (args or {}).get("timeout") or _DEFAULT_TIMEOUT_S)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout_s가 올바르지 않습니다.") from exc
    timeout_s = max(1.0, min(timeout_s, _MAX_TIMEOUT_S))
    cwd = resolve_shell_cwd((args or {}).get("cwd"))
    return ShellJob(command=command, cwd=cwd, timeout_s=timeout_s)


def _clip(text: str, limit: int = _MAX_CAPTURE) -> tuple[str, bool]:
    raw = text or ""
    if len(raw) <= limit:
        return raw, False
    return raw[:limit] + "…", True


def _shell_argv(command: str) -> list[str]:
    if os.name == "nt":
        return ["cmd", "/c", command]
    return ["sh", "-c", command]


def _outcome_from_record(
    *,
    job: ShellJob,
    run_id: str,
    rec,
    stdout: str,
    stderr: str,
    truncated: bool,
    summary_override: str = "",
) -> ShellOutcome:
    status = rec.status.value if hasattr(rec.status, "value") else str(rec.status)
    code = int(rec.exit_code) if rec.exit_code is not None else -1
    if status == ProcessStatus.TIMED_OUT.value:
        return ShellOutcome(
            ok=False,
            command=job.command,
            cwd=str(job.cwd),
            exit_code=-1,
            stdout=stdout,
            stderr=stderr or f"timeout after {job.timeout_s}s",
            summary=summary_override or f"timeout · {job.timeout_s}s",
            truncated=truncated,
            run_id=run_id,
            status=status,
            stdout_ref=str(rec.stdout_ref or ""),
            stderr_ref=str(rec.stderr_ref or ""),
        )
    if status in (ProcessStatus.CANCELLED.value, ProcessStatus.INTERRUPTED.value):
        return ShellOutcome(
            ok=False,
            command=job.command,
            cwd=str(job.cwd),
            exit_code=-1,
            stdout=stdout,
            stderr=stderr,
            summary=summary_override or "cancelled",
            truncated=truncated,
            run_id=run_id,
            status=status,
            stdout_ref=str(rec.stdout_ref or ""),
            stderr_ref=str(rec.stderr_ref or ""),
        )
    ok = code == 0 and status == ProcessStatus.COMPLETED.value
    return ShellOutcome(
        ok=ok,
        command=job.command,
        cwd=str(job.cwd),
        exit_code=code,
        stdout=stdout,
        stderr=stderr,
        summary=summary_override or f"exit {code} · {'ok' if ok else 'fail'}",
        truncated=truncated,
        run_id=run_id,
        status=status,
        stdout_ref=str(rec.stdout_ref or ""),
        stderr_ref=str(rec.stderr_ref or ""),
    )


def run_shell_job(
    job: ShellJob,
    *,
    session_id: str = "",
    workspace_id: str = "",
    owner: str = "shell.run",
) -> ShellOutcome:
    """Run one command via Execution Runtime. Never opens a console window."""
    rt = default_runtime()
    argv = _shell_argv(job.command)
    try:
        run_id = rt.start(
            argv=argv,
            cwd=str(job.cwd),
            timeout_s=job.timeout_s,
            session_id=str(session_id or ""),
            workspace_id=str(workspace_id or ""),
            owner=str(owner or "shell.run"),
        )
    except OSError as exc:
        return ShellOutcome(
            ok=False,
            command=job.command,
            cwd=str(job.cwd),
            exit_code=-1,
            stdout="",
            stderr=str(exc),
            summary="spawn failed",
        )
    except ValueError as exc:
        return ShellOutcome(
            ok=False,
            command=job.command,
            cwd=str(job.cwd),
            exit_code=-1,
            stdout="",
            stderr=str(exc),
            summary="spawn failed",
        )
    rec = rt.wait(run_id, timeout_s=float(job.timeout_s) + 5.0)
    out = rt.read_output(run_id, stream="stdout")
    err = rt.read_output(run_id, stream="stderr")
    stdout, t_out = _clip(str(out.get("text") or ""))
    stderr, t_err = _clip(str(err.get("text") or ""))
    return _outcome_from_record(
        job=job,
        run_id=run_id,
        rec=rec,
        stdout=stdout,
        stderr=stderr,
        truncated=t_out or t_err,
    )


def stream_shell_job(
    job: ShellJob,
    on_chunk: Callable[[str], None],
    *,
    cancel_event: threading.Event | None = None,
    session_id: str = "",
    workspace_id: str = "",
    owner: str = "shell.run",
) -> ShellOutcome:
    """Stream one Runtime-backed command; paint live output via on_chunk.

    Chunks are stdout text for chat. ``on_chunk`` may be called from this thread.
    """
    rt = default_runtime()
    argv = _shell_argv(job.command)
    try:
        run_id = rt.start(
            argv=argv,
            cwd=str(job.cwd),
            timeout_s=job.timeout_s,
            session_id=str(session_id or ""),
            workspace_id=str(workspace_id or ""),
            owner=str(owner or "shell.run"),
        )
    except (OSError, ValueError) as exc:
        return ShellOutcome(
            ok=False,
            command=job.command,
            cwd=str(job.cwd),
            exit_code=-1,
            stdout="",
            stderr=str(exc),
            summary="spawn failed",
        )

    parts: list[str] = []
    parts_len = 0
    hit_limit = False
    offset = 0
    deadline = time.monotonic() + float(job.timeout_s) + 5.0
    cancelled = False

    while True:
        if cancel_event is not None and cancel_event.is_set():
            cancelled = True
            try:
                rt.cancel(run_id)
            except Exception:
                pass
            break
        chunk_info = rt.read_output(run_id, stream="stdout", offset=offset)
        text = str(chunk_info.get("text") or "")
        if text:
            emit = text
            if parts_len >= _MAX_CAPTURE:
                hit_limit = True
            else:
                room = _MAX_CAPTURE - parts_len
                if len(text) > room:
                    emit = text[:room]
                    hit_limit = True
                parts.append(emit)
                parts_len += len(emit)
                on_chunk(emit)
            offset = int(chunk_info.get("offset") or 0) + len(text)
        rec = rt.status(run_id)
        if rec.status in _TERMINAL:
            break
        if time.monotonic() >= deadline:
            # Soft wait timeout — Runtime may still mark timed_out via start timeout_s.
            snap = rt.wait(run_id, timeout_s=0.05)
            if snap.status not in _TERMINAL:
                try:
                    rt.cancel(run_id)
                except Exception:
                    pass
            break
        time.sleep(0.05)

    rec = rt.status(run_id)
    if cancelled and rec.status not in _TERMINAL:
        try:
            rec = rt.cancel(run_id)
        except Exception:
            pass
    # Final stdout flush
    final = rt.read_output(run_id, stream="stdout", offset=offset)
    more = str(final.get("text") or "")
    if more and parts_len < _MAX_CAPTURE:
        room = _MAX_CAPTURE - parts_len
        emit = more[:room]
        if len(more) > room:
            hit_limit = True
        parts.append(emit)
        parts_len += len(emit)
        on_chunk(emit)
    err = rt.read_output(run_id, stream="stderr")
    raw = "".join(parts)
    stdout, clipped = _clip(raw)
    stderr, _ = _clip(str(err.get("text") or ""))
    truncated = hit_limit or clipped
    if cancelled:
        return _outcome_from_record(
            job=job,
            run_id=run_id,
            rec=rec,
            stdout=stdout,
            stderr=stderr,
            truncated=truncated,
            summary_override="cancelled",
        )
    return _outcome_from_record(
        job=job,
        run_id=run_id,
        rec=rec,
        stdout=stdout,
        stderr=stderr,
        truncated=truncated,
    )


def outcome_as_result(outcome: ShellOutcome) -> dict:
    return {
        "command": outcome.command,
        "cwd": outcome.cwd,
        "exit_code": outcome.exit_code,
        "stdout": outcome.stdout,
        "stderr": outcome.stderr,
        "via": outcome.via,
        "summary": outcome.summary,
        "truncated": outcome.truncated,
        "run_id": outcome.run_id,
        "status": outcome.status,
        "stdout_ref": outcome.stdout_ref,
        "stderr_ref": outcome.stderr_ref,
        "argv": shlex.split(outcome.command, posix=os.name != "nt")
        if outcome.command
        else [],
    }
