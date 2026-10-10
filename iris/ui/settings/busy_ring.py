"""설정 창이 내용을 붙이는 동안 도는 원형 표시."""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from iris.ui.shared.theme_tokens import TOKENS


class BusyRing(QWidget):
    """안드로이드 원형 진행처럼 호가 계속 회전한다."""

    def __init__(self, parent: QWidget | None = None, *, diameter: int = 48) -> None:
        super().__init__(parent)
        self._angle = 0
        self.setFixedSize(diameter, diameter)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def angle(self) -> int:
        return self._angle

    def _tick(self) -> None:
        self._angle = (self._angle + 8) % 360
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        self.stop()
        super().hideEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        inset = 4.0
        rect = QRectF(inset, inset, self.width() - inset * 2, self.height() - inset * 2)
        track = QPen(QColor(TOKENS.text_muted))
        track.setWidth(4)
        track.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track)
        painter.drawArc(rect, 0, 360 * 16)
        arc = QPen(QColor(TOKENS.neon_cyan))
        arc.setWidth(4)
        arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc)
        painter.drawArc(rect, int(self._angle * 16), 110 * 16)
        painter.end()


class SettingsBusyOverlay(QWidget):
    """스크롤 영역 위를 덮고, 섹션이 끝날 때까지 원형 표시를 보여 준다."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsBusyOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#SettingsBusyOverlay {{ background-color: {TOKENS.space_deep}; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addStretch(1)
        self.ring = BusyRing(self)
        lay.addWidget(self.ring, 0, Qt.AlignmentFlag.AlignHCenter)
        caption = QLabel("불러오는 중")
        caption.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        caption.setStyleSheet(
            f"color: {TOKENS.text_secondary}; background: transparent; font-size: 13px;"
        )
        lay.addWidget(caption)
        lay.addStretch(1)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.ring.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        self.ring.stop()
        super().hideEvent(event)
