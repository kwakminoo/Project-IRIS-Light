"""Obsidian 상세 패널 스텁 — Light에서는 Running Windows만 사용."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class ObsidianDetailPanel(QWidget):
    """원본 호환용 빈 패널 (아이콘 전환 화면은 Light에 포함하지 않음)."""

    view_mode_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ObsidianDetailPanel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        hint = QLabel("Wiki 상세는 Light에서 비활성")
        hint.setObjectName("MutedHint")
        lay.addWidget(hint)
        lay.addStretch(1)
