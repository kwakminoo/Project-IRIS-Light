"""관리자 권한으로 Iris 재실행."""

from __future__ import annotations

import sys
from pathlib import Path

# Win32 ShowWindow — 콘솔 깜빡임 없이 기동
_SW_HIDE = 0


def is_elevated() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def hide_console_window() -> None:
    """Iris GUI 전용 콘솔을 모니터에서 숨김.

    - 콘솔에 이 프로세스만 붙어 있으면 창을 SW_HIDE 후 분리
    - 부모 CMD/터미널과 공유 중이면 FreeConsole만 (부모 창은 유지)
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        hwnd = kernel32.GetConsoleWindow()
        if not hwnd:
            return
        # GetConsoleProcessList — 공유 여부
        buf = (wintypes.DWORD * 16)()
        n = int(kernel32.GetConsoleProcessList(ctypes.byref(buf), 16) or 0)
        if n <= 1:
            user32.ShowWindow(hwnd, _SW_HIDE)
        kernel32.FreeConsole()
    except Exception:
        pass


def _project_root() -> Path:
    # iris/learning/elevation.py → repo root
    return Path(__file__).resolve().parents[2]


def _find_iris_exe() -> Path | None:
    """UAC에 IRIS로 뜨도록 IRIS.exe를 우선 찾는다."""
    # PyInstaller 빌드본 — 이미 IRIS.exe로 실행 중
    if getattr(sys, "frozen", False):
        frozen = Path(sys.executable)
        if frozen.is_file() and frozen.name.lower() == "iris.exe":
            return frozen

    root = _project_root()
    candidates = [
        root / "dist" / "IRIS.exe",
        root / "IRIS.exe",
        Path(sys.executable).resolve().parent / "IRIS.exe",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def iris_launch_command() -> tuple[str, str]:
    """(executable, parameters) for ShellExecute runas.

    UAC 프로그램명은 실행 파일 기준이므로 IRIS.exe를 우선 사용한다.
    없을 때만 pythonw -m iris (개발 폴백).
    """
    iris_exe = _find_iris_exe()
    if iris_exe is not None:
        return str(iris_exe), ""

    exe = Path(sys.executable)
    if exe.name.lower() == "python.exe":
        pythonw = exe.with_name("pythonw.exe")
        if pythonw.is_file():
            exe = pythonw
    return str(exe), "-m iris"


def relaunch_as_admin(*, working_directory: str | None = None) -> bool:
    """UAC 프롬프트 후 관리자 권한으로 새 프로세스 기동. 성공 시 True."""
    if sys.platform != "win32":
        return False
    if is_elevated():
        return False
    import ctypes

    exe, params = iris_launch_command()
    cwd = working_directory or str(_project_root())
    # SEE_MASK — return value > 32 means success
    rc = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        exe,
        params or None,
        cwd,
        _SW_HIDE,
    )
    return int(rc) > 32


if __name__ == "__main__":
    exe, params = iris_launch_command()
    name = Path(exe).name.lower()
    assert name in {"iris.exe", "python.exe", "pythonw.exe"}, exe
    if name == "iris.exe":
        assert params == ""
    else:
        assert "-m iris" in params
    print("elevation self-check ok", exe, repr(params), "elevated=", is_elevated())
