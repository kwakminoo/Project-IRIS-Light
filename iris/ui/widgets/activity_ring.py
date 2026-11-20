"""공유 원형 활동 링 — 채팅 목록·모델 정리 상태줄 공통."""

from __future__ import annotations

from enum import Enum

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget


class ActivityKind(str, Enum):
    IDLE = "idle"
    WORKING = "working"
    DONE = "done"
    FAILED = "failed"


class ActivityRing(QWidget):
    """Cyan spinning arc while working; soft blue/red dot when done/failed."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(12, 16)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._kind = ActivityKind.IDLE
        self._phase = 0.0
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(33)
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self.hide()

    def kind(self) -> ActivityKind:
        return self._kind

    def set_kind(self, kind: ActivityKind, phase: float | None = None) -> None:
        next_kind = kind if isinstance(kind, ActivityKind) else ActivityKind.IDLE
        if phase is not None:
            self._phase = float(phase)
        elif next_kind != self._kind:
            self._phase = 0.0
        self._kind = next_kind
        self.setVisible(self._kind != ActivityKind.IDLE)
        if self._kind == ActivityKind.WORKING:
            if not self._anim_timer.isActive():
                self._anim_timer.start()
        elif self._anim_timer.isActive():
            self._anim_timer.stop()
        self.update()

    def set_working(self, working: bool) -> None:
        self.set_kind(ActivityKind.WORKING if working else ActivityKind.IDLE)

    def _on_anim_tick(self) -> None:
        self._phase = (self._phase + 0.06) % 1.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        if self._kind == ActivityKind.IDLE:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        if self._kind == ActivityKind.WORKING:
            radius = 4.5
            rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
            pen = QPen(QColor(125, 211, 252, 230))
            pen.setWidthF(1.7)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            span = int(100 * 16)
            start = int((-self._phase * 360.0) * 16)
            painter.drawArc(rect, start, span)
            pen.setColor(QColor(125, 211, 252, 55))
            painter.setPen(pen)
            painter.drawArc(rect, start + span, int(260 * 16))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(
                QColor(248, 113, 113, 230)
                if self._kind == ActivityKind.FAILED
                else QColor(147, 197, 253, 210)
            )
            painter.drawEllipse(QPointF(cx, cy), 3.2, 3.2)
        painter.end()
