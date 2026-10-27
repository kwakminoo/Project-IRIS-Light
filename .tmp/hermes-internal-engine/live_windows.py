from __future__ import annotations

import ctypes
from ctypes import wintypes

USER32 = ctypes.WinDLL("user32", use_last_error=True)
EnumWindows = USER32.EnumWindows
GetWindowTextW = USER32.GetWindowTextW
IsWindowVisible = USER32.IsWindowVisible
GetWindowRect = USER32.GetWindowRect
GetWindowThreadProcessId = USER32.GetWindowThreadProcessId
GetClassNameW = USER32.GetClassNameW
GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]


def main() -> None:
    found: list[str] = []

    def cb(hwnd: int, _lp: int) -> bool:
        pid = wintypes.DWORD()
        GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value != 45424:
            return True
        title = ctypes.create_unicode_buffer(512)
        GetWindowTextW(hwnd, title, 512)
        cls = ctypes.create_unicode_buffer(256)
        GetClassNameW(hwnd, cls, 256)
        rect = wintypes.RECT()
        GetWindowRect(hwnd, ctypes.byref(rect))
        vis = bool(IsWindowVisible(hwnd))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return True
        found.append(
            f"hwnd={hwnd} vis={vis} {w}x{h} @({rect.left},{rect.top}) class={cls.value!r} title={title.value!r}"
        )
        return True

    EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb), 0)
    print("\n".join(found) if found else "none")


if __name__ == "__main__":
    main()
