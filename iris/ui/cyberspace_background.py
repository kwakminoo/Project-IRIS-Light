"""사이버스페이스 배경 — 성운·지평선 그리드 + 구체·UI 오버레이 레이어."""

from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QRadialGradient
from PyQt6.QtWidgets import QLayout, QWidget

from iris.ui.theme_tokens import TOKENS


class CyberspaceBackground(QWidget):
    """짙은 우주 배경 + 은은한 성운 + 디지털 지평선."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._phase = 0.0
        self._orb_layer: Optional[QWidget] = None
        self._ui_overlay: Optional[QWidget] = None
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(False)
        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._tick)

    def set_orb_layer(self, widget: QWidget) -> None:
        """구체 비주얼라이저 — 창 전체를 채우는 최하단 레이어."""
        self._orb_layer = widget
        widget.setParent(self)
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        widget.lower()
        widget.show()
        self._sync_layers()

    def set_ui_overlay(self, widget: QWidget) -> None:
        """모든 HUD·패널 — 구체 위 투명 오버레이."""
        self._ui_overlay = widget
        widget.setParent(self)
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        widget.raise_()
        widget.show()
        self._sync_layers()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_layers()

    def _sync_layers(self) -> None:
        rect = self.rect()
        # UI 오버레이·레이아웃을 먼저 확정한 뒤 orb 레이어와 anchor 동기화
        if self._ui_overlay is not None:
            self._ui_overlay.setGeometry(rect)
            self._activate_layout_chain(self._ui_overlay)
        if self._orb_layer is not None:
            self._orb_layer.setGeometry(rect)
            request_sync = getattr(self._orb_layer, "request_sync_orb_anchor", None)
            if callable(request_sync):
                request_sync("cyberspace_sync_layers")
        if self._ui_overlay is not None:
            self._ui_overlay.raise_()

    def _activate_layout_chain(self, root: QWidget) -> None:
        """오버레이 및 하위 AssistantWorkspace·Splitter 레이아웃을 즉시 반영."""
        lay = root.layout()
        if isinstance(lay, QLayout):
            lay.activate()
        for child in root.findChildren(QWidget):
            child.updateGeometry()
            child_lay = child.layout()
            if isinstance(child_lay, QLayout):
                child_lay.activate()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._timer.isActive():
            self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self._timer.stop()

    def _tick(self) -> None:
        self._phase += 0.012
        if self._phase > math.tau:
            self._phase -= math.tau
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ARG002, N802
        w, h = max(self.width(), 1), max(self.height(), 1)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 기본 void
        painter.fillRect(0, 0, w, h, QColor(TOKENS.void_black))

        # 수직 그라디언트 — 깊은 남색
        vert = QLinearGradient(0, 0, 0, h)
        vert.setColorAt(0.0, QColor(TOKENS.space_deep))
        vert.setColorAt(0.55, QColor(TOKENS.space_navy))
        vert.setColorAt(1.0, QColor("#04020a"))
        painter.fillRect(0, 0, w, h, vert)

        # 중앙 성운 — orb 뒤 에너지 필드
        cx, cy = w * 0.52, h * 0.38
        nebula_r = max(w, h) * 0.55
        nebula = QRadialGradient(cx, cy, nebula_r)
        pulse = 0.5 + 0.5 * math.sin(self._phase * 0.7)
        nebula.setColorAt(0.0, QColor(56, 189, 248, int(28 + 10 * pulse)))
        nebula.setColorAt(0.25, QColor(37, 99, 235, int(14 + 6 * pulse)))
        nebula.setColorAt(0.55, QColor(13, 40, 71, int(8 + 4 * pulse)))
        nebula.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(0, 0, w, h, nebula)

        # 보조 시안 성운
        nebula2 = QRadialGradient(w * 0.72, h * 0.28, nebula_r * 0.45)
        nebula2.setColorAt(0.0, QColor(34, 211, 238, int(10 + 5 * pulse)))
        nebula2.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(0, 0, w, h, nebula2)

        # 디지털 지평선 그리드
        self._draw_horizon_grid(painter, w, h)

        painter.end()

    def _draw_horizon_grid(self, painter: QPainter, w: int, h: int) -> None:
        horizon_y = h * 0.82
        vanish_x = w * 0.5

        # 지평선 글로우 라인
        painter.setPen(QColor(56, 189, 248, 22))
        painter.drawLine(0, int(horizon_y), w, int(horizon_y))

        # 원근 그리드
        rows = 6
        cols = 14
        for row in range(1, rows + 1):
            t = row / (rows + 1)
            y = horizon_y + (h - horizon_y) * t * 0.95
            alpha = int(8 + 18 * (1.0 - t))
            painter.setPen(QColor(56, 189, 248, alpha))
            painter.drawLine(0, int(y), w, int(y))

        for col in range(-cols // 2, cols // 2 + 1):
            painter.setPen(QColor(96, 165, 250, 10))
            top_x = vanish_x + col * (w * 0.04)
            bottom_x = vanish_x + col * (w * 0.22)
            painter.drawLine(int(top_x), int(horizon_y * 0.92), int(bottom_x), h)
