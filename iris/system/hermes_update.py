"""Iris Agent 런타임이 제품 pin 과 다른지 확인하고, pin 으로 맞춘다.

Nous ``origin/main`` 을 추격하지 않는다. 목표 SHA 는 ``vendor/iris-agent-runtime/PIN``.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from iris.infrastructure.agent_runtime import (
    apply_iris_agent_baseline_overlays,
    load_pinned_sha,
    load_upstream_url,
)
from iris.system.win_subprocess import no_window_kwargs

_UPDATE_TIMEOUT_SEC = 2400.0


@dataclass(frozen=True)
class HermesUpdateStatus:
    available: bool
    local_sha: str = ""
    remote_sha: str = ""
    detail: str = ""
    repo: str = ""


def hermes_repo_dir(command: str = "hermes") -> Path | None:
    """실행 중인 hermes 체크아웃. venv Scripts 위, 없으면 제품 홈/hermes-agent."""
    from iris.infrastructure.hermes_credentials import hermes_home
    from iris.system.hermes_gateway import hermes_executable

    exe = hermes_executable(command)
    if exe:
        for parent in Path(exe).resolve().parents:
            if (parent / ".git").exists() and (parent / "hermes_cli").is_dir():
                return parent
    repo = hermes_home() / "hermes-agent"
    if (repo / ".git").exists():
        return repo
    return None


def _git(repo: Path, *args: str, timeout: float = 25.0) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            **no_window_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def fetch_hermes_remote_sha(repo: Path | None = None) -> str:
    """제품 pin SHA. 네트워크를 타지 않는다 (floating main 금지)."""
    del repo  # pin 은 vendor 가 소유. 로컬 origin/main 무시.
    return load_pinned_sha()


def check_hermes_update(
    *,
    command: str = "hermes",
    repo: Path | None = None,
    remote_sha: str | None = None,
) -> HermesUpdateStatus:
    """로컬 HEAD 와 제품 pin 이 다르면 업데이트 가능.

    ``remote_sha`` 를 넘기면 그 값을 pin 대신 비교한다 (자검용).
    """
    root = repo if repo is not None else hermes_repo_dir(command)
    if root is None or not (root / ".git").exists():
        return HermesUpdateStatus(available=False, detail="Hermes git 설치 없음")
    local = _git(root, "rev-parse", "HEAD", timeout=15.0)
    if not local:
        return HermesUpdateStatus(
            available=False, detail="로컬 리비전 확인 실패", repo=str(root)
        )
    pin = (remote_sha if remote_sha is not None else load_pinned_sha()).strip()
    if not pin:
        return HermesUpdateStatus(
            available=False,
            local_sha=local,
            detail="제품 pin 없음",
            repo=str(root),
        )
    if local.lower() == pin.lower():
        return HermesUpdateStatus(
            available=False,
            local_sha=local,
            remote_sha=pin,
            detail="최신",
            repo=str(root),
        )
    return HermesUpdateStatus(
        available=True,
        local_sha=local,
        remote_sha=pin,
        detail=f"{local[:7]} → {pin[:7]}",
        repo=str(root),
    )


def hermes_update_argv(exe: str) -> list[str]:
    """레거시 UI 자검용. 실제 apply 는 git pin checkout 을 쓴다."""
    return [exe, "update", "--yes"]


def _note(on_progress: Callable[[str], None] | None, msg: str) -> None:
    if on_progress:
        on_progress(msg)


def _checkout_pin(repo: Path, pin: str) -> None:
    url = load_upstream_url()
    remotes = _git(repo, "remote")
    if "origin" not in remotes.split():
        proc = subprocess.run(
            ["git", "-C", str(repo), "remote", "add", "origin", url],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30.0,
            check=False,
            **no_window_kwargs(),
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"git remote add 실패: {(proc.stderr or proc.stdout or '')[-240:]}"
            )
    fetch = subprocess.run(
        ["git", "-C", str(repo), "fetch", "--depth", "1", "origin", pin],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_UPDATE_TIMEOUT_SEC,
        check=False,
        **no_window_kwargs(),
    )
    if fetch.returncode != 0:
        raise RuntimeError(
            f"git fetch pin 실패: {(fetch.stderr or fetch.stdout or '')[-400:]}"
        )
    co = subprocess.run(
        ["git", "-C", str(repo), "checkout", "--force", "FETCH_HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120.0,
        check=False,
        **no_window_kwargs(),
    )
    if co.returncode != 0:
        raise RuntimeError(
            f"git checkout pin 실패: {(co.stderr or co.stdout or '')[-400:]}"
        )
    got = _git(repo, "rev-parse", "HEAD", timeout=15.0)
    if got.lower() != pin.lower():
        raise RuntimeError(f"pin SHA 불일치 want={pin} got={got}")


def apply_hermes_update(
    *,
    command: str = "hermes",
    base_url: str = "",
    api_key: str = "",
    on_progress: Callable[[str], None] | None = None,
) -> str:
    """제품 pin 으로 checkout 한 뒤 baseline overlay 를 적용하고 gateway 를 다시 띄운다.

    Windows 에서 gateway 가 venv 파일을 잠그므로 갱신 전에 먼저 내린다.
    갱신이 실패해도 gateway 는 다시 올리려 한다.
    """
    from iris.system.hermes_gateway import (
        get_last_gateway_diagnosis,
        hermes_executable,
        restart_hermes_gateway,
        stop_hermes_gateway,
    )

    exe = hermes_executable(command)
    if not exe:
        raise RuntimeError("hermes 실행 파일이 없습니다")
    repo = hermes_repo_dir(command)
    if repo is None or not (repo / ".git").exists():
        raise RuntimeError("Hermes git 설치 없음 — pin checkout 불가")

    pin = load_pinned_sha()
    _note(on_progress, "Hermes gateway 중지…")
    stop_hermes_gateway(command, wait_sec=20.0)

    _note(on_progress, f"Iris Agent pin {pin[:7]} checkout…")
    try:
        _checkout_pin(repo, pin)
        apply_iris_agent_baseline_overlays(repo)
    except Exception as exc:
        _restart_after(command, base_url, api_key, on_progress)
        raise RuntimeError(str(exc)) from exc

    _note(on_progress, "Hermes gateway 재시작…")
    ok = restart_hermes_gateway(
        base_url,
        api_key=api_key,
        command=command,
        wait_sec=90.0,
        on_progress=on_progress,
    )
    if not ok:
        diag = get_last_gateway_diagnosis()
        why = (diag.message if diag is not None else "") or "gateway 재시작 실패"
        raise RuntimeError(f"업데이트는 적용됐으나 gateway 재시작 실패: {why[:240]}")
    return "Iris Agent 런타임이 pin에 맞춰졌고 gateway를 재시작했습니다."


def _restart_after(
    command: str,
    base_url: str,
    api_key: str,
    on_progress: Callable[[str], None] | None,
) -> None:
    from iris.system.hermes_gateway import restart_hermes_gateway

    _note(on_progress, "Hermes gateway 재시작…")
    try:
        restart_hermes_gateway(
            base_url,
            api_key=api_key,
            command=command,
            wait_sec=90.0,
            on_progress=on_progress,
        )
    except Exception:
        return
