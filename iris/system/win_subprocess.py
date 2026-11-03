"""Windows subprocess — 콘솔 창 없이 백그라운드 실행."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from typing import Any

_PATCHED = False


def no_window_kwargs(*, extra_creationflags: int = 0) -> dict[str, Any]:
    """subprocess.run/Popen용 — 모니터에 터미널이 안 뜨게.

    extra_creationflags: CREATE_NEW_PROCESS_GROUP 등 CREATE_NO_WINDOW와 OR할 플래그.
    GUI 에뮬 기동에는 이 헬퍼 대신 `_gui_launch_creationflags()`를 쓴다
    (여기의 STARTUPINFO/SW_HIDE가 Qt 창을 깨뜨림).
    """
    if sys.platform != "win32":
        return {}
    flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) | int(extra_creationflags)
    kw: dict[str, Any] = {"creationflags": flags}
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        kw["startupinfo"] = si
    except Exception:
        pass
    return kw


def suppress_platform_ver_console() -> None:
    """platform.win32_ver()의 ``cmd /c ver`` 콘솔 깜빡임 제거. 비-Windows는 no-op.

    pythonw 부모에서 ``platform.uname()`` / 의존성 import 가 짧은 cmd 창을 띄운다.
    스텁 후 win32_ver 는 sys.getwindowsversion() 폴백만 쓴다.
    """
    if sys.platform != "win32":
        return
    if getattr(platform, "_iris_syscmd_ver_suppressed", False):
        return

    def _no_shell_ver(
        system: str = "",
        release: str = "",
        version: str = "",
        supported_platforms: tuple[str, ...] = ("win32", "win16", "dos"),
    ) -> tuple[str, str, str]:
        if sys.platform not in supported_platforms:
            return system, release, version
        return system, release, version

    platform._syscmd_ver = _no_shell_ver  # type: ignore[attr-defined]
    platform._uname_cache = None  # type: ignore[attr-defined]
    platform._iris_syscmd_ver_suppressed = True  # type: ignore[attr-defined]


def _allow_console(kwargs: dict[str, Any]) -> bool:
    if kwargs.pop("iris_allow_console", False):
        return True
    flag = (os.environ.get("IRIS_ALLOW_CONSOLE") or "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def harden_subprocess_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Windows에서 콘솔 플래시를 막도록 kwargs를 보강. GUI(DETACHED) 경로는 건드리지 않는다."""
    if sys.platform != "win32" or _allow_console(kwargs):
        return kwargs
    no_win = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    detached = int(getattr(subprocess, "DETACHED_PROCESS", 0))
    new_console = int(getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    flags = int(kwargs.get("creationflags") or 0)
    # 에뮬 GUI·의도적 새 콘솔 — CREATE_NO_WINDOW/SW_HIDE 금지
    if flags & detached or flags & new_console:
        return kwargs
    if not (flags & no_win):
        kwargs["creationflags"] = flags | no_win
    if "startupinfo" not in kwargs:
        extra = no_window_kwargs()
        if "startupinfo" in extra:
            kwargs["startupinfo"] = extra["startupinfo"]
    return kwargs


def install_no_console_subprocess_patch() -> bool:
    """Iris 프로세스의 subprocess.* 에 CREATE_NO_WINDOW를 기본 주입. idempotent.

    채팅·첨부·git·MCP·헬퍼가 빠뜨린 호출도 Cascadia/콘솔 깜빡임을 막는다.
    DETACHED_PROCESS(GUI IDE/에뮬)와 CREATE_NEW_CONSOLE은 제외.
    """
    global _PATCHED
    if sys.platform != "win32":
        return False
    if _PATCHED or getattr(subprocess, "_iris_no_console_patched", False):
        _PATCHED = True
        return True

    orig_popen = subprocess.Popen
    orig_run = subprocess.run
    orig_call = subprocess.call
    orig_check_call = subprocess.check_call
    orig_check_output = subprocess.check_output

    class _Popen(orig_popen):  # type: ignore[valid-type,misc]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **harden_subprocess_kwargs(kwargs))

    def _run(*args: Any, **kwargs: Any):
        return orig_run(*args, **harden_subprocess_kwargs(kwargs))

    def _call(*args: Any, **kwargs: Any):
        return orig_call(*args, **harden_subprocess_kwargs(kwargs))

    def _check_call(*args: Any, **kwargs: Any):
        return orig_check_call(*args, **harden_subprocess_kwargs(kwargs))

    def _check_output(*args: Any, **kwargs: Any):
        return orig_check_output(*args, **harden_subprocess_kwargs(kwargs))

    subprocess.Popen = _Popen  # type: ignore[misc,assignment]
    subprocess.run = _run  # type: ignore[assignment]
    subprocess.call = _call  # type: ignore[assignment]
    subprocess.check_call = _check_call  # type: ignore[assignment]
    subprocess.check_output = _check_output  # type: ignore[assignment]
    subprocess._iris_no_console_patched = True  # type: ignore[attr-defined]
    _PATCHED = True
    return True
