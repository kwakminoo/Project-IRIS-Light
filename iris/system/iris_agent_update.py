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
    iris_agent_repo_dir,
    load_pinned_sha,
    load_upstream_url,
)
from iris.infrastructure.iris_agent_credentials import iris_agent_home
from iris.system.win_subprocess import no_window_kwargs

_UPDATE_TIMEOUT_SEC = 2400.0


@dataclass(frozen=True)
class IrisAgentUpdateStatus:
    available: bool
    local_sha: str = ""
    remote_sha: str = ""
    detail: str = ""
    repo: str = ""


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


def check_iris_agent_update(
    *,
    command: str = "hermes",
    repo: Path | None = None,
    remote_sha: str | None = None,
) -> IrisAgentUpdateStatus:
    """로컬 HEAD 와 제품 pin 이 다르면 업데이트 가능.

    ``remote_sha`` 를 넘기면 그 값을 pin 대신 비교한다 (자검용).
    """
    root = repo if repo is not None else iris_agent_repo_dir(iris_agent_home())
    if not (root / ".git").exists():
        return IrisAgentUpdateStatus(available=False, detail="Iris Agent git 설치 없음")
    local = _git(root, "rev-parse", "HEAD", timeout=15.0)
    if not local:
        return IrisAgentUpdateStatus(
            available=False, detail="로컬 리비전 확인 실패", repo=str(root)
        )
    pin = (remote_sha if remote_sha is not None else load_pinned_sha()).strip()
    if not pin:
        return IrisAgentUpdateStatus(
            available=False,
            local_sha=local,
            detail="제품 pin 없음",
            repo=str(root),
        )
    if local.lower() == pin.lower():
        return IrisAgentUpdateStatus(
            available=False,
            local_sha=local,
            remote_sha=pin,
            detail="최신",
            repo=str(root),
        )
    return IrisAgentUpdateStatus(
        available=True,
        local_sha=local,
        remote_sha=pin,
        detail=f"{local[:7]} → {pin[:7]}",
        repo=str(root),
    )


def iris_agent_update_argv(exe: str) -> list[str]:
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


def apply_iris_agent_update(
    *,
    command: str = "hermes",
    base_url: str = "",
    api_key: str = "",
    on_progress: Callable[[str], None] | None = None,
) -> str:
    """제품 pin 으로 checkout 한 뒤 baseline overlay 를 적용하고 엔진을 다시 준비한다.

    Windows 에서 옛 gateway 가 venv 파일을 잠글 수 있어 갱신 전에 내리기만 한다.
    HTTP :8642 재기동은 제품 경로에서 하지 않는다.
    """
    _ = (base_url, api_key)  # compat kwargs; gateway restart retired
    from iris.system.iris_agent_gateway import (
        iris_agent_executable,
        stop_hermes_gateway,
    )

    exe = iris_agent_executable(command)
    if not exe:
        raise RuntimeError("Iris Agent 실행 파일이 없습니다")
    repo = iris_agent_repo_dir(iris_agent_home())
    if not (repo / ".git").exists():
        raise RuntimeError("Iris Agent git 설치 없음 — pin checkout 불가")

    pin = load_pinned_sha()
    _note(on_progress, "Iris Agent gateway 중지(파일 잠금 해제)…")
    stop_hermes_gateway(command, wait_sec=20.0)

    _note(on_progress, f"Iris Agent pin {pin[:7]} checkout…")
    try:
        _checkout_pin(repo, pin)
        apply_iris_agent_baseline_overlays(repo)
    except Exception as exc:
        _ensure_engine_after(on_progress)
        raise RuntimeError(str(exc)) from exc

    _ensure_engine_after(on_progress)
    return (
        "Iris Agent 런타임이 pin에 맞춰졌습니다. "
        "(HTTP gateway 재시작은 사용하지 않음)"
    )


def _ensure_engine_after(
    on_progress: Callable[[str], None] | None,
) -> None:
    from iris.engine import EngineFailed, shared_engine
    from iris.engine.runtime import reset_shared_engine

    _note(on_progress, "Iris Agent 엔진 준비…")
    try:
        reset_shared_engine()
        result = shared_engine().ensure_ready()
    except Exception:
        return
    if isinstance(result, EngineFailed):
        _note(
            on_progress,
            f"엔진 준비 실패(디스크는 갱신됨): "
            f"{(result.error.detail or result.user_message)[:160]}",
        )
