"""Animated microphone waveform shown below the chat input."""

from __future__ import annotations

import math
from collections import deque

from PyQt6.QtCore import QPointF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from iris.audio.mic_level import speech_rms_to_display_level

_SAMPLE_CAPACITY = 180
_FRAME_INTERVAL_MS = 33


class MicWaveformBar(QWidget):
    """
    Thin center-line audio waveform.

    The shape is drawn in code, not from a bitmap, so it can keep moving even
    when no microphone signal is coming in. Incoming mic level increases the
    height and brightness of the spikes.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MicWaveformBar")
        self.setMinimumHeight(52)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._samples: deque[float] = deque(maxlen=_SAMPLE_CAPACITY)
        self._level = 0.0
        self._smooth_level = 0.0
        self._threshold_display = speech_rms_to_display_level(0.018)
        self._phase = 0.0
        self._mic_live = False
        # 기동 인트로 — 0이면 숨김, 1이면 전체 폭 (가운데→좌우)
        self._reveal = 1.0

        self._frame_timer = QTimer(self)
        self._frame_timer.setInterval(_FRAME_INTERVAL_MS)
        self._frame_timer.timeout.connect(self._on_frame)
        self._frame_timer.start()

    def set_threshold_rms(self, speech_rms: float) -> None:
        self._threshold_display = speech_rms_to_display_level(speech_rms)
        self.update()

    def set_reveal_progress(self, value: float) -> None:
        """가운데에서 좌우로 선이 뻗어나가는 등장 진행도."""
        self._reveal = max(0.0, min(1.0, float(value)))
        self.update()

    def set_level(self, level: float) -> None:
        incoming = min(1.0, max(0.0, level))
        self._mic_live = True
        self._level = max(incoming, self._level * 0.85)
        self._samples.append(self._level)
        self.update()

    def _on_frame(self) -> None:
        self._phase += 0.08
        if self._phase > math.pi * 200:
            self._phase -= math.pi * 200

        target = self._level if self._mic_live else 0.0
        self._smooth_level += (target - self._smooth_level) * 0.12

        if self._level > 0.001:
            self._level *= 0.92
        else:
            self._level = 0.0

        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        if self._reveal <= 0.001:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width, height = self.width(), self.height()
        margin_x = 18
        inner_width = max(1, width - margin_x * 2)
        mid_y = height / 2.0
        center_x = margin_x + inner_width / 2.0
        visible_half = (inner_width / 2.0) * self._reveal
        painter.setClipRect(
            int(center_x - visible_half),
            0,
            max(1, int(visible_half * 2)),
            height,
        )

        level = max(0.08, min(1.0, self._smooth_level))
        active = self._smooth_level >= self._threshold_display * 0.5
        peak_amp = height * (0.34 + 0.70 * level)

        self._draw_center_glow(painter, margin_x, inner_width, mid_y, active)
        self._draw_center_wave(painter, margin_x, inner_width, mid_y, peak_amp)
        self._draw_center_line(painter, margin_x, inner_width, mid_y, active)

        painter.end()

    def _draw_center_glow(
        self,
        painter: QPainter,
        margin_x: int,
        inner_width: int,
        mid_y: float,
        active: bool,
    ) -> None:
        for line_width, alpha in ((8.0, 24), (4.0, 42), (1.4, 170 if active else 115)):
            pen = QPen(QColor(56, 189, 248, alpha))
            pen.setWidthF(line_width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(
                QPointF(margin_x, mid_y),
                QPointF(margin_x + inner_width, mid_y),
            )

    def _draw_center_wave(
        self,
        painter: QPainter,
        margin_x: int,
        inner_width: int,
        mid_y: float,
        peak_amp: float,
    ) -> None:
        sample_count = max(220, int(inner_width / 2))
        step = inner_width / sample_count
        drift = self._phase * 0.75

        layers = (
            (1.0, 70, 0.9, QColor(34, 211, 238), 0.00),
            (0.72, 120, 1.1, QColor(56, 189, 248), 0.45),
            (0.42, 210, 1.3, QColor(241, 245, 249), 0.92),
        )

        for layer_index, (scale, alpha, pen_width, base_color, offset) in enumerate(layers):
            path = QPainterPath()
            for i in range(sample_count + 1):
                t = i / sample_count
                x = margin_x + i * step
                center_envelope = math.exp(-((t - 0.5) ** 2) / 0.030)
                ripple_envelope = math.exp(-((t - 0.5) ** 2) / 0.080) * 0.22
                envelope = min(1.0, center_envelope + ripple_envelope)
                wave = (
                    math.sin(t * math.pi * 52.0 + drift + offset) * 0.62
                    + math.sin(t * math.pi * 113.0 - drift * 1.45 + offset) * 0.27
                    + math.sin(t * math.pi * 181.0 + drift * 2.1 + layer_index) * 0.11
                )
                motion = 0.70 + 0.30 * math.sin(
                    self._phase * 2.8 + t * math.pi * 8.0 + layer_index
                )
                y = mid_y + wave * peak_amp * envelope * motion * scale

                if i == 0:
                    path.moveTo(QPointF(x, y))
                else:
                    path.lineTo(QPointF(x, y))

            color = QColor(base_color)
            color.setAlpha(alpha)
            pen = QPen(color)
            pen.setWidthF(pen_width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(path)

    def _draw_center_line(
        self,
        painter: QPainter,
        margin_x: int,
        inner_width: int,
        mid_y: float,
        active: bool,
    ) -> None:
        pen = QPen(QColor(236, 253, 255, 230 if active else 165))
        pen.setWidthF(1.1)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(QPointF(margin_x, mid_y), QPointF(margin_x + inner_width, mid_y))
