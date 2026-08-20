"""설정창용 마이크 레벨 게이지 + 임계치 세로 바."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from iris.audio.mic_level import display_level_to_speech_rms, speech_rms_to_display_level


class MicLevelGauge(QWidget):
    """가로 음성 게이지 — 실시간 입력 레벨 표시."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(28)
        self.setMinimumWidth(160)
        self._level = 0.0
        self._threshold = speech_rms_to_display_level(0.02)

    def set_level(self, level: float) -> None:
        self._level = min(1.0, max(0.0, float(level)))
        self.update()

    def set_threshold_display(self, value: float) -> None:
        self._threshold = min(1.0, max(0.0, float(value)))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        margin = 4
        bar_h = max(10, h - margin * 2)
        y = (h - bar_h) / 2.0
        # track
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(15, 23, 42, 180))
        painter.drawRoundedRect(margin, int(y), w - margin * 2, bar_h, 4, 4)
        # fill
        fill_w = int((w - margin * 2) * self._level)
        if fill_w > 0:
            over = self._level >= self._threshold
            painter.setBrush(QColor(248, 113, 113, 210) if over else QColor(56, 189, 248, 200))
            painter.drawRoundedRect(margin, int(y), fill_w, bar_h, 4, 4)
        # threshold marker
        tx = margin + int((w - margin * 2) * self._threshold)
        pen = QPen(QColor(241, 245, 249, 220))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawLine(tx, int(y) - 1, tx, int(y + bar_h) + 1)
        painter.end()


class MicThresholdBar(QWidget):
    """세로 임계치 슬라이더 + 옆 가로 게이지."""

    threshold_changed = pyqtSignal(float)  # speech_rms

    def __init__(self, *, speech_rms: float = 0.02, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        col.addWidget(QLabel("덜 민감"))
        self._slider = QSlider(Qt.Orientation.Vertical)
        self._slider.setMinimum(1)
        self._slider.setMaximum(100)
        self._slider.setFixedHeight(96)
        self._slider.setToolTip("위로 갈수록 덜 민감, 아래로 갈수록 더 민감합니다")
        display = speech_rms_to_display_level(speech_rms)
        self._slider.setValue(max(1, min(100, int(round(display * 100)))))
        self._slider.valueChanged.connect(self._on_slider)
        col.addWidget(self._slider, 0, Qt.AlignmentFlag.AlignHCenter)
        self._thresh_label = QLabel("")
        self._thresh_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        col.addWidget(self._thresh_label)
        col.addWidget(QLabel("더 민감"))
        lay.addLayout(col)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(4)
        right.addWidget(QLabel("음성 게이지"))
        self.gauge = MicLevelGauge()
        self.gauge.set_threshold_display(display)
        right.addWidget(self.gauge)
        self._level_label = QLabel("마이크를 선택하면 실시간 입력이 표시됩니다.")
        self._level_label.setWordWrap(True)
        right.addWidget(self._level_label)
        right.addStretch(1)
        lay.addLayout(right, 1)

        self._update_label()

    def speech_rms(self) -> float:
        return display_level_to_speech_rms(self._slider.value() / 100.0)

    def set_speech_rms(self, rms: float) -> None:
        display = speech_rms_to_display_level(rms)
        self._slider.blockSignals(True)
        self._slider.setValue(max(1, min(100, int(round(display * 100)))))
        self._slider.blockSignals(False)
        self.gauge.set_threshold_display(display)
        self._update_label()

    def set_level(self, level: float) -> None:
        self.gauge.set_level(level)
        over = level >= (self._slider.value() / 100.0)
        self._level_label.setText(
            f"입력 레벨 {level:.0%} — {'인식 구간' if over else '대기 (민감도 미만)'}"
        )

    def set_inactive(self) -> None:
        self.gauge.set_level(0.0)
        self._level_label.setText("마이크가 꺼져 있습니다")

    def set_status(self, text: str) -> None:
        self._level_label.setText(text)

    def _on_slider(self, value: int) -> None:
        display = value / 100.0
        self.gauge.set_threshold_display(display)
        self._update_label()
        self.threshold_changed.emit(display_level_to_speech_rms(display))

    def _update_label(self) -> None:
        rms = self.speech_rms()
        self._thresh_label.setText(f"{rms:.3f}")
