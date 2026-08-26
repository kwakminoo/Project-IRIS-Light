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


def ecg_pulse(u: float) -> float:
    """Single ECG beat in 0..1 — symmetric QRS spike (up AND down)."""
    if u < 0.06:
        return 0.12 * (u / 0.06)          # 위로 올라가는 P파
    if u < 0.10:
        return 0.12 - 1.05 * ((u - 0.06) / 0.04)  # Q: 아래로 내려감
    if u < 0.14:
        return -0.93 + 1.88 * ((u - 0.10) / 0.04)  # R: 위로 솟구침 (양수 피크)
    if u < 0.20:
        return 0.95 - 1.45 * ((u - 0.14) / 0.06)   # S: 다시 아래로
    if u < 0.28:
        return -0.50 + 0.55 * math.sin((u - 0.20) / 0.08 * math.pi)  # T파
    return 0.0


def ecg_wave_offset(t: float, phase: float, layer: int, voice: float) -> float:
    """Center-heavy ECG trace. voice=0 → faint idle flutter, voice=1 → full spike.
    Phase is used only for breathing amplitude — NOT for horizontal drift.
    """
    v = min(1.0, max(0.0, voice))
    center = math.exp(-((t - 0.5) ** 2) / 0.012)
    edge = 0.05 + 0.95 * center
    # 위치 고정: beats 수만큼 균등 분포, phase는 위상 이동에 사용 안 함
    beats = 5.5 + layer * 0.35
    u = (t * beats + layer * 0.17) % 1.0
    pulse = ecg_pulse(u)
    # 잔 노이즈는 t 기반으로만 — phase 제거로 좌우 이동 방지
    hiss = 0.04 * math.sin(t * 48.0 + layer * 2.1)
    idle = pulse * (0.28 + 0.20 * abs(math.sin(phase * 4.0 + layer)))
    voiced = pulse * (0.55 + 0.85 * v)
    mix = idle * (1.0 - v) + voiced * v + hiss * (0.35 + 0.65 * v)
    return mix * edge


def wave_peak_amp(height: float, listening: bool, level: float) -> float:
    if not listening:
        return height * 0.34
    base = 0.28 + 0.22 * min(1.0, level)
    spike = 0.42 + 0.78 * min(1.0, level)
    return height * (base + (spike - base) * min(1.0, level * 1.15))


class MicWaveformBar(QWidget):
    """
    Thin center-line audio waveform.

    Mic off: slow flowing wave. Mic on: ECG-like multi-line spikes in the
    center; voice level makes them taller and sharper.
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
        self._listening = False
        self._reveal = 1.0

        self._frame_timer = QTimer(self)
        self._frame_timer.setInterval(_FRAME_INTERVAL_MS)
        self._frame_timer.timeout.connect(self._on_frame)
        self._frame_timer.start()

    def set_threshold_rms(self, speech_rms: float) -> None:
        self._threshold_display = speech_rms_to_display_level(speech_rms)
        self.update()

    def set_reveal_progress(self, value: float) -> None:
        self._reveal = max(0.0, min(1.0, float(value)))
        self.update()

    def set_listening(self, on: bool) -> None:
        listening = bool(on)
        if listening == self._listening:
            return
        self._listening = listening
        if not listening:
            self._level = 0.0
            self._samples.clear()
        self.update()

    def set_level(self, level: float) -> None:
        if not self._listening:
            return
        incoming = min(1.0, max(0.0, level))
        self._level = max(incoming, self._level * 0.85)

    def _sample_at(self, t: float) -> float:
        if not self._samples:
            return self._smooth_level
        n = len(self._samples)
        idx = int(t * (n - 1)) if n > 1 else n - 1
        return self._samples[idx]

    def _on_frame(self) -> None:
        self._phase += 0.18 if self._listening else 0.08
        if self._phase > math.pi * 200:
            self._phase -= math.pi * 200

        target = self._level if self._listening else 0.0
        rate = 0.24 if self._listening else 0.12
        self._smooth_level += (target - self._smooth_level) * rate

        if self._listening:
            self._samples.append(self._level)

        if self._level > 0.001:
            self._level *= 0.88
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

        level = max(0.0, min(1.0, self._smooth_level))
        active = self._listening and level >= self._threshold_display * 0.5
        self._draw_center_glow(painter, margin_x, inner_width, mid_y, active or self._listening)
        peak_amp = wave_peak_amp(height, self._listening, level)
        self._draw_center_wave(painter, margin_x, inner_width, mid_y, peak_amp, level)
        self._draw_center_line(painter, margin_x, inner_width, mid_y, active or self._listening)

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
        level: float,
    ) -> None:
        sample_count = max(220, int(inner_width / 2))
        step = inner_width / sample_count

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

                if self._listening:
                    local = max(level, self._sample_at(t) * 0.85)
                    wave = ecg_wave_offset(t, self._phase, layer_index, local)
                else:
                    # idle: 위치 고정 정재파 (drift 제거, offset/layer만 위상 차이)
                    center_envelope = math.exp(-((t - 0.5) ** 2) / 0.030)
                    ripple_envelope = math.exp(-((t - 0.5) ** 2) / 0.080) * 0.22
                    envelope = min(1.0, center_envelope + ripple_envelope)
                    wave = (
                        math.sin(t * math.pi * 52.0 + offset) * 0.62
                        + math.sin(t * math.pi * 113.0 + offset * 0.7) * 0.27
                        + math.sin(t * math.pi * 181.0 + layer_index * 0.9) * 0.11
                    )
                    # 진폭만 phase로 호흡시킴 — 위치는 고정
                    motion = 0.70 + 0.30 * math.sin(self._phase * 2.8 + layer_index)
                    wave = wave * envelope * motion

                y = mid_y + wave * peak_amp * scale

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
