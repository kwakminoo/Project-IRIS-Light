"""Iris Shell — scoped subprocess for the home (non-IDE) surface.

No visible console window. Output is for chat ToolShellBlock, not a terminal UI.
IDE-bound project commands stay on project.run.
"""

from __future__ import annotations

import os
import shlex
import subprocess
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


def run_shell_job(job: ShellJob) -> ShellOutcome:
    """Run one command with CREATE_NO_WINDOW. Never opens a console window."""
    if os.name == "nt":
        argv = ["cmd", "/c", job.command]
    else:
        argv = ["sh", "-c", job.command]
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
