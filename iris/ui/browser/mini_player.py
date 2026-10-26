from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QEvent, QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizeGrip, QVBoxLayout, QWidget

from iris.ui.shared.theme_tokens import TOKENS

if TYPE_CHECKING:
    from PyQt6.QtWebEngineWidgets import QWebEngineView


_MINI_W = 240
_MINI_H = 135
_MIN_SIZE = QSize(200, 112)
_GRIP = 16
_MARGIN = 8

_SHARED_MINI: BrowserMiniPlayer | None = None


def _mini_stylesheet() -> str:
    t = TOKENS
    return f"""
    QWidget#IrisBrowserMiniPlayer {{
        background: {t.void_black};
        border: 1px solid {t.border_subtle};
    }}
    QLabel#IrisBrowserMiniTitle {{
        color: {t.text_primary};
        font-family: {t.font_family};
        font-size: 12px;
        padding-left: 4px;
    }}
    QPushButton#IrisBrowserMiniBtn {{
        background: {t.background_secondary};
        color: {t.text_primary};
        border: 1px solid {t.border_subtle};
        border-radius: 4px;
        padding: 2px 8px;
        font-family: {t.font_family};
        min-width: 28px;
    }}
    """


def _input_reserve(host: QWidget | None) -> int:
    if host is None:
        return _MARGIN
    area = getattr(host, "_input_area", None)
    if area is None or not hasattr(area, "height"):
        return _MARGIN
    try:
        return max(_MARGIN, int(area.height()) + _MARGIN)
    except Exception:
        return _MARGIN


def _tool_flags() -> Qt.WindowType:
    return (
        Qt.WindowType.Tool
        | Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowStaysOnTopHint
    )


def get_shared_browser_mini(parent: QWidget | None = None) -> BrowserMiniPlayer:
    global _SHARED_MINI
    if _SHARED_MINI is None:
        _SHARED_MINI = BrowserMiniPlayer(parent)
    return _SHARED_MINI


def reset_shared_browser_mini_for_tests() -> None:
    global _SHARED_MINI
    mini = _SHARED_MINI
    _SHARED_MINI = None
    if mini is not None:
        mini.hide()
        mini.deleteLater()


