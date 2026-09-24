"""IRIS.exe 진입점 — 항상 프로젝트 최신 소스를 실행한다.

frozen(dist/IRIS.exe)이든 개발 실행이든 `.venv`의 pythonw로 `-m iris`를
띄우므로, 소스 수정이 바로 반영된다. (540MB PyQt 번들 불필요)

pythonw는 콘솔이 없어서 기동 실패가 어디에도 남지 않는다. 그래서 자식의
출력을 로그로 받아 두고, 뜨자마자 죽으면 그 이유를 창으로 보여 준다.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# 정상 기동이면 이 시간 안에 끝나지 않는다 — 즉사만 걸러 내는 값
STARTUP_GRACE_SEC = 10.0
LOG_TAIL_CHARS = 1500


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


def _log_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or ""
    home = Path(base) / "iris-light" if base else Path.home() / ".iris-light"
    try:
        home.mkdir(parents=True, exist_ok=True)
    except OSError:
        return Path(os.environ.get("TEMP") or ".") / "iris-launcher.log"
    return home / "launcher.log"


def _die(msg: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, msg, "IRIS", 0x10)
    except Exception:
        sys.stderr.write(msg + "\n")
    raise SystemExit(1)


def _diagnose(log_text: str) -> str:
    """로그 꼬리에서 흔한 실패를 사람 말로 옮긴다."""
    # import 실패는 따옴표가 붙고(`'PyQt6.QtCore'`), `-m iris` 실패는 안 붙는다
    missing = re.search(r"No module named '?([\w.]+)'?", log_text)
    if missing:
        return (
            f"'{missing.group(1)}' 패키지가 없습니다 — 의존성 설치가 끝나지 않았습니다.\n"
            "폴더의 setup.bat 을 다시 실행해 주세요."
        )
    if "DLL load failed" in log_text:
        return (
            "PyQt6 DLL 을 불러오지 못했습니다.\n"
            "Visual C++ 재배포 패키지를 설치한 뒤 다시 실행하세요:\n"
            "winget install -e --id Microsoft.VCRedist.2015+.x64"
        )
    last = [ln.strip() for ln in log_text.splitlines() if ln.strip()]
    if last:
        return f"오류: {last[-1]}\n\nsetup.bat 을 다시 실행하면 대부분 해결됩니다."
    return "setup.bat 을 다시 실행하면 대부분 해결됩니다."


def _run_and_watch(py: Path, root: Path) -> subprocess.Popen:
    """자식을 띄우고 유예 시간만 지켜본다. 살아 있으면 조용히 손을 뗀다."""
    log = _log_path()
    try:
        sink = open(log, "w", encoding="utf-8", errors="replace")
    except OSError:
        sink = None

    proc = subprocess.Popen(
        [str(py), "-m", "iris", *sys.argv[1:]],
        cwd=str(root),
        close_fds=True,
        stdout=sink if sink is not None else subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    if sink is not None:
        sink.close()

    try:
        rc = proc.wait(timeout=STARTUP_GRACE_SEC)
    except subprocess.TimeoutExpired:
        return proc  # 창이 떴다
    if rc == 0:
        return proc

    tail = ""
    if sink is not None:
        try:
            tail = log.read_text(encoding="utf-8", errors="replace")[-LOG_TAIL_CHARS:]
        except OSError:
            pass
    _die(f"IRIS를 시작하지 못했습니다.\n\n{_diagnose(tail)}\n\n로그: {log}")
    return proc


def main() -> None:
    root = _project_root()
    try:
        os.chdir(root)
    except OSError as e:
        _die(f"프로젝트 폴더로 이동 실패:\n{root}\n\n{e}")

    venv_cfg = root / ".venv" / "pyvenv.cfg"
    scripts = root / ".venv" / "Scripts"
    has_py = (scripts / "pythonw.exe").is_file() or (scripts / "python.exe").is_file()
    if has_py and not venv_cfg.is_file():
        _die(
            "IRIS를 시작하지 못했습니다.\n\n"
            "가상환경이 깨져 있습니다 (No pyvenv.cfg).\n"
            "설치 폴더의 setup.bat 을 다시 실행하세요.\n"
            "그래도 안 되면 PowerShell에서:\n"
            f"  cd /d {root}\n"
            "  .\\setup.ps1 -Recreate\n\n"
            f"프로젝트: {root}"
        )

    for py in _python_candidates(root):
        if not py.is_file():
            continue
        _run_and_watch(py, root)
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
        "설치가 끝나지 않았습니다 — 폴더의 setup.bat 을 실행해 주세요."
    )


if __name__ == "__main__":
    main()
