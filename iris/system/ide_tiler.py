"""IDE / Iris 창을 주 모니터 work area 기준 80:20 타일 배치."""

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
    ratio = min(0.95, max(0.5, float(ide_ratio)))
    ide_w = int(work.width() * ratio)
    iris_w = work.width() - ide_w
    ide = QRect(work.left(), work.top(), ide_w, work.height())
    iris = QRect(work.left() + ide_w, work.top(), iris_w, work.height())
    return TileRects(work=work, ide=ide, iris=iris)


def place_hwnd(hwnd: int, rect: QRect) -> tuple[bool, str]:
    """HWND를 지정 사각형으로 이동·리사이즈."""
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
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOP,
            int(rect.left()),
            int(rect.top()),
            int(rect.width()),
            int(rect.height()),
            win32con.SWP_SHOWWINDOW | win32con.SWP_FRAMECHANGED,
        )
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


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
) -> tuple[bool, str]:
    """IDE 왼쪽 ~80%, Iris 오른쪽 나머지."""
    tiles = compute_tile_rects(work_area_for(iris_window), ide_ratio=ide_ratio)
    ok, err = place_hwnd(ide_hwnd, tiles.ide)
    if not ok:
        return False, err
    place_qt_window(iris_window, tiles.iris)
    # Cursor 등이 자체 복원으로 되돌리는 경우 대비 — 즉시 한 번 더
    place_hwnd(ide_hwnd, tiles.ide)
    return True, "ok"


if __name__ == "__main__":
    w = QRect(0, 0, 1000, 800)
    t = compute_tile_rects(w)
    assert t.ide.width() == 800
    assert t.iris.width() == 200
    assert t.ide.left() == 0
    assert t.iris.left() == 800
    print("ide_tiler ok")
