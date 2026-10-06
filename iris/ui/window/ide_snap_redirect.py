"""IDE 포커스에서 Win+방향키를 아이리스 창 스냅으로 돌린다.

Windows 스냅은 포커스된 HWND에 붙는다. IRIS IDE가 앞에 있으면 셸이 IDE만
반쪽·최대화하고 아이리스는 그대로다. 저수준 키보드 훅이 그 조합만 삼키고
같은 배치를 아이리스에 적용한다.

ponytail: 훅은 UI 스레드에 있다. 스레드가 멈추면 Windows가 훅을 건너뛰어
IDE가 그대로 스냅될 수 있다. 업그레이드는 전용 훅 스레드 + Qt 큐 신호.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QRect, Qt, QTimer
from PyQt6.QtWidgets import QWidget

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_LWIN = 0x5B
VK_RWIN = 0x5C

_ARROWS = {VK_LEFT: "left", VK_UP: "up", VK_RIGHT: "right", VK_DOWN: "down"}

# 반쪽·사분면. 반대 방향은 스냅 전 크기로 되돌린다 (Windows 10/11 키보드 스냅).
_NEXT: dict[tuple[str, str], str] = {
    ("normal", "left"): "left",
    ("normal", "right"): "right",
    ("normal", "up"): "max",
    ("normal", "down"): "min",
    ("max", "left"): "left",
    ("max", "right"): "right",
    ("max", "up"): "max",
    ("max", "down"): "restore",
    ("left", "left"): "left",
    ("left", "right"): "restore",
    ("left", "up"): "tl",
    ("left", "down"): "bl",
    ("right", "left"): "restore",
    ("right", "right"): "right",
    ("right", "up"): "tr",
    ("right", "down"): "br",
    ("tl", "left"): "tl",
    ("tl", "right"): "tr",
    ("tl", "up"): "tl",
    ("tl", "down"): "left",
    ("tr", "left"): "tl",
    ("tr", "right"): "tr",
    ("tr", "up"): "tr",
    ("tr", "down"): "right",
    ("bl", "left"): "bl",
    ("bl", "right"): "br",
    ("bl", "up"): "left",
    ("bl", "down"): "restore",
    ("br", "left"): "bl",
    ("br", "right"): "br",
    ("br", "up"): "right",
    ("br", "down"): "restore",
}

_ZONE_TOL = 8
log = logging.getLogger("iris.ui.ide_snap_redirect")


@dataclass
class SnapMemory:
    restore: QRect | None = None


@dataclass(frozen=True)
class SnapStep:
    kind: str  # geometry | maximize | minimize | none
    rect: QRect | None = None


def arrow_name(vk: int) -> str | None:
    return _ARROWS.get(int(vk))


def title_is_iris_ide(title: str) -> bool:
    """빈 제목은 IDE가 아니다. 로딩 중 빈 제목까지 잡으면 다른 창의 스냅을 뺏는다."""
    t = (title or "").strip().lower()
    if not t:
        return False
    return t == "iris ide" or t.endswith("iris ide") or " — iris ide" in t or " - iris ide" in t


def should_take_snap(vk: int, *, win: bool, ctrl: bool, alt: bool, ide_foreground: bool) -> bool:
    """Win+방향키이고 IDE가 앞일 때만. Ctrl+Win은 가상 데스크톱이라 넘긴다."""
    return bool(ide_foreground and win and not ctrl and not alt and arrow_name(vk))


def zone_rect(work: QRect, name: str) -> QRect:
    x, y = int(work.left()), int(work.top())
    w, h = int(work.width()), int(work.height())
    lw, rw = w // 2, w - (w // 2)
    th, bh = h // 2, h - (h // 2)
    table = {
        "left": QRect(x, y, lw, h),
        "right": QRect(x + lw, y, rw, h),
        "tl": QRect(x, y, lw, th),
        "tr": QRect(x + lw, y, rw, th),
        "bl": QRect(x, y + th, lw, bh),
        "br": QRect(x + lw, y + th, rw, bh),
    }
    return table[name]


def _near(a: QRect, b: QRect, tol: int = _ZONE_TOL) -> bool:
    return (
        abs(int(a.left()) - int(b.left())) <= tol
        and abs(int(a.top()) - int(b.top())) <= tol
        and abs(int(a.width()) - int(b.width())) <= tol
        and abs(int(a.height()) - int(b.height())) <= tol
    )


def classify_zone(work: QRect, rect: QRect, *, maximized: bool) -> str:
    if maximized:
        return "max"
    for name in ("left", "right", "tl", "tr", "bl", "br"):
        if _near(rect, zone_rect(work, name)):
            return name
    return "normal"


def _default_restore(work: QRect) -> QRect:
    w = max(480, int(work.width() * 2 / 3))
    h = max(360, int(work.height() * 2 / 3))
    return QRect(
        int(work.left()) + (int(work.width()) - w) // 2,
        int(work.top()) + (int(work.height()) - h) // 2,
        w,
        h,
    )


def shift_monitor(rect: QRect, direction: str, screens: list[QRect]) -> QRect | None:
    """Win+Shift+좌/우 — 옆 모니터로 같은 크기를 옮긴다. 없으면 None."""
    if direction not in ("left", "right") or len(screens) < 2:
        return None
    center = rect.center()
    here = next((s for s in screens if s.contains(center)), screens[0])
    side = [
        s
        for s in screens
        if s != here
        and (
            (direction == "left" and s.center().x() < here.center().x())
            or (direction == "right" and s.center().x() > here.center().x())
        )
    ]
    if not side:
        return None
    dest = min(side, key=lambda s: abs(int(s.center().x()) - int(here.center().x())))
    moved = QRect(
        int(rect.left()) + int(dest.left()) - int(here.left()),
        int(rect.top()) + int(dest.top()) - int(here.top()),
        int(rect.width()),
        int(rect.height()),
    )
    if moved.right() > dest.right():
        moved.moveRight(int(dest.right()))
    if moved.left() < dest.left():
        moved.moveLeft(int(dest.left()))
    if moved.bottom() > dest.bottom():
        moved.moveBottom(int(dest.bottom()))
    if moved.top() < dest.top():
        moved.moveTop(int(dest.top()))
    return moved


def next_snap(
    work: QRect,
    rect: QRect,
    direction: str,
    *,
    maximized: bool,
    memory: SnapMemory,
    shift: bool = False,
    screens: list[QRect] | None = None,
) -> SnapStep:
    zone = classify_zone(work, rect, maximized=maximized)
    if zone == "normal":
        memory.restore = QRect(rect)
    if shift and direction in ("left", "right"):
        moved = shift_monitor(rect, direction, screens or [work])
        return SnapStep("geometry", moved) if moved is not None else SnapStep("none")
    if shift and direction == "up":
        return SnapStep(
            "geometry",
            QRect(int(rect.left()), int(work.top()), int(rect.width()), int(work.height())),
        )
    if shift and direction == "down":
        saved = memory.restore or _default_restore(work)
        return SnapStep(
            "geometry",
            QRect(int(rect.left()), int(saved.top()), int(rect.width()), int(saved.height())),
        )
    target = _NEXT[(zone, direction)]
    if target == "max":
        return SnapStep("maximize")
    if target == "min":
        return SnapStep("minimize")
    if target == "restore":
        return SnapStep("geometry", QRect(memory.restore or _default_restore(work)))
    return SnapStep("geometry", zone_rect(work, target))


def apply_snap(window: QWidget, step: SnapStep) -> None:
    """아이리스 배치. 포커스는 호출한 쪽이 IDE로 되돌린다."""
    if step.kind == "none":
        return
    if step.kind == "minimize":
        window.showMinimized()
        return
    if step.kind == "maximize":
        window.showMaximized()
        return
    rect = step.rect
    if rect is None:
        return
    if window.isMinimized() or window.isMaximized() or window.isFullScreen():
        window.setWindowState(Qt.WindowState.WindowNoState)
    window.setGeometry(rect)


def _win32():
    """HWND는 포인터 크기다. windll 기본 c_int면 포커스 비교가 어긋난다."""
    user32 = getattr(_win32, "api", None)
    if user32 is not None:
        return user32
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    _win32.api = user32
    return user32


def _window_text(hwnd: int) -> str:
    if int(hwnd) <= 0 or sys.platform != "win32":
        return ""
    user32 = _win32()
    n = int(user32.GetWindowTextLengthW(hwnd) or 0)
    if n <= 0:
        return ""
    import ctypes

    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _key_down(vk: int) -> bool:
    if sys.platform != "win32":
        return False
    return bool(_win32().GetAsyncKeyState(int(vk)) & 0x8000)


class IdeSnapRedirect:
    """IDE HWND가 앞일 때 Win+방향키를 삼키고 아이리스에 적용."""

    def __init__(
        self,
        owner: QWidget,
        *,
        ide_hwnd: Callable[[], int],
        on_applied: Callable[[], None] | None = None,
        arm_lock: Callable[[], None] | None = None,
    ) -> None:
        self._owner = owner
        self._ide_hwnd = ide_hwnd
        self._on_applied = on_applied
        self._arm_lock = arm_lock
        self._memory = SnapMemory()
        self._held: set[int] = set()
        self._swallowed: set[int] = set()
        self._hook = None
        self._proc = None

    def consider(
        self,
        vk: int,
        is_up: bool,
        *,
        win: bool,
        ctrl: bool,
        alt: bool,
        shift: bool,
        ide_foreground: bool,
    ) -> bool:
        """True면 키를 셸에 넘기지 않는다. 자동반복은 한 번만 적용."""
        name = arrow_name(vk)
        if name is None:
            return False
        if is_up:
            self._held.discard(vk)
            swallowed = vk in self._swallowed
            self._swallowed.discard(vk)
            return swallowed
        if vk in self._held:
            return vk in self._swallowed
        self._held.add(vk)
        if not should_take_snap(
            vk, win=win, ctrl=ctrl, alt=alt, ide_foreground=ide_foreground
        ):
            return False
        self._swallowed.add(vk)
        self._queue(name, shift=shift)
        return True

    def install(self) -> bool:
        if sys.platform != "win32":
            return False
        if self._hook:
            return True
        import ctypes

        try:
            from iris.learning.win32_hooks import KBDLLHOOKSTRUCT, LowLevelProc
        except (ImportError, OSError):
            log.exception("IDE snap hook initialization failed")
            return False

        user32 = ctypes.windll.user32
        WH_KEYBOARD_LL = 13
        LLKHF_UP = 0x80

        def key_cb(nCode, wParam, lParam):
            consume = False
            if nCode >= 0:
                try:
                    info = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    consume = self.consider(
                        int(info.vkCode),
                        bool(int(info.flags) & LLKHF_UP),
                        win=_key_down(VK_LWIN) or _key_down(VK_RWIN),
                        ctrl=_key_down(VK_CONTROL),
                        alt=_key_down(VK_MENU),
                        shift=_key_down(VK_SHIFT),
                        ide_foreground=self._foreground_is_ide(),
                    )
                except Exception:
                    consume = False
            if consume:
                return 1
            return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

        self._proc = LowLevelProc(key_cb)
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        if not self._hook:
            self._proc = None
            return False
        return True

    def uninstall(self) -> None:
        if sys.platform != "win32" or not self._hook:
            self._hook = None
            self._proc = None
            return
        import ctypes

        ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
        self._hook = None
        self._proc = None

    def _foreground_is_ide(self) -> bool:
        if sys.platform != "win32":
            return False
        ide = int(self._ide_hwnd() or 0)
        if ide <= 0:
            return False
        user32 = _win32()
        fg = int(user32.GetForegroundWindow() or 0)
        if fg <= 0:
            return False
        if fg == ide:
            return True
        root = int(user32.GetAncestor(fg, 2) or 0)  # GA_ROOT
        owner = int(user32.GetAncestor(fg, 3) or 0)  # GA_ROOTOWNER
        if root == ide or owner == ide:
            return True
        return title_is_iris_ide(_window_text(fg)) or title_is_iris_ide(_window_text(root))

    def _queue(self, direction: str, *, shift: bool) -> None:
        ide = int(self._ide_hwnd() or 0)
        QTimer.singleShot(0, lambda: self._apply(direction, shift, ide))

    def _apply(self, direction: str, shift: bool, ide_hwnd: int) -> None:
        try:
            iris = self._owner
            if iris is None:
                return
            if self._arm_lock is not None:
                self._arm_lock()
            from iris.system.ide_tiler import work_area_for

            ide_win = getattr(iris, "_iris_ide_window", None)
            anchor = ide_win if ide_win is not None and ide_win.isVisible() else iris
            work = work_area_for(anchor)
            screens = []
            try:
                from PyQt6.QtGui import QGuiApplication

                screens = [s.availableGeometry() for s in QGuiApplication.screens()]
            except Exception:
                screens = [work]
            step = next_snap(
                work,
                iris.frameGeometry(),
                direction,
                maximized=bool(iris.isMaximized()),
                memory=self._memory,
                shift=shift,
                screens=screens,
            )
            needs_refocus = (
                step.kind in ("maximize", "minimize")
                or iris.isMinimized()
                or iris.isMaximized()
                or iris.isFullScreen()
            )
            apply_snap(iris, step)
            if self._on_applied is not None:
                self._on_applied()
            if self._arm_lock is not None:
                self._arm_lock()
            if needs_refocus:
                _focus_hwnd(ide_hwnd)
        except Exception:
            log.exception("ide snap redirect")


def _focus_hwnd(hwnd: int) -> None:
    if sys.platform != "win32" or int(hwnd) <= 0:
        return
    _win32().SetForegroundWindow(int(hwnd))
