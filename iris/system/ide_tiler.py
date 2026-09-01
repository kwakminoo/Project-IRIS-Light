"""IDE / Iris 창을 주 모니터 work area 기준 80:20 타일 배치.

계약 (회귀 방지 — .cursor/rules/ide-companion-tile-8020.mdc):
- PyQt(IrisIdeWindow, MainWindow): place_qt_window = setGeometry only; read_qt_window_rect = frameGeometry.
- 외부 IDE(Cursor HWND): place_hwnd + read_ide_rect (Win32, DPI→physical).
- compute_tile_rects: 정수 픽셀 8:2 — ide.width + iris.width == work.width, seam 겹침·틈 없음.
"""

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


def compute_tile_rects(work: QRect, *, ide_ratio: float = 0.8) -> TileRects:
    """work area를 정수 픽셀로 8:2 (또는 ide_ratio) 분할 — 틈·겹침 없음."""
    ratio = min(0.95, max(0.5, float(ide_ratio)))
    total_w = int(work.width())
    ide_w = int(total_w * ratio)
    iris_w = total_w - ide_w
    left = int(work.left())
    top = int(work.top())
    h = int(work.height())
    ide = QRect(left, top, ide_w, h)
    iris = QRect(left + ide_w, top, iris_w, h)
    return TileRects(work=work, ide=ide, iris=iris)


def iris_rect_from_ide_edge(
    work: QRect,
    ide_rect: QRect,
    *,
    min_iris_width: int = 0,
) -> QRect:
    """IDE 오른쪽 경계에 Iris를 픽셀 단위로 맞춤 (겹침 없음)."""
    iris_left = int(ide_rect.left()) + int(ide_rect.width())
    iris_width = int(work.left()) + int(work.width()) - iris_left
    if min_iris_width > 0 and iris_width < min_iris_width:
        iris_width = min_iris_width
        iris_left = int(work.left()) + int(work.width()) - iris_width
    return QRect(iris_left, int(work.top()), iris_width, int(work.height()))


def tiles_are_flush(ide_rect: QRect, iris_rect: QRect) -> bool:
    """IDE 오른쪽 == Iris 왼쪽 (픽셀 단위, 겹침·틈 없음)."""
    return int(ide_rect.left()) + int(ide_rect.width()) == int(iris_rect.left())


def tiles_have_overlap(ide_rect: QRect, iris_rect: QRect) -> bool:
    """Iris가 IDE 프레임과 겹치면 True."""
    return int(iris_rect.left()) < int(ide_rect.left()) + int(ide_rect.width())


def _iris_rect_at_seam(work: QRect, seam_x: int) -> QRect:
    seam_x = int(seam_x)
    iris_w = int(work.left()) + int(work.width()) - seam_x
    return QRect(seam_x, int(work.top()), max(1, iris_w), int(work.height()))


def enforce_qt_companion_flush(
    ide_window: QWidget,
    iris_window: QWidget,
    work: QRect | None = None,
) -> None:
    """IDE 실측 오른쪽에 Iris를 붙임 — WM/DWM 반올림·겹침 제거."""
    if work is None:
        work = work_area_for(iris_window)
    ide_r = read_qt_window_rect(ide_window)
    if ide_r is None:
        place_qt_window(iris_window, compute_tile_rects(work).iris)
        return
    seam_x = int(ide_r.left()) + int(ide_r.width())
    place_qt_window(iris_window, _iris_rect_at_seam(work, seam_x))
    for _ in range(3):
        iris_r = read_qt_window_rect(iris_window)
        if iris_r is None:
            break
        drift = seam_x - int(iris_r.left())
        if drift == 0:
            break
        place_qt_window(
            iris_window,
            _iris_rect_at_seam(work, seam_x),
        )
        ide_r = read_qt_window_rect(ide_window)
        if ide_r is not None:
            seam_x = int(ide_r.left()) + int(ide_r.width())


def enforce_hwnd_companion_flush(
    ide_hwnd: int,
    iris_window: QWidget,
    work: QRect | None = None,
    *,
    ide_pid: int | None = None,
) -> None:
    """외부 IDE HWND 실측 후 Iris flush."""
    if work is None:
        work = work_area_for(iris_window)
    ide_r = read_ide_rect(ide_hwnd, pid=ide_pid)
    if ide_r is None:
        place_qt_window(iris_window, compute_tile_rects(work).iris)
        return
    seam_x = int(ide_r.left()) + int(ide_r.width())
    place_qt_window(iris_window, _iris_rect_at_seam(work, seam_x))
    for _ in range(3):
        iris_r = read_qt_window_rect(iris_window)
        if iris_r is None:
            break
        if int(iris_r.left()) == seam_x:
            break
        ide_r = read_ide_rect(ide_hwnd, pid=ide_pid)
        if ide_r is not None:
            seam_x = int(ide_r.left()) + int(ide_r.width())
        place_qt_window(iris_window, _iris_rect_at_seam(work, seam_x))


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
    return _read_hwnd_rect(hwnd, pid=pid)


