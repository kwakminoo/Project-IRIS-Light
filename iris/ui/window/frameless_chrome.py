"""프레임리스 창 가장자리 리사이즈."""

from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QCursor, QMouseEvent
from PyQt6.QtWidgets import QApplication, QWidget

from iris.ui.shared.theme_tokens import TOKENS

_RESIZE_MARGIN = 8

# 가장자리 그립 배치 순서: TL, T, TR, L, R, BL, B, BR
_GRIP_EDGES: tuple[Qt.Edge, ...] = (
    Qt.Edge.TopEdge | Qt.Edge.LeftEdge,
    Qt.Edge.TopEdge,
    Qt.Edge.TopEdge | Qt.Edge.RightEdge,
    Qt.Edge.LeftEdge,
    Qt.Edge.RightEdge,
    Qt.Edge.BottomEdge | Qt.Edge.LeftEdge,
    Qt.Edge.BottomEdge,
    Qt.Edge.BottomEdge | Qt.Edge.RightEdge,
)


def _cursor_for_edges(edges: Qt.Edge) -> Qt.CursorShape:
    has_l = bool(edges & Qt.Edge.LeftEdge)
    has_r = bool(edges & Qt.Edge.RightEdge)
    has_t = bool(edges & Qt.Edge.TopEdge)
    has_b = bool(edges & Qt.Edge.BottomEdge)
    if has_t and has_l or has_b and has_r:
        return Qt.CursorShape.SizeFDiagCursor
    if has_t and has_r or has_b and has_l:
        return Qt.CursorShape.SizeBDiagCursor
    if has_l or has_r:
        return Qt.CursorShape.SizeHorCursor
    if has_t or has_b:
        return Qt.CursorShape.SizeVerCursor
    return Qt.CursorShape.ArrowCursor


def suppress_native_window_border(window: QWidget) -> None:
    """Windows DWM 1px 테두리 제거 — frameless 창."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.winId())
    except (AttributeError, TypeError, RuntimeError):
        return
    if hwnd == 0:
        return
    try:
        import ctypes

        dwm = ctypes.windll.dwmapi
        # DWMWA_BORDER_COLOR — Win11 기본 리사이즈 테두리 숨김
        border_color = ctypes.c_uint(0xFFFFFFFE)  # DWMWA_COLOR_NONE
        dwm.DwmSetWindowAttribute(
            hwnd,
            34,
            ctypes.byref(border_color),
            ctypes.sizeof(border_color),
        )
        # DWMWA_NCRENDERING_POLICY = DWMNCRP_DISABLED
        policy = ctypes.c_int(1)
        dwm.DwmSetWindowAttribute(
            hwnd,
            2,
            ctypes.byref(policy),
            ctypes.sizeof(policy),
        )
    except (OSError, AttributeError):
        pass


def _colorref(hex_color: str) -> int:
    """Qt hex(#RRGGBB) → Win32 COLORREF(0x00BBGGRR)."""
    c = QColor(hex_color)
    return (c.blue() << 16) | (c.green() << 8) | c.red()


def force_dark_titlebar(window: QWidget) -> None:
    """네이티브 타이틀바(설정/프로필/시작 프로토콜 등 QDialog용)를 앱 다크 테마로 고정.

    프레임리스가 아닌 대화상자는 Windows가 타이틀바를 직접 그리므로, 사용자의
    OS 라이트모드·강조색 설정에 따라 PC마다 맨 위쪽 색이 달라 보였다. 이 설정과
    무관하게 항상 동일하게 보이도록 DWM에 다크모드 + 앱 색상을 강제한다.
    """
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.winId())
    except (AttributeError, TypeError, RuntimeError):
        return
    if hwnd == 0:
        return
    try:
        import ctypes

        dwm = ctypes.windll.dwmapi
        use_dark = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE — 신/구 빌드 호환
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(use_dark), ctypes.sizeof(use_dark))
        # Win11 22000+ 전용 — 실패해도 위 다크모드 설정으로 대부분 충분히 일관됨
        caption = ctypes.c_uint(_colorref(TOKENS.space_deep))
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), ctypes.sizeof(caption))  # DWMWA_CAPTION_COLOR
        text_color = ctypes.c_uint(_colorref(TOKENS.text_primary))
        dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text_color), ctypes.sizeof(text_color))  # DWMWA_TEXT_COLOR
    except (OSError, AttributeError):
        pass


class _ResizeGrip(QWidget):
    """투명 리사이즈 핸들 — startSystemResize 위임."""

    def __init__(self, host: QWidget, edges: Qt.Edge, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self._edges = edges
        self.setCursor(QCursor(_cursor_for_edges(edges)))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setStyleSheet("background: transparent; border: none;")

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and not self._host.isMaximized():
            handle = self._host.windowHandle()
            if handle is not None and handle.startSystemResize(self._edges):
                event.accept()
                return
        super().mousePressEvent(event)


class FramelessShell(QWidget):
    """콘텐츠를 창 전체에 깔고 가장자리 리사이즈 그립만 겹친다."""

    def __init__(self, host: QWidget, margin: int = _RESIZE_MARGIN, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self._margin = margin
        self.setObjectName("FramelessShell")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent; border: none;")
        self._content: QWidget | None = None
        self._grips: list[_ResizeGrip] = []

    def set_center_widget(self, content: QWidget) -> None:
        """본문을 전체 영역에 배치하고 투명 리사이즈 그립을 가장자리에 겹친다."""
        self._content = content
        content.setParent(self)
        content.lower()

        for edges in _GRIP_EDGES:
            grip = _ResizeGrip(self._host, edges, self)
            self._grips.append(grip)

        self._sync_layout()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_layout()

    def set_left_grips_visible(self, visible: bool) -> None:
        """Companion 80:20 — IDE와 맞닿은 왼쪽 가장자리 리사이즈 그립 숨김."""
        if len(self._grips) < 6:
            return
        for idx in (0, 3, 5):
            self._grips[idx].setVisible(visible)

    def _sync_layout(self) -> None:
        if self._content is not None:
            self._content.setGeometry(0, 0, self.width(), self.height())

        if not self._grips:
            return

        m = self._margin
        w, h = max(self.width(), 1), max(self.height(), 1)
        inner_w = max(1, w - 2 * m)
        inner_h = max(1, h - 2 * m)
        rects = (
            (0, 0, m, m),
            (m, 0, inner_w, m),
            (w - m, 0, m, m),
            (0, m, m, inner_h),
            (w - m, m, m, inner_h),
            (0, h - m, m, m),
            (m, h - m, inner_w, m),
            (w - m, h - m, m, m),
        )
        for grip, (x, y, gw, gh) in zip(self._grips, rects, strict=True):
            grip.setGeometry(x, y, gw, gh)
            grip.raise_()


def center_on_screen(widget: QWidget) -> None:
    """주 모니터 가용 영역 중앙에 배치."""
    try:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        widget.move(
            area.x() + max(0, (area.width() - widget.width()) // 2),
            area.y() + max(0, (area.height() - widget.height()) // 2),
        )
    except RuntimeError:
        pass
