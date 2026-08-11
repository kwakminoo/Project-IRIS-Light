"""Win32 low-level mouse/keyboard hooks — pynput 폴백."""

from __future__ import annotations

import logging
import threading
from ctypes import (
    CFUNCTYPE,
    POINTER,
    Structure,
    byref,
    c_int,
    c_long,
    c_void_p,
    sizeof,
    windll,
)
from ctypes.wintypes import DWORD, HINSTANCE, HWND, LPARAM, LRESULT, MSG, WPARAM
from typing import Callable

log = logging.getLogger("iris.learning.win32_hooks")

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_QUIT = 0x0012

HC_ACTION = 0

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A
WM_MOUSEMOVE = 0x0200

# Virtual-Key → name (subset)
_VK = {
    0x08: "BACKSPACE",
    0x09: "TAB",
    0x0D: "ENTER",
    0x1B: "ESC",
    0x20: "SPACE",
    0x25: "LEFT",
    0x26: "UP",
    0x27: "RIGHT",
    0x28: "DOWN",
    0x2E: "DELETE",
    0x10: "SHIFT",
    0x11: "CTRL",
    0x12: "ALT",
}


class POINT(Structure):
    _fields_ = [("x", c_long), ("y", c_long)]


class MSLLHOOKSTRUCT(Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", DWORD),
        ("flags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", c_void_p),
    ]


class KBDLLHOOKSTRUCT(Structure):
    _fields_ = [
        ("vkCode", DWORD),
        ("scanCode", DWORD),
        ("flags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", c_void_p),
    ]


LowLevelProc = CFUNCTYPE(LRESULT, c_int, WPARAM, LPARAM)


class Win32InputHooks:
    """SetWindowsHookEx LL 훅 — 별도 스레드에서 메시지 펌프."""

    def __init__(
        self,
        *,
        on_mouse: Callable[[str, float, float, dict], None] | None = None,
        on_key: Callable[[str, str, dict], None] | None = None,
    ) -> None:
        self._on_mouse = on_mouse
        self._on_key = on_key
        self._thread: threading.Thread | None = None
        self._tid = 0
        self._mouse_hook = None
        self._key_hook = None
        self._mouse_proc = None
        self._key_proc = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run, name="iris-win32-hooks", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._tid:
            try:
                windll.user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def _run(self) -> None:
        import ctypes

        self._tid = threading.get_ident()
        # Windows thread id for PostThreadMessage
        self._tid = windll.kernel32.GetCurrentThreadId()

        user32 = windll.user32

        def mouse_cb(nCode, wParam, lParam):
            if nCode == HC_ACTION and self._on_mouse:
                try:
                    info = ctypes.cast(lParam, POINTER(MSLLHOOKSTRUCT)).contents
                    x, y = float(info.pt.x), float(info.pt.y)
                    wp = int(wParam)
                    if wp == WM_LBUTTONDOWN:
                        self._on_mouse("press", x, y, {"button": "left", "pressed": True})
                    elif wp == WM_LBUTTONUP:
                        self._on_mouse("release", x, y, {"button": "left", "pressed": False})
                    elif wp == WM_RBUTTONDOWN:
                        self._on_mouse("press", x, y, {"button": "right", "pressed": True})
                    elif wp == WM_RBUTTONUP:
                        self._on_mouse("release", x, y, {"button": "right", "pressed": False})
                    elif wp == WM_MOUSEWHEEL:
                        delta = ctypes.c_short(info.mouseData >> 16).value
                        self._on_mouse(
                            "scroll", x, y, {"dx": 0, "dy": 1 if delta > 0 else -1}
                        )
                    elif wp == WM_MOUSEMOVE:
                        self._on_mouse("move", x, y, {})
                except Exception:
                    log.exception("mouse hook")
            return user32.CallNextHookEx(self._mouse_hook, nCode, wParam, lParam)

        def key_cb(nCode, wParam, lParam):
            if nCode == HC_ACTION and self._on_key:
                try:
                    info = ctypes.cast(lParam, POINTER(KBDLLHOOKSTRUCT)).contents
                    vk = int(info.vkCode)
                    name = _VK.get(vk)
                    if name is None and 0x30 <= vk <= 0x39:
                        name = chr(vk)
                    elif name is None and 0x41 <= vk <= 0x5A:
                        name = chr(vk)
                    else:
                        name = name or f"VK_{vk:02X}"
                    wp = int(wParam)
                    if wp in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        self._on_key("key_down", name, {"vk": vk})
                    elif wp in (WM_KEYUP, WM_SYSKEYUP):
                        self._on_key("key_up", name, {"vk": vk})
                except Exception:
                    log.exception("key hook")
            return user32.CallNextHookEx(self._key_hook, nCode, wParam, lParam)

        self._mouse_proc = LowLevelProc(mouse_cb)
        self._key_proc = LowLevelProc(key_cb)
        self._mouse_hook = user32.SetWindowsHookExW(
            WH_MOUSE_LL, self._mouse_proc, None, 0
        )
        self._key_hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._key_proc, None, 0
        )
        if not self._mouse_hook or not self._key_hook:
            log.error("SetWindowsHookEx failed")
            self._running = False
            return

        msg = MSG()
        while self._running and user32.GetMessageW(byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))

        if self._mouse_hook:
            user32.UnhookWindowsHookEx(self._mouse_hook)
        if self._key_hook:
            user32.UnhookWindowsHookEx(self._key_hook)
        self._mouse_hook = None
        self._key_hook = None