def read_qt_window_rect(window: QWidget) -> QRect | None:
    """Qt frame geometry (DIP) — setGeometry과 동일 좌표계."""
    geo = window.frameGeometry()
    if geo.isValid() and geo.width() > 0 and geo.height() > 0:
        return geo
    return None


def _read_hwnd_rect(hwnd: int, *, pid: int | None = None) -> QRect | None:
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
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        except Exception:
            pass
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
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
    """IDE 창이 최대화(또는 work area 전체를 덮음) 상태인지."""
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
    """Qt 위젯 배치 — setGeometry만 (Qt DIP). Win32 SetWindowPos 금지 — ide-companion-tile-8020."""
    if window.isMaximized() or window.isFullScreen():
        window.showNormal()
    window.setGeometry(rect)
    window.raise_()
    window.activateWindow()


def seal_qt_companion_seam(
    ide_window: QWidget,
    iris_window: QWidget,
    *,
    min_iris_width: int = 0,
) -> None:
    """PyQt IDE + Iris — 드래그 후 Iris를 IDE 오른쪽에 픽셀 맞춤."""
    work = work_area_for(iris_window)
    enforce_qt_companion_flush(ide_window, iris_window, work)
    if min_iris_width <= 0:
        return
    iris_r = read_qt_window_rect(iris_window)
    if iris_r is not None and iris_r.width() < min_iris_width:
        place_qt_window(
            iris_window,
            iris_rect_from_ide_edge(
                work,
                read_qt_window_rect(ide_window) or compute_tile_rects(work).ide,
                min_iris_width=min_iris_width,
            ),
        )


def seal_companion_seam(
    ide_hwnd: int,
    iris_window: QWidget,
    *,
    ide_pid: int | None = None,
    min_iris_width: int = 0,
) -> None:
    """IDE HWND 실측 후 Iris를 IDE 오른쪽에 픽셀 맞춤."""
    work = work_area_for(iris_window)
    enforce_hwnd_companion_flush(ide_hwnd, iris_window, work, ide_pid=ide_pid)
    if min_iris_width <= 0:
        return
    iris_r = read_qt_window_rect(iris_window)
    if iris_r is not None and iris_r.width() < min_iris_width:
        ide_rect = read_ide_rect(ide_hwnd, pid=ide_pid) or compute_tile_rects(work).ide
        place_qt_window(
            iris_window,
            iris_rect_from_ide_edge(work, ide_rect, min_iris_width=min_iris_width),
        )


def tile_iris_ide_and_iris(
    iris_ide_window: QWidget,
    iris_window: QWidget,
    *,
    ide_ratio: float = 0.8,
) -> tuple[bool, str]:
    """IRIS IDE(PyQt) + Iris MainWindow — 정수 픽셀 80:20, 틈·겹침 없음."""
    from PyQt6.QtWidgets import QApplication

    work = work_area_for(iris_window)
    tiles = compute_tile_rects(work, ide_ratio=ide_ratio)
    place_qt_window(iris_ide_window, tiles.ide)
    QApplication.processEvents()
    enforce_qt_companion_flush(iris_ide_window, iris_window, work)
    return True, "ok"


def tile_ide_and_iris(
    ide_hwnd: int,
    iris_window: QWidget,
    *,
    ide_ratio: float = 0.8,
    ide_pid: int | None = None,
    min_iris_width: int = 0,
) -> tuple[bool, str]:
    """IDE 왼쪽 80%, Iris 오른쪽 20% — 정수 픽셀, 틈·겹침 없음."""
    work = work_area_for(iris_window)
    tiles = compute_tile_rects(work, ide_ratio=ide_ratio)
    ok, err = place_hwnd(ide_hwnd, tiles.ide, pid=ide_pid)
    if not ok:
        return False, err
    enforce_hwnd_companion_flush(ide_hwnd, iris_window, work, ide_pid=ide_pid)
    # Cursor 등이 자체 복원으로 되돌리는 경우 대비
    place_hwnd(ide_hwnd, tiles.ide, pid=ide_pid)
    enforce_hwnd_companion_flush(ide_hwnd, iris_window, work, ide_pid=ide_pid)
    if min_iris_width > 0:
        seal_companion_seam(
            ide_hwnd,
            iris_window,
            ide_pid=ide_pid,
            min_iris_width=min_iris_width,
        )
    return True, "ok"


if __name__ == "__main__":
    w = QRect(0, 0, 1000, 800)
    t = compute_tile_rects(w)
    assert t.ide.width() == 800
    assert t.iris.width() == 200
    assert t.ide.left() + t.ide.width() == t.iris.left()
    assert t.ide.width() + t.iris.width() == w.width()
    assert tiles_are_flush(t.ide, t.iris)
    w2 = QRect(0, 0, 1921, 800)
    t2 = compute_tile_rects(w2)
    assert t2.ide.width() + t2.iris.width() == w2.width()
    assert tiles_are_flush(t2.ide, t2.iris)
    print("ide_tiler ok")
