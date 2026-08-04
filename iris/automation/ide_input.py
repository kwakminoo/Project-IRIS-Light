"""IDE 창 포커스·단축키·유니코드 타이핑 (Windows + macOS).

ponytail: Cursor/VS Code 통합 터미널·에디터 연출용.
Windows: AttachThreadInput으로 포커스 성공률을 올린다 (hwnd 기반).
macOS: hwnd 자리엔 CGWindowNumber를 쓰되, 포커스·키 입력은 pid 기반
(NSRunningApplication 활성화 + CGEvent 유니코드/키 입력, HWND 개념이 없다).
천장: OS/IME에 따라 일부 문자·포커스 실패 가능 → 호출측에서 폴백.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path


def _win32() -> bool:
    return sys.platform == "win32"


def _macos() -> bool:
    return sys.platform == "darwin"


# ---- macOS 저수준 프리미티브 (Accessibility 권한 필요) ----

_VK_RETURN = 0x24
_VK_DELETE = 0x33
_VK_ESCAPE = 0x35
_VK_A = 0x00
_VK_S = 0x01
_VK_P = 0x23
_VK_B = 0x0B
_VK_GRAVE = 0x32


def _macos_window_info(window_number: int) -> dict:
    if not window_number:
        return {}
    try:
        import Quartz  # type: ignore

        wins = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListExcludeDesktopElements, Quartz.kCGNullWindowID
        )
        for w in wins:
            if int(w.get("kCGWindowNumber", 0) or 0) == int(window_number):
                return dict(w)
    except Exception:
        pass
    return {}


def _macos_activate_pid(pid: int) -> bool:
    try:
        from AppKit import (  # type: ignore
            NSApplicationActivateIgnoringOtherApps,
            NSRunningApplication,
        )

        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(int(pid))
        if app is None:
            return False
        return bool(app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps))
    except Exception:
        return False


def _macos_post_unicode_text(
    text: str, *, delay_ms: int = 12, pump: Callable[[], None] | None = None
) -> None:
    import Quartz  # type: ignore

    delay = max(0, int(delay_ms)) / 1000.0
    for ch in text:
        down = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
        Quartz.CGEventKeyboardSetUnicodeString(down, len(ch), ch)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        up = Quartz.CGEventCreateKeyboardEvent(None, 0, False)
        Quartz.CGEventKeyboardSetUnicodeString(up, len(ch), ch)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
        if delay > 0:
            if pump is not None:
                pump()
            time.sleep(delay)


def _macos_key_combo(flags: int, keycode: int) -> None:
    import Quartz  # type: ignore

    down = Quartz.CGEventCreateKeyboardEvent(None, keycode, True)
    Quartz.CGEventSetFlags(down, flags)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    up = Quartz.CGEventCreateKeyboardEvent(None, keycode, False)
    Quartz.CGEventSetFlags(up, flags)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def _macos_click_point(x: float, y: float) -> None:
    import Quartz  # type: ignore

    point = Quartz.CGPointMake(x, y)
    down = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseDown, point, Quartz.kCGMouseButtonLeft
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    up = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseUp, point, Quartz.kCGMouseButtonLeft
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def get_window_title(hwnd: int) -> str:
    if not hwnd:
        return ""
    if _macos():
        info = _macos_window_info(hwnd)
        if not info:
            return ""
        import Quartz  # type: ignore

        return (info.get(Quartz.kCGWindowName, "") or "").strip()
    if not _win32():
        return ""
    try:
        import win32gui  # type: ignore

        return (win32gui.GetWindowText(int(hwnd)) or "").strip()
    except Exception:
        return ""


def force_focus_hwnd(hwnd: int, *, pid: int | None = None) -> bool:
    """IDE 창을 전면으로. SetForegroundWindow 제한 우회 시도 (Windows) /
    NSRunningApplication 활성화 (macOS, pid 필요)."""
    if _macos():
        if not pid:
            return False
        return _macos_activate_pid(int(pid))
    if not _win32() or not hwnd:
        return False
    try:
        import win32api  # type: ignore
        import win32con  # type: ignore
        import win32gui  # type: ignore
        import win32process  # type: ignore

        hwnd = int(hwnd)
        if not win32gui.IsWindow(hwnd):
            return False
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        fg = win32gui.GetForegroundWindow()
        if fg == hwnd:
            return True
        tid_target = win32process.GetWindowThreadProcessId(hwnd)[0]
        tid_fg = win32process.GetWindowThreadProcessId(fg)[0] if fg else 0
        tid_cur = win32api.GetCurrentThreadId()
        attached_fg = False
        attached_cur = False
        try:
            if tid_fg and tid_fg != tid_cur:
                win32process.AttachThreadInput(tid_fg, tid_cur, True)
                attached_fg = True
            if tid_target and tid_target != tid_cur:
                win32process.AttachThreadInput(tid_target, tid_cur, True)
                attached_cur = True
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
        finally:
            if attached_cur:
                win32process.AttachThreadInput(tid_target, tid_cur, False)
            if attached_fg:
                win32process.AttachThreadInput(tid_fg, tid_cur, False)
        time.sleep(0.08)
        return win32gui.GetForegroundWindow() == hwnd
    except Exception:
        return False


def wait_ide_shows_file(
    hwnd: int,
    file_path: str,
    *,
    timeout_sec: float = 6.0,
    pump: Callable[[], None] | None = None,
) -> bool:
    """창 제목에 파일명이 나타날 때까지 대기 (탭 선택·표시 추정)."""
    name = Path(file_path).name.strip()
    if not name or not hwnd:
        return False
    needle = name.lower()
    deadline = time.monotonic() + max(0.5, float(timeout_sec))
    while time.monotonic() < deadline:
        title = get_window_title(hwnd).lower()
        if needle in title:
            return True
        if pump is not None:
            pump()
        time.sleep(0.2)
    return needle in get_window_title(hwnd).lower()


def send_key_combo(hwnd: int, *vk_codes: int) -> bool:
    """Windows 전용 — vk_codes 조합(마지막이 메인 키). macOS는 각 trigger_* 함수가
    CGEvent 플래그 방식으로 자체 처리한다(단일 keycode + modifier flags)."""
    if not _win32() or not vk_codes:
        return False
    try:
        import win32api  # type: ignore
        import win32con  # type: ignore

        force_focus_hwnd(hwnd)
        time.sleep(0.12)
        for vk in vk_codes[:-1]:
            win32api.keybd_event(int(vk), 0, 0, 0)
        win32api.keybd_event(int(vk_codes[-1]), 0, 0, 0)
        win32api.keybd_event(int(vk_codes[-1]), 0, win32con.KEYEVENTF_KEYUP, 0)
        for vk in reversed(vk_codes[:-1]):
            win32api.keybd_event(int(vk), 0, win32con.KEYEVENTF_KEYUP, 0)
        return True
    except Exception:
        return False


def trigger_default_build_task(hwnd: int, *, pid: int | None = None) -> bool:
    """Ctrl+Shift+B (win) / Cmd+Shift+B (mac) — VS Code/Cursor 기본 Build Task (Iris: Run)."""
    if _macos():
        if not force_focus_hwnd(hwnd, pid=pid):
            return False
        time.sleep(0.1)
        import Quartz  # type: ignore

        _macos_key_combo(
            Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskShift, _VK_B
        )
        return True
    import win32con  # type: ignore

    return send_key_combo(
        hwnd,
        win32con.VK_CONTROL,
        win32con.VK_SHIFT,
        ord("B"),
    )


def trigger_save(hwnd: int, *, pid: int | None = None) -> bool:
    if _macos():
        if not force_focus_hwnd(hwnd, pid=pid):
            return False
        time.sleep(0.1)
        import Quartz  # type: ignore

        _macos_key_combo(Quartz.kCGEventFlagMaskCommand, _VK_S)
        return True
    import win32con  # type: ignore

    return send_key_combo(hwnd, win32con.VK_CONTROL, ord("S"))


def trigger_quick_open(hwnd: int, *, pid: int | None = None) -> bool:
    if _macos():
        if not force_focus_hwnd(hwnd, pid=pid):
            return False
        time.sleep(0.1)
        import Quartz  # type: ignore

        _macos_key_combo(Quartz.kCGEventFlagMaskCommand, _VK_P)
        return True
    import win32con  # type: ignore

    return send_key_combo(hwnd, win32con.VK_CONTROL, ord("P"))


def trigger_integrated_terminal(hwnd: int, *, pid: int | None = None) -> bool:
    if _macos():
        if not force_focus_hwnd(hwnd, pid=pid):
            return False
        time.sleep(0.1)
        import Quartz  # type: ignore

        # VS Code/Cursor 기본 터미널 토글은 macOS에서도 Ctrl+` 그대로 유지(Cmd 아님).
        _macos_key_combo(Quartz.kCGEventFlagMaskControl, _VK_GRAVE)
        return True
    import win32con  # type: ignore

    return send_key_combo(hwnd, win32con.VK_CONTROL, getattr(win32con, "VK_OEM_3", 0xC0))


def type_unicode_text(
    text: str,
    *,
    delay_ms: int = 12,
    pump: Callable[[], None] | None = None,
) -> None:
    """전면 창에 유니코드 타이핑."""
    if not text:
        return
    if _macos():
        _macos_post_unicode_text(text, delay_ms=delay_ms, pump=pump)
        return
    if not _win32():
        return
    import ctypes
    from ctypes import wintypes

    ULONG_PTR = ctypes.c_size_t

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class INPUT(ctypes.Structure):
        class _I(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]

        _anonymous_ = ("i",)
        _fields_ = [("type", wintypes.DWORD), ("i", _I)]

    SendInput = ctypes.windll.user32.SendInput
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    INPUT_KEYBOARD = 1
    delay = max(0, int(delay_ms)) / 1000.0

    def _send_char(ch: str) -> None:
        code = ord(ch)
        if ch == "\n":
            # Enter
            for flags in (0, KEYEVENTF_KEYUP):
                inp = INPUT(type=INPUT_KEYBOARD)
                inp.ki = KEYBDINPUT(0x0D, 0, flags, 0, ULONG_PTR(0))
                SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            return
        if ch == "\r":
            return
        for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
            inp = INPUT(type=INPUT_KEYBOARD)
            inp.ki = KEYBDINPUT(0, code, flags, 0, ULONG_PTR(0))
            SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    for ch in text:
        _send_char(ch)
        if delay > 0:
            if pump is not None:
                pump()
            time.sleep(delay)


def click_editor_area(hwnd: int, *, pid: int | None = None) -> bool:
    """IDE 창 중앙-좌측(에디터 추정) 클릭으로 텍스트 버퍼 포커스."""
    if _macos():
        if not force_focus_hwnd(hwnd, pid=pid):
            return False
        info = _macos_window_info(hwnd)
        bounds = info.get("kCGWindowBounds") if info else None
        if not bounds:
            return False
        left, top = float(bounds["X"]), float(bounds["Y"])
        w, h = float(bounds["Width"]), float(bounds["Height"])
        x = left + w * 0.35
        y = top + h * 0.45
        _macos_click_point(x, y)
        time.sleep(0.08)
        return True
    if not _win32() or not hwnd:
        return False
    try:
        import win32api  # type: ignore
        import win32con  # type: ignore
        import win32gui  # type: ignore

        force_focus_hwnd(hwnd)
        left, top, right, bot = win32gui.GetWindowRect(int(hwnd))
        w, h = max(1, right - left), max(1, bot - top)
        # 사이드바·미니맵 피해서 가로 35%, 세로 45% 지점
        x = int(left + w * 0.35)
        y = int(top + h * 0.45)
        win32api.SetCursorPos((x, y))
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.08)
        return True
    except Exception:
        return False


def typewriter_into_ide(
    hwnd: int,
    text: str,
    *,
    delay_ms: int | None = None,
    pump: Callable[[], None] | None = None,
    pid: int | None = None,
) -> bool:
    """IDE 포커스 후 본문 타이핑 + 저장(Ctrl/Cmd+S)."""
    if not hwnd:
        return False
    body = str(text)
    if delay_ms is None:
        # ponytail: 긴 파일도 ~8초 안에 끝나게 속도 조절
        n = max(len(body), 1)
        delay_ms = max(4, min(18, int(8000 / n)))
    force_focus_hwnd(hwnd, pid=pid)
    time.sleep(0.15)
    click_editor_area(hwnd, pid=pid)
    if _macos():
        import Quartz  # type: ignore

        # Escape로 팔레트/검색 닫기
        _macos_key_combo(0, _VK_ESCAPE)
        time.sleep(0.05)
        # Cmd+A / Delete 로 빈 버퍼 확보 (외부에서 쓴 잔여 대비)
        _macos_key_combo(Quartz.kCGEventFlagMaskCommand, _VK_A)
        time.sleep(0.05)
        _macos_key_combo(0, _VK_DELETE)
        time.sleep(0.05)
    else:
        try:
            import win32api  # type: ignore
            import win32con  # type: ignore

            win32api.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
            win32api.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.05)
            send_key_combo(hwnd, win32con.VK_CONTROL, ord("A"))
            time.sleep(0.05)
            win32api.keybd_event(win32con.VK_DELETE, 0, 0, 0)
            win32api.keybd_event(win32con.VK_DELETE, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.05)
        except Exception:
            pass
    type_unicode_text(body, delay_ms=int(delay_ms), pump=pump)
    time.sleep(0.1)
    trigger_save(hwnd, pid=pid)
    return True


def open_file_in_workspace(
    hwnd: int,
    file_path: str,
    *,
    workspace_root: str = "",
    pump: Callable[[], None] | None = None,
    pid: int | None = None,
) -> bool:
    """현재 IDE 창의 Quick Open으로 파일을 연다."""
    if not hwnd:
        return False
    path = Path(file_path).expanduser()
    if not path.is_file():
        return False
    query = str(path.resolve())
    if workspace_root:
        try:
            root = Path(workspace_root).expanduser().resolve()
            query = str(path.resolve().relative_to(root)).replace("\\", "/")
        except Exception:
            query = str(path.resolve())
    force_focus_hwnd(hwnd, pid=pid)
    time.sleep(0.15)
    if _macos():
        _macos_key_combo(0, _VK_ESCAPE)
        time.sleep(0.05)
    else:
        try:
            import win32api  # type: ignore
            import win32con  # type: ignore

            win32api.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
            win32api.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.05)
        except Exception:
            pass
    if not trigger_quick_open(hwnd, pid=pid):
        return False
    time.sleep(0.15)
    type_unicode_text(query, delay_ms=4, pump=pump)
    time.sleep(0.05)
    if _macos():
        _macos_key_combo(0, _VK_RETURN)
    else:
        try:
            import win32api  # type: ignore
            import win32con  # type: ignore

            win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
            win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
        except Exception:
            return False
    return True


def run_command_in_ide_terminal(
    hwnd: int,
    command: str,
    *,
    pump: Callable[[], None] | None = None,
    pid: int | None = None,
) -> bool:
    """현재 IDE 창의 통합 터미널을 열고 명령 1개를 실행한다."""
    if not hwnd or not command:
        return False
    force_focus_hwnd(hwnd, pid=pid)
    time.sleep(0.15)
    if not trigger_integrated_terminal(hwnd, pid=pid):
        return False
    time.sleep(0.2)
    type_unicode_text(str(command), delay_ms=3, pump=pump)
    if _macos():
        _macos_key_combo(0, _VK_RETURN)
    else:
        try:
            import win32api  # type: ignore
            import win32con  # type: ignore

            win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
            win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
        except Exception:
            return False
    return True


if __name__ == "__main__":
    assert get_window_title(0) == ""
    print("ide_input ok")
