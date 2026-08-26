"""IDE / Iris 창을 주 모니터 work area 기준 70:30 타일 배치."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QWidget


@dataclass(frozen=True)
class TileRects:
    work: QRect
    ide: QRect
    iris: QRect


def _dpi_scale_for_hwnd(hwnd: int) -> float:
    """hwnd가 있는 모니터의 DPI 배율 (100%=1.0, 200%=2.0).

    Qt의 availableGeometry/geometry는 DIP(논리 픽셀)인데, win32 GetWindowRect/
    SetWindowPos는 PHYSICAL(실제) 픽셀을 쓴다 — 200% 배율 모니터에서 DIP 좌표를
    그대로 SetWindowPos에 넘기면 창이 실제 크기의 절반으로 배치된다
    (예: 의도한 폭 1152가 physical 1152px = DIP 576px로 보임)."""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        get_dpi = getattr(user32, "GetDpiForWindow", None)
        if get_dpi is not None:
            dpi = int(get_dpi(hwnd))
            if dpi > 0:
                return dpi / 96.0
    except Exception:
        pass
    return 1.0


def _scale_rect(rect: QRect, factor: float) -> QRect:
    return QRect(
        round(rect.left() * factor),
        round(rect.top() * factor),
        round(rect.width() * factor),
        round(rect.height() * factor),
    )


def work_area_for(widget: QWidget) -> QRect:
    """Iris가 있는 모니터의 availableGeometry (작업 표시줄 제외)."""
    screen = widget.screen()
    if screen is None:
        from PyQt6.QtGui import QGuiApplication

        screen = QGuiApplication.primaryScreen()
    if screen is None:
        return QRect(0, 0, 1280, 720)
    return screen.availableGeometry()


def compute_tile_rects(work: QRect, *, ide_ratio: float = 0.7) -> TileRects:
    ratio = min(0.95, max(0.5, float(ide_ratio)))
    ide_w = int(work.width() * ratio)
    iris_w = work.width() - ide_w
    ide = QRect(work.left(), work.top(), ide_w, work.height())
    iris = QRect(work.left() + ide_w, work.top(), iris_w, work.height())
    return TileRects(work=work, ide=ide, iris=iris)


def _place_macos_pid(pid: int, rect: QRect) -> tuple[bool, str]:
    """PID의 (가장 큰) 창을 Accessibility API로 이동·리사이즈.

    macOS엔 HWND가 없어 CGWindowNumber로는 창을 옮길 수 없다 — AXUIElement로
    프로세스의 창 목록을 얻어 그중 가장 큰 창(= companion 진입 시 새로 연 IDE 창)을
    움직인다. 실패 시 대개 손쉬운 사용(Accessibility) 권한 미허용이 원인.
    """
    try:
        import ApplicationServices as AS  # type: ignore
    except Exception as exc:
        return False, f"pyobjc ApplicationServices 없음: {exc}"

    if not AS.AXIsProcessTrusted():
        return False, "손쉬운 사용(Accessibility) 권한이 필요합니다 — 시스템 설정에서 허용하세요."

    app_ref = AS.AXUIElementCreateApplication(int(pid))
    err, windows = AS.AXUIElementCopyAttributeValue(app_ref, AS.kAXWindowsAttribute, None)
    if err != 0 or not windows:
        return False, "AX 창을 찾을 수 없습니다"

    # companion 진입 흐름은 항상 "새로 연 창 1개"를 대상으로 하므로 프론트모스트
    # (AX가 돌려주는 첫 창)를 그대로 사용한다 — 다중 창 매칭은 다루지 않음.
    window_ref = windows[0]

    pos_value = AS.AXValueCreate(
        AS.kAXValueCGPointType, AS.CGPoint(rect.left(), rect.top())
    )
    size_value = AS.AXValueCreate(
        AS.kAXValueCGSizeType, AS.CGSize(rect.width(), rect.height())
    )
    e1 = AS.AXUIElementSetAttributeValue(window_ref, AS.kAXPositionAttribute, pos_value)
    e2 = AS.AXUIElementSetAttributeValue(window_ref, AS.kAXSizeAttribute, size_value)
    if e1 != 0 or e2 != 0:
        return False, f"AX 창 배치 실패 (pos={e1}, size={e2})"
    return True, "ok"


def _read_macos_pid_rect(pid: int) -> QRect | None:
    try:
        import ApplicationServices as AS  # type: ignore
    except Exception:
        return None
    try:
        app_ref = AS.AXUIElementCreateApplication(int(pid))
        err, windows = AS.AXUIElementCopyAttributeValue(app_ref, AS.kAXWindowsAttribute, None)
        if err != 0 or not windows:
            return None
        window_ref = windows[0]
        e1, pos_val = AS.AXUIElementCopyAttributeValue(window_ref, AS.kAXPositionAttribute, None)
        e2, size_val = AS.AXUIElementCopyAttributeValue(window_ref, AS.kAXSizeAttribute, None)
        if e1 != 0 or e2 != 0:
            return None
        ok1, pt = AS.AXValueGetValue(pos_val, AS.kAXValueCGPointType, None)
        ok2, sz = AS.AXValueGetValue(size_val, AS.kAXValueCGSizeType, None)
        if not ok1 or not ok2:
            return None
        return QRect(int(pt.x), int(pt.y), int(sz.width), int(sz.height))
    except Exception:
        return None


def read_ide_rect(hwnd: int, *, pid: int | None = None) -> QRect | None:
    """IDE 창의 현재 위치·크기 — 사용자가 직접 드래그했는지 감지하는 용도."""
    if sys.platform == "darwin":
        if not pid:
            return None
        return _read_macos_pid_rect(pid)
    if sys.platform != "win32" or hwnd <= 0:
        return None
    try:
        import win32gui  # type: ignore

        if not win32gui.IsWindow(hwnd):
            return None
        left, top, right, bot = win32gui.GetWindowRect(hwnd)
        physical = QRect(left, top, right - left, bot - top)
        # GetWindowRect는 physical 픽셀 — Qt(DIP) 좌표계와 맞춰 반환
        scale = _dpi_scale_for_hwnd(hwnd)
        if scale != 1.0:
            return _scale_rect(physical, 1.0 / scale)
        return physical
    except Exception:
        return None


def place_hwnd(hwnd: int, rect: QRect, *, pid: int | None = None) -> tuple[bool, str]:
    """HWND(win32) 또는 PID(macOS)의 창을 지정 사각형으로 이동·리사이즈."""
    if sys.platform == "darwin":
        if not pid:
            return False, "macOS는 pid가 필요합니다"
        return _place_macos_pid(pid, rect)
    if sys.platform != "win32" or hwnd <= 0:
        return False, "Windows HWND만 지원"
    try:
        import win32con  # type: ignore
        import win32gui  # type: ignore

        if not win32gui.IsWindow(hwnd):
            return False, "invalid hwnd"
        # 최대화/최소화면 복원 후 좌표 적용 (Cursor가 중앙 창으로 남는 원인)
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        except Exception:
            pass
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        # SetWindowPos는 physical 픽셀을 기대 — rect는 Qt(DIP) 좌표계이므로
        # 배율을 곱해 physical로 변환 (안 하면 200% 배율에서 절반 크기로 배치됨)
        scale = _dpi_scale_for_hwnd(hwnd)
        physical = _scale_rect(rect, scale) if scale != 1.0 else rect
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOP,
            int(physical.left()),
            int(physical.top()),
            int(physical.width()),
            int(physical.height()),
            win32con.SWP_SHOWWINDOW | win32con.SWP_FRAMECHANGED,
        )
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def is_ide_maximized(hwnd: int, rect: QRect | None, work: QRect) -> bool:
    """IDE 창이 최대화(또는 work area 전체를 덮음) 상태인지.

    Windows는 IsZoomed로 정확히 판정한다. macOS(HWND 없음) 등은 rect가 work area를
    거의 다 덮었는지로 근사한다 — 이 경우를 "사용자 드래그"로 오인해 companion
    sync가 Iris 폭을 0으로 밀어버리는 버그를 막기 위한 판정이다."""
    if sys.platform == "win32" and hwnd > 0:
        try:
            import win32gui  # type: ignore

            if win32gui.IsWindow(hwnd):
                return bool(win32gui.IsZoomed(hwnd))
        except Exception:
            pass
    if rect is None:
        return False
    return rect.width() >= work.width() * 0.92 and rect.height() >= work.height() * 0.85


def place_qt_window(window: QWidget, rect: QRect) -> None:
    if window.isMaximized() or window.isFullScreen():
        window.showNormal()
    window.setGeometry(rect)
    window.raise_()
    window.activateWindow()


def tile_ide_and_iris(
    ide_hwnd: int,
    iris_window: QWidget,
    *,
ide_ratio: float = 0.8,
    ide_pid: int | None = None,
) -> tuple[bool, str]:
    """IDE 왼쪽 ~80%, Iris 오른쪽 나머지.

    ide_pid: macOS에서 창 이동에 필요 (HWND가 없어 PID의 AX 창을 옮긴다)."""
    tiles = compute_tile_rects(work_area_for(iris_window), ide_ratio=ide_ratio)
    ok, err = place_hwnd(ide_hwnd, tiles.ide, pid=ide_pid)
    if not ok:
        return False, err
    place_qt_window(iris_window, tiles.iris)
    # Cursor 등이 자체 복원으로 되돌리는 경우 대비 — 즉시 한 번 더
    place_hwnd(ide_hwnd, tiles.ide, pid=ide_pid)
    return True, "ok"


if __name__ == "__main__":
    w = QRect(0, 0, 1000, 800)
    t = compute_tile_rects(w)
    assert t.ide.width() == 800
    assert t.iris.width() == 200
    assert t.ide.left() == 0
    assert t.iris.left() == 800
    print("ide_tiler ok")
