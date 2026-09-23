"""GitHub main 대비 앱 소스 업데이트 감지·적용.

설치본(.git 없음)은 zip 오버레이, 개발본은 git fetch/ff-only.
.venv · .env · 사용자 로그는 덮어쓰지 않는다.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from iris.system.hermes_iris_control_sync import iris_state_dir, project_root

GITHUB_OWNER = "kwakminoo"
GITHUB_REPO = "Project-IRIS-Light"
GITHUB_REF = "main"
USER_AGENT = "IRIS-Light-Update/0.1"

_PRESERVE_NAMES = frozenset(
    {
        ".venv",
        ".venv-voice",
        ".env",
        "setup-log.txt",
        "setup-log-pip.txt",
        "setup-fail-reason.txt",
        "REVISION",
        ".iris_light_test_tmp",
    }
)


@dataclass(frozen=True)
class UpdateStatus:
    available: bool
    local_sha: str = ""
    remote_sha: str = ""
    detail: str = ""


def revision_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "REVISION"


def update_state_path() -> Path:
    return iris_state_dir() / "update_state.json"


def _load_state() -> dict[str, Any]:
    path = update_state_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_state(data: dict[str, Any]) -> None:
    path = update_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_local_sha(root: Path | None = None) -> str:
    repo = root or project_root()
    git_dir = repo / ".git"
    if git_dir.exists():
        try:
            proc = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            if proc.returncode == 0:
                sha = (proc.stdout or "").strip()
                if sha:
                    return sha
        except (OSError, subprocess.TimeoutExpired):
            pass
    rev = revision_path(repo)
    if rev.is_file():
        try:
            return rev.read_text(encoding="utf-8").strip().split()[0]
        except OSError:
            pass
    remembered = str(_load_state().get("local_sha") or "").strip()
    return remembered


def write_local_sha(sha: str, root: Path | None = None) -> None:
    sha = (sha or "").strip()
    if not sha:
        return
    repo = root or project_root()
    try:
        revision_path(repo).write_text(sha + "\n", encoding="utf-8")
    except OSError:
        pass
    st = _load_state()
    st["local_sha"] = sha
    _save_state(st)


def fetch_remote_sha(*, ref: str = GITHUB_REF, timeout_sec: float = 12.0) -> str:
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/commits/{ref}"
    req = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
        method="GET",
    )
    token = (os.environ.get("IRIS_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urlopen(req, timeout=timeout_sec) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    sha = str(payload.get("sha") or "").strip()
    if not sha:
        raise RuntimeError("GitHub 응답에 sha가 없습니다")
    return sha


def check_for_update(*, root: Path | None = None) -> UpdateStatus:
    """원격 main HEAD와 로컬 리비전 비교."""
    repo = root or project_root()
    try:
        remote = fetch_remote_sha()
    except (HTTPError, URLError, TimeoutError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        return UpdateStatus(available=False, detail=f"원격 확인 실패: {exc}"[:200])
    local = read_local_sha(repo)
    if not local:
        # 최초: 현재 원격으로 기준만 잡고 프롬프트는 생략
        write_local_sha(remote, repo)
        return UpdateStatus(
            available=False,
            local_sha=remote,
            remote_sha=remote,
            detail="최초 기준 리비전 기록",
        )
    if local == remote:
        return UpdateStatus(
            available=False,
            local_sha=local,
            remote_sha=remote,
            detail="최신",
        )
    # git 개발본: 로컬이 원격의 조상일 때만(뒤처짐) 안내. 앞서면 무시.
    if (repo / ".git").exists():
        try:
            proc = subprocess.run(
                ["git", "-C", str(repo), "merge-base", "--is-ancestor", local, remote],
                capture_output=True,
                timeout=20,
                check=False,
            )
            if proc.returncode != 0:
                return UpdateStatus(
                    available=False,
                    local_sha=local,
                    remote_sha=remote,
                    detail="로컬이 앞서 있거나 분기됨",
                )
        except (OSError, subprocess.TimeoutExpired):
            pass
    return UpdateStatus(
        available=True,
        local_sha=local,
        remote_sha=remote,
        detail=f"{local[:7]} → {remote[:7]}",
    )


def _git_ff_update(repo: Path, remote_sha: str) -> None:
    cmds = [
        ["git", "-C", str(repo), "fetch", "origin", GITHUB_REF],
        ["git", "-C", str(repo), "merge", "--ff-only", f"origin/{GITHUB_REF}"],
    ]
    for cmd in cmds:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()[:240]
            raise RuntimeError(f"git 실패 ({' '.join(cmd[3:])}): {err or proc.returncode}")
    # 실제 HEAD 기록 (로컬이 앞서면 ff-only가 no-op일 수 있음)
    write_local_sha(read_local_sha(repo) or remote_sha, repo)


def _should_preserve(name: str) -> bool:
    return name in _PRESERVE_NAMES or name.endswith(".pyc")


def _overlay_tree(src: Path, dest: Path) -> None:
    for item in src.iterdir():
        if _should_preserve(item.name):
            continue
        target = dest / item.name
        if item.is_dir():
            if target.is_file():
                target.unlink()
            target.mkdir(parents=True, exist_ok=True)
            _overlay_tree(item, target)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


def _zip_overlay_update(repo: Path, remote_sha: str) -> None:
    url = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/archive/refs/heads/{GITHUB_REF}.zip"
    req = Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    with tempfile.TemporaryDirectory(prefix="iris-upd-") as tmp:
        tmp_path = Path(tmp)
        zip_path = tmp_path / "src.zip"
        with urlopen(req, timeout=120) as resp, zip_path.open("wb") as out:
            shutil.copyfileobj(resp, out)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp_path)
        roots = [p for p in tmp_path.iterdir() if p.is_dir() and p.name.startswith(GITHUB_REPO)]
        if not roots:
            raise RuntimeError("압축 해제 루트를 찾지 못했습니다")
        _overlay_tree(roots[0], repo)
    write_local_sha(remote_sha, repo)


def apply_update(*, root: Path | None = None, remote_sha: str = "") -> str:
    """소스를 원격 기준으로 맞춘다. 성공 메시지 반환."""
    repo = root or project_root()
    sha = (remote_sha or "").strip() or fetch_remote_sha()
    if (repo / ".git").exists():
        _git_ff_update(repo, sha)
        return f"git 업데이트 완료 ({sha[:7]})"
    _zip_overlay_update(repo, sha)
    return f"소스 업데이트 완료 ({sha[:7]})"


def _self_check() -> None:
    assert not UpdateStatus(available=False).available
    st = UpdateStatus(available=True, local_sha="aaa", remote_sha="bbb")
    assert st.available and st.detail == ""
    assert revision_path(Path(".")).name == "REVISION"
    assert "bge" not in GITHUB_REPO
    print("app_update ok")


if __name__ == "__main__":
    _self_check()
