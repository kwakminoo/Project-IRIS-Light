"""Windows Explorer → Iris 파일 드롭 — DragAcceptFiles 준비.

PyQt6 nativeEvent / QAbstractNativeEventFilter / WNDPROC 서브클래스는
이 환경에서 기동 즉사·메시지루프 붕괴를 유발하므로 쓰지 않는다.
실제 첨부는 Qt setAcceptDrops + eventFilter 경로를 사용한다.
여기선 WS_EX_ACCEPTFILES·UIPI 만 보조로 연다.
"""

from __future__ import annotations

import sys
from pathlib import Path


WM_DROPFILES = 0x0233
WM_COPYDATA = 0x004A
WM_COPYGLOBALDATA = 0x0049
MSGFLT_ALLOW = 1
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_ACCEPTFILES = 0x00000010


def enable_shell_file_drop(hwnd: int) -> bool:
    """WS_EX_ACCEPTFILES + UIPI 완화. 훅/필터 없음."""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32

        ex = user32.GetWindowLongW(int(hwnd), GWL_EXSTYLE)
        if ex & WS_EX_TRANSPARENT:
            user32.SetWindowLongW(int(hwnd), GWL_EXSTYLE, ex & ~WS_EX_TRANSPARENT)

        shell32.DragAcceptFiles(wintypes.HWND(int(hwnd)), True)

        ex2 = user32.GetWindowLongW(int(hwnd), GWL_EXSTYLE)
        if not (ex2 & WS_EX_ACCEPTFILES):
            user32.SetWindowLongW(int(hwnd), GWL_EXSTYLE, ex2 | WS_EX_ACCEPTFILES)

        try:
            fn = user32.ChangeWindowMessageFilterEx
            fn.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.DWORD, ctypes.c_void_p]
            fn.restype = wintypes.BOOL
            hw = wintypes.HWND(int(hwnd))
            for msg in (WM_DROPFILES, WM_COPYDATA, WM_COPYGLOBALDATA):
                fn(hw, msg, MSGFLT_ALLOW, None)
        except Exception:
            pass

        _log(
            f"shell_drop_armed hwnd={int(hwnd)} "
            f"ex=0x{user32.GetWindowLongW(int(hwnd), GWL_EXSTYLE) & 0xFFFFFFFF:08x}"
        )
        return True
    except Exception as exc:
        _log(f"shell_drop_arm_fail {exc!r}")
        return False


def _log(line: str) -> None:
    try:
        log_dir = Path.home() / ".iris-light" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        from time import strftime

        with (log_dir / "dnd.log").open("a", encoding="utf-8") as fh:
            fh.write(f"{strftime('%H:%M:%S')} {line}\n")
    except Exception:
        pass
