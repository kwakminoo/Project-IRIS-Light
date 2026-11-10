"""Force the IRIS window above others, then screenshot its rect."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

USER32 = ctypes.WinDLL("user32", use_last_error=True)
EnumWindows = USER32.EnumWindows
EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
GetWindowTextW = USER32.GetWindowTextW
IsWindowVisible = USER32.IsWindowVisible
GetWindowRect = USER32.GetWindowRect
SetForegroundWindow = USER32.SetForegroundWindow
ShowWindow = USER32.ShowWindow
SetWindowPos = USER32.SetWindowPos
SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
SW_RESTORE = 9
HWND_TOPMOST = wintypes.HWND(-1)
HWND_NOTOPMOST = wintypes.HWND(-2)
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040


def find() -> int | None:
    found: list[tuple[int, int]] = []

    def cb(hwnd: int, _lp: int) -> bool:
        if not IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(512)
        GetWindowTextW(hwnd, buf, 512)
        if buf.value != "IRIS":
            return True
        rect = wintypes.RECT()
        GetWindowRect(hwnd, ctypes.byref(rect))
        area = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
        found.append((area, int(hwnd)))
        return True

    EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb), 0)
    if not found:
        return None
    found.sort(reverse=True)
    return found[0][1]


def main() -> int:
    hwnd = find()
    if hwnd is None:
        print("missing")
        return 1
    ShowWindow(hwnd, SW_RESTORE)
    SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
    SetForegroundWindow(hwnd)
    rect = wintypes.RECT()
    GetWindowRect(hwnd, ctypes.byref(rect))
    print(int(hwnd), rect.left, rect.top, rect.right, rect.bottom)
    stay = "--stay" in sys.argv
    if not stay:
        SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
    Path(__file__).with_name("iris-rect.txt").write_text(
        f"{rect.left} {rect.top} {rect.right} {rect.bottom}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