class BrowserMiniPlayer(QWidget):
    """One QWebEngineView host. Tool window so Chromium is not parented into
    a translucent ChatPanel (that path access-violates). Geometry follows the
    chat widget so the player sits in the chat column like mobile PIP.
    """

    expand_requested = pyqtSignal()
    close_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, _tool_flags())
        self.setObjectName("IrisBrowserMiniPlayer")
        self.setStyleSheet(_mini_stylesheet())
        self.setMinimumSize(_MIN_SIZE)
        self.resize(_MINI_W, _MINI_H)
        self._view: QWebEngineView | None = None
        self._drag_origin: QPoint | None = None
        self._signals_wired = False
        self._anchor: QWidget | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QHBoxLayout()
        bar.setContentsMargins(6, 4, 6, 4)
        bar.setSpacing(4)
        self._title = QLabel("YouTube")
        self._title.setObjectName("IrisBrowserMiniTitle")
        expand = QPushButton("▢")
        expand.setObjectName("IrisBrowserMiniBtn")
        expand.setToolTip("Expand to browser panel")
        expand.setCursor(Qt.CursorShape.PointingHandCursor)
        close = QPushButton("×")
        close.setObjectName("IrisBrowserMiniBtn")
        close.setToolTip("Close mini player")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        bar.addWidget(self._title, 1)
        bar.addWidget(expand)
        bar.addWidget(close)
        root.addLayout(bar)
        self._bar_h = 28

        self._view_slot = QWidget()
        self._view_lay = QVBoxLayout(self._view_slot)
        self._view_lay.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._view_slot, 1)

        self._grip = QSizeGrip(self)
        self._grip.setFixedSize(_GRIP, _GRIP)

        expand.clicked.connect(self.expand_requested.emit)
        close.clicked.connect(self.close_requested.emit)

    def signals_wired(self) -> bool:
        return self._signals_wired

    def mark_signals_wired(self) -> None:
        self._signals_wired = True

    def is_overlay(self) -> bool:
        return self._anchor is not None and self.isVisible()

    def attach_view(self, view) -> None:
        if view is None:
            return
        if self._view is view and view.parent() is self._view_slot:
            return
        self._view_lay.addWidget(view)
        self._view = view
        try:
            title = view.title()
            if title:
                self._title.setText(title[:40])
        except Exception:
            pass

    def detach_view(self):
        view = self._view
        if view is None:
            return None
        self._view_lay.removeWidget(view)
        self._view = None
        return view

    def has_view(self) -> bool:
        return self._view is not None

    def _set_anchor(self, host: QWidget | None) -> None:
        if self._anchor is host:
            return
        if self._anchor is not None:
            self._anchor.removeEventFilter(self)
        self._anchor = host
        if host is not None:
            host.installEventFilter(self)

    def show_in_chat(self, chat: QWidget | None = None) -> None:
        host = chat or self._anchor or self.parentWidget()
        self._set_anchor(host)
        self._fit_default_size()
        self._place_default()
        self._clamp_to_anchor()
        self.show()
        self.raise_()

    def show_anchored(self, anchor: QWidget | None = None) -> None:
        self.show_in_chat(anchor)

    def _anchor_rect(self) -> QRect | None:
        host = self._anchor
        if host is None:
            return None
        top_left = host.mapToGlobal(QPoint(0, 0))
        return QRect(top_left, host.size())

    def _fit_default_size(self) -> None:
        box = self._anchor_rect()
        if box is None:
            self.resize(_MINI_W, _MINI_H)
            return
        reserve = _input_reserve(self._anchor)
        max_w = max(_MIN_SIZE.width(), box.width() - 2 * _MARGIN)
        max_h = max(_MIN_SIZE.height(), box.height() - reserve - _MARGIN)
        self.setMaximumSize(max_w, max_h)
        self.resize(min(_MINI_W, max_w), min(_MINI_H, max_h))

    def _place_default(self) -> None:
        box = self._anchor_rect()
        if box is None:
            return
        reserve = _input_reserve(self._anchor)
        x = box.x() + max(_MARGIN, box.width() - self.width() - _MARGIN)
        y = box.y() + max(_MARGIN, box.height() - self.height() - reserve)
        self.move(x, y)

    def _clamp_to_anchor(self) -> None:
        box = self._anchor_rect()
        if box is None:
            self._place_grip()
            return
        reserve = _input_reserve(self._anchor)
        max_w = max(_MIN_SIZE.width(), box.width() - 2 * _MARGIN)
        max_h = max(_MIN_SIZE.height(), box.height() - reserve - _MARGIN)
        w = min(self.width(), max_w)
        h = min(self.height(), max_h)
        if w != self.width() or h != self.height():
            self.resize(w, h)
        min_x = box.x() + _MARGIN
        min_y = box.y() + _MARGIN
        max_x = box.x() + max(_MARGIN, box.width() - self.width() - _MARGIN)
        max_y = box.y() + max(_MARGIN, box.height() - self.height() - reserve)
        x = min(max(min_x, self.x()), max_x)
        y = min(max(min_y, self.y()), max_y)
        if x != self.x() or y != self.y():
            self.move(x, y)
        self._place_grip()

    def contained_in_anchor(self) -> bool:
        box = self._anchor_rect()
        if box is None:
            return False
        reserve = _input_reserve(self._anchor)
        usable = QRect(
            box.x(),
            box.y(),
            box.width(),
            max(0, box.height() - reserve),
        )
        return usable.intersects(self.frameGeometry())

    def _place_grip(self) -> None:
        self._grip.move(self.width() - _GRIP, self.height() - _GRIP)
        self._grip.raise_()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._anchor and event.type() in (QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show):
            if self.isVisible():
                self._clamp_to_anchor()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._place_grip()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            local = event.position().toPoint()
            if local.y() <= self._bar_h and local.x() < self.width() - 72:
                self._drag_origin = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_origin)
            self._clamp_to_anchor()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_origin = None
        super().mouseReleaseEvent(event)
