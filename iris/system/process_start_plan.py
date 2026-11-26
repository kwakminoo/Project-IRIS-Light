"""Finalized process.manage start plan — one shape for card grant and ledger consume.

cwd is resolved, argv XOR shell is bound, fingerprint inputs match what will run.
RequestApprovalLedger stays the only approval system.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from iris.system.execution_policy import check_process_start_cwd
from iris.system.request_approval import normalize_execution_fingerprint

_START_XOR_HINT = (
    "Provide exactly one of argv (list of strings) or shell (string; command alias ok)"
)


@dataclass(frozen=True)
class FinalizedStartPlan:
    cwd: str
    argv: list[str] | None
    shell: str | None
    env: tuple[tuple[str, str], ...] | None = None

    def fingerprint(self) -> str:
        env_map = dict(self.env) if self.env else None
        return normalize_execution_fingerprint(
            argv=list(self.argv) if self.argv is not None else None,
            shell=self.shell,
            cwd=self.cwd,
            env=env_map,
        )

    def preview(self) -> str:
        if self.argv:
            return " ".join(str(x) for x in self.argv)
        text = str(self.shell or "").strip()
        return text or "process.manage start"


@dataclass(frozen=True)
class FinalizeStartFailure:
    error: str
    error_code: str
    hint: str
    data: dict[str, Any]


def normalize_process_start_args(
    raw: Mapping[str, Any],
) -> tuple[list[str] | None, str | None]:
    """Boundary parse for process.manage start.

    - list argv kept as argv
    - non-list argv string → shell only when shell/command absent (never drop shell)
    - other argv types ignored
    - shell/command alias: first non-empty wins
    Caller still enforces XOR before ExecutionRuntime.start.
    """
    shell_raw = raw.get("shell")
    if shell_raw is None or not str(shell_raw).strip():
        shell_raw = raw.get("command")
    shell: str | None = (
        str(shell_raw).strip()
        if shell_raw is not None and str(shell_raw).strip()
        else None
    )

    argv_raw = raw.get("argv")
    argv: list[str] | None = None
    if isinstance(argv_raw, list):
        if argv_raw:
            argv = [str(x) for x in argv_raw]
    elif isinstance(argv_raw, str) and argv_raw.strip():
        if shell is None:
            shell = argv_raw.strip()
    return argv, shell


def _resolve_start_cwd(
    raw_cwd: Any,
    *,
    workspace_root: str | None,
) -> str:
    text = str(raw_cwd or "").strip()
    ws = str(workspace_root or "").strip()
    if ws:
        root = Path(ws).expanduser().resolve()
        if text:
            return str(Path(text).expanduser().resolve())
        return str(root)
    if text:
        return str(Path(text).expanduser().resolve())
    return str(Path.home().resolve())


def _env_tuple(raw: Mapping[str, Any]) -> tuple[tuple[str, str], ...] | None:
    env = raw.get("env")
    if not isinstance(env, Mapping) or not env:
        return None
    return tuple(
        (str(k), str(v)) for k, v in sorted(env.items(), key=lambda kv: str(kv[0]))
    )


def finalize_process_start_plan(
    raw: Mapping[str, Any] | None,
    *,
    workspace_root: str | None = None,
) -> FinalizedStartPlan | FinalizeStartFailure:
    """Resolve cwd, bind argv XOR shell. Call before grant and before ledger consume."""
    args = dict(raw or {})
    ws = str(workspace_root or "").strip() or None
    cwd_decision = check_process_start_cwd(
        args.get("cwd"),
        workspace_root=ws,
    )
    if not cwd_decision.allowed:
        return FinalizeStartFailure(
            error=cwd_decision.reason or "cwd denied",
            error_code="cwd_denied",
            hint="cwd must stay under trusted workspace root or home",
            data={},
        )
    cwd_final = _resolve_start_cwd(args.get("cwd"), workspace_root=ws)
    bound_argv, shell = normalize_process_start_args(args)
    has_argv = bool(bound_argv)
    has_shell = bool(shell)
    if has_argv == has_shell:
        return FinalizeStartFailure(
            error="start requires exactly one of argv or shell",
            error_code="start_xor_required",
            hint=_START_XOR_HINT,
            data={"argv_present": has_argv, "shell_present": has_shell},
        )
    if bound_argv:
        from iris.system.workspace_env import bind_execution_argv

        bound_argv = bind_execution_argv(
            bound_argv,
            project_root=cwd_final,
            allow_create=False,
        )
    return FinalizedStartPlan(
        cwd=cwd_final,
        argv=list(bound_argv) if bound_argv else None,
        shell=shell if has_shell else None,
        env=_env_tuple(args),
    )
