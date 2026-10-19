"""Floating mini-player chrome — holds the same QWebEngineView via reparent."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from iris.ui.shared.theme_tokens import TOKENS

if TYPE_CHECKING:
    from PyQt6.QtWebEngineWidgets import QWebEngineView


_MINI_W = 480
_MINI_H = 270


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


class BrowserMiniPlayer(QWidget):
    """Frameless Tool window; view slot may hold the panel's QWebEngineView."""

    expand_requested = pyqtSignal()
    close_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        super().__init__(parent, flags)
        self.setObjectName("IrisBrowserMiniPlayer")
        self.setStyleSheet(_mini_stylesheet())
        self.setFixedSize(_MINI_W, _MINI_H)
        self._view: QWebEngineView | None = None
        self._drag_origin: QPoint | None = None

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

        self._view_slot = QWidget()
        self._view_lay = QVBoxLayout(self._view_slot)
        self._view_lay.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._view_slot, 1)

        expand.clicked.connect(self.expand_requested.emit)
        close.clicked.connect(self.close_requested.emit)

    def attach_view(self, view) -> None:
        if view is None:
            return
        if self._view is view and view.parent() is self._view_slot:
            return
        self._view_lay.addWidget(view)
        self._view = view

    def detach_view(self):
        view = self._view
        if view is None:
            return None
        self._view_lay.removeWidget(view)
        self._view = None
        return view

    def has_view(self) -> bool:
        return self._view is not None

    def show_anchored(self, anchor: QWidget | None = None) -> None:
        host = anchor or self.parentWidget()
        if host is not None:
            geo = host.frameGeometry()
            x = geo.x() + max(8, geo.width() - _MINI_W - 16)
            y = geo.y() + max(8, geo.height() - _MINI_H - 16)
            self.move(x, y)
        self.show()
        self.raise_()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_origin)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_origin = None
        super().mouseReleaseEvent(event)
