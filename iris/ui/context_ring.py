"""채팅 컨텍스트 사용량 추정·원형 게이지."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from iris.ui.theme_tokens import TOKENS

_RING_PX = 18
_RING_WIDTH = 2.2


def estimate_messages_tokens(messages: list[dict[str, Any]] | list[dict[str, str]]) -> int:
    """대략적 토큰 수. 한/영 혼용 기준 chars/3 (ponytail: 정확 카운터 없음)."""
    total_chars = 0
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        content = m.get("content")
        if isinstance(content, str):
            total_chars += len(content)
        # role overhead
        total_chars += 8
    return max(0, total_chars // 3)


def format_context_pair(used: int, limit: int) -> str:
    def _n(n: int) -> str:
        n = max(0, int(n))
        if n >= 1_000_000:
            v = n / 1_000_000
            return f"{v:.1f}M".replace(".0M", "M")
        if n >= 10_000:
            return f"{n // 1000}k"
        if n >= 1000:
            v = n / 1000
            return f"{v:.1f}k".replace(".0k", "k")
        return str(n)

    return f"{_n(used)} / {_n(limit)}"


class ContextRingWidget(QWidget):
    """Cursor 스타일 원형 컨텍스트 게이지."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ContextRing")
        self._ratio = 0.0
        self.setFixedSize(_RING_PX, _RING_PX)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setToolTip("Context 0%")

    def set_usage(self, used: int, limit: int) -> None:
        lim = max(1, int(limit))
        u = max(0, int(used))
        self._ratio = max(0.0, min(1.0, u / lim))
        pct = self._ratio * 100.0
        self.setToolTip(f"Context {format_context_pair(u, lim)} ({pct:.0f}%)")
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        side = min(self.width(), self.height())
        if side <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        margin = _RING_WIDTH / 2 + 0.5
        rect = QRectF(margin, margin, side - 2 * margin, side - 2 * margin)

        track = QColor(TOKENS.text_muted)
        track.setAlpha(90)
        painter.setPen(QPen(track, _RING_WIDTH, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect)

        if self._ratio <= 0.001:
            painter.end()
            return

        # 사용량에 따라 색: 여유→시안, 높음→경고
        if self._ratio >= 0.9:
            fill = QColor(TOKENS.error)
        elif self._ratio >= 0.7:
            fill = QColor(TOKENS.warning)
        else:
            fill = QColor(TOKENS.neon_cyan)
        painter.setPen(QPen(fill, _RING_WIDTH, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        # Qt: 3시 기준, 반시계. Cursor처럼 12시부터 시계방향 ≈ start 90°, span -360*ratio
        span = -360.0 * self._ratio
        painter.drawArc(rect, int(90 * 16), int(span * 16))
        painter.end()


if __name__ == "__main__":
    assert estimate_messages_tokens([{"role": "user", "content": "abcd" * 30}]) > 0
    assert format_context_pair(1200, 262144) == "1.2k / 262k"
    print("context_ring self-check ok")
