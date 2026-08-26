"""IRIS.exe 진입점 — 항상 프로젝트 최신 소스를 실행한다.

frozen(dist/IRIS.exe)이든 개발 실행이든 `.venv`의 pythonw로 `-m iris`를
띄우므로, 소스 수정이 바로 반영된다. (540MB PyQt 번들 불필요)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        # dist/IRIS.exe → repo root
        if exe.parent.name.lower() == "dist":
            return exe.parent.parent
        return exe.parent
    return Path(__file__).resolve().parent


def _python_candidates(root: Path) -> list[Path]:
    scripts = root / ".venv" / "Scripts"
    return [scripts / "pythonw.exe", scripts / "python.exe"]


def _die(msg: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, msg, "IRIS", 0x10)
    except Exception:
        sys.stderr.write(msg + "\n")
    raise SystemExit(1)


def main() -> None:
    root = _project_root()
    try:
        os.chdir(root)
    except OSError as e:
        _die(f"프로젝트 폴더로 이동 실패:\n{root}\n\n{e}")

    for py in _python_candidates(root):
        if not py.is_file():
            continue
        # 런처는 즉시 종료, GUI는 pythonw가 담당
        subprocess.Popen(
            [str(py), "-m", "iris", *sys.argv[1:]],
            cwd=str(root),
            close_fds=True,
        )
        raise SystemExit(0)

    # venv 없을 때만: 현재 인터프리터로 직접 기동 (개발용)
    if not getattr(sys, "frozen", False):
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from iris.__main__ import main as iris_main

        iris_main()
        return

    _die(
        "IRIS를 실행할 수 없습니다.\n\n"
        f"프로젝트: {root}\n"
        ".venv\\Scripts\\pythonw.exe 가 없습니다.\n"
        "프로젝트 루트에서 venv를 구성한 뒤 다시 실행하세요."
    )


if __name__ == "__main__":
    main()
