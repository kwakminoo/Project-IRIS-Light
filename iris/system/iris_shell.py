"""Iris Shell — scoped subprocess for the home (non-IDE) surface.

No visible console window. Output is for chat ToolShellBlock, not a terminal UI.
IDE-bound project commands stay on project.run.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from iris.system.win_subprocess import no_window_kwargs

_MAX_CAPTURE = 32_768
_DEFAULT_TIMEOUT_S = 60.0
_MAX_TIMEOUT_S = 300.0


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


def _terminate_proc(proc: subprocess.Popen[str]) -> None:
    try:
        proc.terminate()
    except OSError:
        return
    try:
        proc.wait(timeout=1.5)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass
        try:
            proc.wait(timeout=1.5)
        except (subprocess.TimeoutExpired, OSError):
            pass


def run_shell_job(job: ShellJob) -> ShellOutcome:
    """Run one command with CREATE_NO_WINDOW. Never opens a console window."""
    argv = _shell_argv(job.command)
    try:
        completed = subprocess.run(
            argv,
            cwd=str(job.cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=job.timeout_s,
            **no_window_kwargs(),
        )
    except subprocess.TimeoutExpired as exc:
        out, t1 = _clip(str(exc.stdout or ""))
        err, t2 = _clip(str(exc.stderr or "") or f"timeout after {job.timeout_s}s")
        return ShellOutcome(
            ok=False,
            command=job.command,
            cwd=str(job.cwd),
            exit_code=-1,
            stdout=out,
            stderr=err,
            summary=f"timeout · {job.timeout_s}s",
            truncated=t1 or t2,
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
    stdout, t_out = _clip(completed.stdout or "")
    stderr, t_err = _clip(completed.stderr or "")
    code = int(completed.returncode)
    ok = code == 0
    return ShellOutcome(
        ok=ok,
        command=job.command,
        cwd=str(job.cwd),
        exit_code=code,
        stdout=stdout,
        stderr=stderr,
        summary=f"exit {code} · {'ok' if ok else 'fail'}",
        truncated=t_out or t_err,
    )


def stream_shell_job(
    job: ShellJob,
    on_chunk: Callable[[str], None],
    *,
    cancel_event: threading.Event | None = None,
) -> ShellOutcome:
    """Stream one command; paint live output via on_chunk.

    Chunks are merged plain text (stderr redirected to stdout) for chat.
    ``on_chunk`` may be called from a reader thread — keep it thread-safe
    and non-blocking. Windows uses CREATE_NO_WINDOW / no_window_kwargs.
    """
    argv = _shell_argv(job.command)
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(job.cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            **no_window_kwargs(),
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

    parts: list[str] = []
    parts_len = 0
    hit_limit = False
    lock = threading.Lock()

    def reader() -> None:
        nonlocal parts_len, hit_limit
        stream = proc.stdout
        if stream is None:
            return
        while True:
            chunk = stream.readline()
            if chunk == "":
                break
            emit = chunk
            with lock:
                if parts_len >= _MAX_CAPTURE:
                    hit_limit = True
                    continue
                room = _MAX_CAPTURE - parts_len
                if len(chunk) > room:
                    emit = chunk[:room]
                    hit_limit = True
                parts.append(emit)
                parts_len += len(emit)
            on_chunk(emit)

    thread = threading.Thread(target=reader, name="iris-shell-stream", daemon=True)
    thread.start()

    deadline = time.monotonic() + float(job.timeout_s)
    timed_out = False
    cancelled = False
    while proc.poll() is None:
        if cancel_event is not None and cancel_event.is_set():
            cancelled = True
            _terminate_proc(proc)
            break
        if time.monotonic() >= deadline:
            timed_out = True
            _terminate_proc(proc)
            break
        time.sleep(0.05)

    try:
        proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        _terminate_proc(proc)
    thread.join(timeout=5.0)

    with lock:
        raw = "".join(parts)
    stdout, clipped = _clip(raw)
    truncated = hit_limit or clipped
    code = int(proc.returncode if proc.returncode is not None else -1)

    if cancelled:
        return ShellOutcome(
            ok=False,
            command=job.command,
            cwd=str(job.cwd),
            exit_code=-1,
            stdout=stdout,
            stderr="",
            summary="cancelled",
            truncated=truncated,
        )
    if timed_out:
        return ShellOutcome(
            ok=False,
            command=job.command,
            cwd=str(job.cwd),
            exit_code=-1,
            stdout=stdout,
            stderr=f"timeout after {job.timeout_s}s",
            summary=f"timeout · {job.timeout_s}s",
            truncated=truncated,
        )
    ok = code == 0
    return ShellOutcome(
        ok=ok,
        command=job.command,
        cwd=str(job.cwd),
        exit_code=code,
        stdout=stdout,
        stderr="",
        summary=f"exit {code} · {'ok' if ok else 'fail'}",
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
        "argv": shlex.split(outcome.command, posix=os.name != "nt")
        if outcome.command
        else [],
    }
