"""Node.js 런타임 탐지·설치 — mobile_mcp / IRIS IDE 공용."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

NODE_DOWNLOAD_URL = "https://nodejs.org/en/download"
_MIN_NODE_MAJOR = 22

# Windows winget 설치 후 PATH 미반영 시 흔한 경로
_NODE_PROBE_DIRS: tuple[str, ...] = (
    r"%ProgramFiles%\nodejs",
    r"%ProgramFiles(x86)%\nodejs",
    r"%LOCALAPPDATA%\Programs\nodejs",
    r"%APPDATA%\npm",
)


def _expand(path: str) -> str:
    return os.path.expandvars(os.path.expanduser(path))


def _winget_exe() -> str | None:
    found = shutil.which("winget")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA", "")
    candidate = Path(local) / "Microsoft" / "WindowsApps" / "winget.exe"
    if candidate.is_file():
        return str(candidate)
    return None


def _probe_node_paths() -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in _NODE_PROBE_DIRS:
        d = Path(_expand(raw))
        if not d.is_dir():
            continue
        for name in ("node.exe", "node"):
            p = d / name
            if p.is_file():
                key = str(p.resolve()).lower()
                if key not in seen:
                    seen.add(key)
                    out.append(str(p.resolve()))
    return out


def node_executable() -> str:
    """node 실행 파일 경로. 없으면 빈 문자열."""
    found = shutil.which("node")
    if found and Path(found).is_file():
        return str(Path(found).resolve())
    for p in _probe_node_paths():
        if Path(p).is_file():
            return p
    return ""


def node_major_version(exe: str | None = None) -> int | None:
    """node --version 의 major. 실패 시 None."""
    cmd = exe or node_executable()
    if not cmd:
        return None
    try:
        proc = subprocess.run(
            [cmd, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (proc.stdout or proc.stderr or "").strip()
    m = re.match(r"v?(\d+)", text)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def is_node_ready(*, min_major: int = _MIN_NODE_MAJOR) -> tuple[bool, str]:
    """(ok, detail). major >= min_major."""
    exe = node_executable()
    if not exe:
        return False, "Node.js가 설치되어 있지 않습니다"
    major = node_major_version(exe)
    if major is None:
        return False, "Node.js 버전을 확인할 수 없습니다"
    if major < min_major:
        return False, f"Node.js {min_major} 이상이 필요합니다 (현재 v{major})"
    return True, f"Node v{major} ({exe})"


def yarn_executable() -> str:
    """yarn classic 실행 파일."""
    for name in ("yarn.cmd", "yarn"):
        found = shutil.which(name)
        if found and Path(found).is_file():
            return str(Path(found).resolve())
    npm = shutil.which("npm")
    if npm:
        # corepack / npx yarn 폴백
        return npm  # caller uses npm exec yarn
    return ""


def install_node_winget(
    *,
    run_streamed: Callable[..., Any] | None = None,
    idle_sec: float = 600.0,
    hard_sec: float = 3600.0,
) -> tuple[bool, str]:
    """Windows winget으로 Node LTS 설치. (ok, message)."""
    ok, detail = is_node_ready()
    if ok:
        return True, detail
    if sys.platform != "win32":
        return False, f"Node { _MIN_NODE_MAJOR } 이상을 설치한 뒤 다시 시도하세요."
    winget = _winget_exe()
    if not winget:
        return False, f"winget 없음 — {NODE_DOWNLOAD_URL} 에서 Node {_MIN_NODE_MAJOR}+ 설치"

    cmd = [
        winget,
        "install",
        "-e",
        "--id",
        "OpenJS.NodeJS.LTS",
        "--accept-package-agreements",
        "--accept-source-agreements",
    ]
    try:
        if run_streamed is not None:
            proc = run_streamed(cmd, timeout=idle_sec, hard_timeout=hard_sec, hidden=False)
            code = proc.returncode
            err_tail = (proc.stdout or "")[-200:]
        else:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=hard_sec, check=False)
            code = proc.returncode
            err_tail = (proc.stderr or proc.stdout or "")[-200:]
    except (OSError, subprocess.TimeoutExpired) as exc:
        ok2, detail2 = is_node_ready()
        if ok2:
            return True, f"시간 초과 후 Node 확인됨 ({detail2})"
        return False, f"Node 설치 실패: {exc}"

    ok3, detail3 = is_node_ready()
    if ok3:
        return True, detail3
    if code == 0:
        return False, "Node 설치는 됐지만 PATH에 없습니다. Iris를 재시작한 뒤 다시 시도하세요."
    return False, f"Node 설치 실패: {err_tail}"


def _self_check() -> None:
    exe = node_executable()
    print("node:", exe or "(missing)")
    ok, msg = is_node_ready()
    assert isinstance(ok, bool)
    print("ready:", ok, msg)
    print("node_runtime ok")


if __name__ == "__main__":
    _self_check()
