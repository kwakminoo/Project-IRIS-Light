"""Focus the IRIS window and type one chat line. Not imported by IRIS."""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

USER32 = ctypes.WinDLL("user32", use_last_error=True)

EnumWindows = USER32.EnumWindows
EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
EnumWindows.restype = wintypes.BOOL
GetWindowTextW = USER32.GetWindowTextW
GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
GetWindowTextW.restype = ctypes.c_int
IsWindowVisible = USER32.IsWindowVisible
IsWindowVisible.argtypes = [wintypes.HWND]
IsWindowVisible.restype = wintypes.BOOL
GetWindowThreadProcessId = USER32.GetWindowThreadProcessId
GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
GetWindowThreadProcessId.restype = wintypes.DWORD
SetForegroundWindow = USER32.SetForegroundWindow
SetForegroundWindow.argtypes = [wintypes.HWND]
SetForegroundWindow.restype = wintypes.BOOL
GetForegroundWindow = USER32.GetForegroundWindow
GetForegroundWindow.argtypes = []
GetForegroundWindow.restype = wintypes.HWND
GetWindowRect = USER32.GetWindowRect
GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
GetWindowRect.restype = wintypes.BOOL
AttachThreadInput = USER32.AttachThreadInput
AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
AttachThreadInput.restype = wintypes.BOOL
GetCurrentThreadId = ctypes.windll.kernel32.GetCurrentThreadId
GetCurrentThreadId.argtypes = []
GetCurrentThreadId.restype = wintypes.DWORD
SetCursorPos = USER32.SetCursorPos
SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
SetCursorPos.restype = wintypes.BOOL
mouse_event = USER32.mouse_event
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

MAPVK_VK_TO_VSC = 0
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_RETURN = 0x0D
INPUT_KEYBOARD = 1


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    )


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = (("ki", KEYBDINPUT),)

    _anonymous_ = ("u",)
    _fields_ = (("type", wintypes.DWORD), ("u", _U))


SendInput = USER32.SendInput
SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
SendInput.restype = wintypes.UINT


def _find_iris() -> tuple[int, int] | None:
    found: list[tuple[int, int, int]] = []

    def _cb(hwnd: int, _lparam: int) -> bool:
        if not IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(512)
        GetWindowTextW(hwnd, buf, 512)
        if buf.value != "IRIS":
            return True
        rect = wintypes.RECT()
        GetWindowRect(hwnd, ctypes.byref(rect))
        area = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
        pid = wintypes.DWORD()
        GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        found.append((area, int(hwnd), int(pid.value)))
        return True

    EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(_cb), 0)
    if not found:
        return None
    found.sort(reverse=True)
    return found[0][1], found[0][2]


def _click(x: int, y: int) -> None:
    SetCursorPos(x, y)
    time.sleep(0.05)
    mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def _type_text(text: str) -> None:
    for ch in text:
        scan = ord(ch)
        down = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, scan, KEYEVENTF_UNICODE, 0, None))
        up = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, scan, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None))
        SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
        SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
        time.sleep(0.01)
    enter = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(VK_RETURN, 0, 0, 0, None))
    enter_up = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(VK_RETURN, 0, KEYEVENTF_KEYUP, 0, None))
    SendInput(1, ctypes.byref(enter), ctypes.sizeof(INPUT))
    SendInput(1, ctypes.byref(enter_up), ctypes.sizeof(INPUT))


def main() -> int:
    text = " ".join(sys.argv[1:]).strip()
    if not text:
        print("usage: live_type.py <text>")
        return 2
    hit = _find_iris()
    if hit is None:
        print("IRIS window not found")
        return 1
    hwnd, pid = hit
    rect = wintypes.RECT()
    GetWindowRect(hwnd, ctypes.byref(rect))
    print("hwnd", hwnd, "pid", pid, "rect", rect.left, rect.top, rect.right, rect.bottom)
    pid_box = wintypes.DWORD()
    target_tid = GetWindowThreadProcessId(hwnd, ctypes.byref(pid_box))
    our_tid = GetCurrentThreadId()
    AttachThreadInput(our_tid, target_tid, True)
    SetForegroundWindow(hwnd)
    time.sleep(0.4)
    fg = GetForegroundWindow()
    print("foreground", int(fg), "match", int(fg) == hwnd)
    x = rect.left + int((rect.right - rect.left) * 0.45)
    y = rect.bottom - 88
    _click(x, y)
    time.sleep(0.25)
    _type_text(text)
    time.sleep(0.2)
    send_x = rect.right - 36
    send_y = rect.bottom - 40
    _click(send_x, send_y)
    AttachThreadInput(our_tid, target_tid, False)
    print("typed", text, "clicked composer", x, y, "send", send_x, send_y)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
