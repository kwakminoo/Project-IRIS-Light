"""관리자 권한으로 Iris 재실행."""

from __future__ import annotations

import sys
from pathlib import Path

# Win32 ShowWindow — 콘솔 깜빡임 없이 기동 / UAC 재실행은 정상 표시
_SW_HIDE = 0
_SW_SHOWNORMAL = 1


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

    UAC·작업표시줄 아이콘은 대상 exe에서 온다. dist\\IRIS.exe(thin launcher)가
    있으면 그걸 쓴다 — 클릭 시 다시 base pythonw -m iris 로 최신 소스를 띄운다.
    exe가 없을 때만 pythonw 폴백 (venv Scripts 스텁이 아니라 base).
    """
    iris_exe = _find_iris_exe()
    if iris_exe is not None:
        return str(iris_exe), ""

    root = _project_root()
    try:
        from iris.system.gui_python import resolve_gui_pythonw

        return str(resolve_gui_pythonw(root)), "-m iris"
    except Exception:
        pass
    for name in ("pythonw.exe", "python.exe"):
        py = root / ".venv" / "Scripts" / name
        if py.is_file():
            return str(py), "-m iris"

    exe = Path(sys.executable)
    if exe.name.lower() == "python.exe":
        pythonw = exe.with_name("pythonw.exe")
        if pythonw.is_file():
            exe = pythonw
    return str(exe), "-m iris"


def relaunch_as_admin(*, working_directory: str | None = None) -> bool:
    """UAC 프롬프트 후 관리자 권한으로 새 프로세스 기동. 성공 시 True.

    성공하면 호출측은 즉시 sys.exit(0) 해야 한다. 부모가 GUI/mutex 를 유지하면
    자식과 이중 UI 가 된다 (Local\\ mutex 는 integrity 가 다르면 공유되지 않음).
    """
    if sys.platform != "win32":
        return False
    if is_elevated():
        return False
    import ctypes
    import os
    from pathlib import Path

    root = _project_root()
    try:
        from iris.system.gui_python import gui_launch_env

        os.environ.update(gui_launch_env(root))
    except Exception:
        pass
    exe, params = iris_launch_command()
    cwd = working_directory or str(root)
    # Child inherits this; parent must exit after successful ShellExecute.
    os.environ["IRIS_ELEVATED_CHILD"] = "1"
    try:
        # SEE_MASK — return value > 32 means success
        rc = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            exe,
            params or None,
            cwd,
            _SW_SHOWNORMAL,
        )
        ok = int(rc) > 32
    except Exception:
        os.environ.pop("IRIS_ELEVATED_CHILD", None)
        raise
    try:
        path = Path.home() / ".iris-light" / "logs" / "boot_trace.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(
                f"pid={os.getpid()} ppid={os.getppid()} "
                f"relaunch_as_admin ShellExecuteW exe={exe!r} params={params!r} "
                f"rc={int(rc)} ok={ok}\n"
            )
    except Exception:
        pass
    if not ok:
        os.environ.pop("IRIS_ELEVATED_CHILD", None)
    return ok


def needs_admin_for_setup() -> bool:
    """실행 프로토콜(첫 설치·미완료 Core)은 관리자 권한이 필요하다."""
    if sys.platform != "win32":
        return False
    if is_elevated():
        return False
    try:
        from iris.system.setup_protocol import is_setup_preview, needs_setup_wizard

        if is_setup_preview():
            return False
        return bool(needs_setup_wizard())
    except Exception:
        return False


def _pending_setup_wizard_path() -> Path:
    from iris.system.iris_agent_control_sync import iris_state_dir

    return iris_state_dir() / "pending_setup_wizard"


def mark_pending_setup_wizard(mode: str = "repair") -> None:
    """관리자 재실행 후 위저드를 다시 열도록 표시."""
    try:
        path = _pending_setup_wizard_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((mode or "repair").strip() or "repair", encoding="utf-8")
    except OSError:
        pass


def consume_pending_setup_wizard() -> str | None:
    """재실행 후 1회만 읽는다. 없으면 None."""
    path = _pending_setup_wizard_path()
    try:
        if not path.is_file():
            return None
        mode = path.read_text(encoding="utf-8").strip() or "repair"
        path.unlink(missing_ok=True)
        return mode if mode in {"first_run", "repair"} else "repair"
    except OSError:
        return None


def elevate_for_setup_protocol(*, mode: str | None = None) -> bool:
    """실행 프로토콜 직전에 관리자로 재실행. True면 현재 프로세스는 종료할 것."""
    if sys.platform != "win32" or is_elevated():
        return False
    try:
        from iris.system.setup_protocol import is_setup_preview

        if is_setup_preview():
            return False
    except Exception:
        pass
    if mode:
        mark_pending_setup_wizard(mode)
    return relaunch_as_admin()


if __name__ == "__main__":
    exe, params = iris_launch_command()
    name = Path(exe).name.lower()
    assert name in {"iris.exe", "python.exe", "pythonw.exe"}, exe
    found = _find_iris_exe()
    if found is not None:
        assert name == "iris.exe", exe
        assert params == ""
        assert Path(exe).resolve() == found.resolve()
    elif name == "iris.exe":
        assert params == ""
    else:
        assert "-m iris" in params
    # ponytail: 미리보기면 상승 요구 금지 — 데모/CI가 UAC에 막히지 않게.
    import os

    os.environ["IRIS_SETUP_DEMO"] = "1"
    assert needs_admin_for_setup() is False
    assert elevate_for_setup_protocol() is False
    mark_pending_setup_wizard("repair")
    assert consume_pending_setup_wizard() == "repair"
    assert consume_pending_setup_wizard() is None
    print("elevation self-check ok", exe, repr(params), "elevated=", is_elevated())
