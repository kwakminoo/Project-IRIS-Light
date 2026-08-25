"""개발 소스 우선 실행 — frozen EXE도 저장소 .venv가 있으면 최신 코드로 넘긴다."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def looks_like_repo(root: Path) -> bool:
    return (root / "iris" / "__main__.py").is_file()


def resolve_repo_root_from_frozen() -> Path | None:
    """dist/IRIS.exe 또는 cwd 기준으로 저장소 루트."""
    exe = Path(sys.executable).resolve()
    candidates: list[Path] = []
    if exe.parent.name.lower() == "dist":
        candidates.append(exe.parent.parent)
    candidates.append(Path.cwd().resolve())
    # 바로가기 WorkingDirectory=dist 인 경우
    if exe.parent.name.lower() == "dist":
        candidates.append(exe.parent)
    seen: set[Path] = set()
    for raw in candidates:
        root = raw
        if root.name.lower() == "dist" and looks_like_repo(root.parent):
            root = root.parent
        if root in seen:
            continue
        seen.add(root)
        if looks_like_repo(root):
            return root
    return None


def resolve_venv_python(root: Path) -> Path | None:
    """소스 실행용 인터프리터 (.venv 우선)."""
    win = [
        root / ".venv" / "Scripts" / "pythonw.exe",
        root / ".venv" / "Scripts" / "python.exe",
    ]
    unix = [
        root / ".venv" / "bin" / "python",
        root / ".venv" / "bin" / "python3",
    ]
    for path in win + unix:
        if path.is_file():
            return path
    return None


def should_prefer_source() -> bool:
    """frozen이면 기본적으로 소스 hop. IRIS_FORCE_FROZEN=1 이면 유지."""
    if not getattr(sys, "frozen", False):
        return False
    if _env_truthy("IRIS_FORCE_FROZEN"):
        return False
    return True


def reexec_to_source_if_available() -> bool:
    """가능하면 .venv 로 `python -m iris` 재기동. True면 호출측은 즉시 종료."""
    if not should_prefer_source():
        return False
    root = resolve_repo_root_from_frozen()
    if root is None:
        return False
    py = resolve_venv_python(root)
    if py is None:
        return False
    env = os.environ.copy()
    env["IRIS_LAUNCHED_FROM_EXE"] = "1"
    # hop 루프 방지 — 자식은 non-frozen
    env.pop("IRIS_FORCE_FROZEN", None)
    kwargs: dict = {
        "cwd": str(root),
        "env": env,
        "close_fds": True,
    }
    if sys.platform == "win32" and py.name.lower() == "python.exe":
        kwargs["creationflags"] = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        subprocess.Popen([str(py), "-m", "iris", *sys.argv[1:]], **kwargs)
    except OSError:
        return False
    return True
