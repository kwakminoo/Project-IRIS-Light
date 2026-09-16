"""IDE 웰컴 화면용 테두리 전용 아이콘."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from iris.ui.shared.theme_tokens import TOKENS

_ICON_SIZE = 28


class WelcomeOutlineIcon(QWidget):
    """채움 없이 stroke만 — Open folder / Create folder / SSH."""

    def __init__(self, kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._kind = kind
        self.setFixedSize(_ICON_SIZE, _ICON_SIZE)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(_ICON_SIZE, _ICON_SIZE)

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(TOKENS.text_secondary))
        pen.setWidthF(1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        w, h = self.width(), self.height()
        if self._kind == "folder":
            self._paint_folder(p, w, h)
        elif self._kind == "folder_plus":
            self._paint_folder(p, w, h)
            cx, cy = w * 0.72, h * 0.28
            p.drawLine(int(cx - 5), int(cy), int(cx + 5), int(cy))
            p.drawLine(int(cx), int(cy - 5), int(cx), int(cy + 5))
        else:
            self._paint_terminal(p, w, h)
        p.end()

    def _paint_folder(self, p: QPainter, w: int, h: int) -> None:
        tab_l = w * 0.18
        tab_r = w * 0.48
        top = h * 0.30
        body_top = h * 0.40
        p.drawLine(int(tab_l), int(top), int(tab_r), int(top))
        p.drawLine(int(tab_r), int(top), int(tab_r + w * 0.08), int(body_top))
        p.drawRect(int(w * 0.14), int(body_top), int(w * 0.72), int(h * 0.48))

    def _paint_terminal(self, p: QPainter, w: int, h: int) -> None:
        p.drawRoundedRect(int(w * 0.12), int(h * 0.14), int(w * 0.76), int(h * 0.72), 3, 3)
        ox, oy = int(w * 0.28), int(h * 0.46)
        p.drawLine(ox, oy, ox + 6, oy + 5)
        p.drawLine(ox + 6, oy + 5, ox, oy + 10)
        p.drawLine(int(w * 0.48), int(h * 0.58), int(w * 0.72), int(h * 0.58))
