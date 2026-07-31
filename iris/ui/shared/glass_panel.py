"""Glass HUD HUD 패널 래퍼."""

from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QVBoxLayout, QWidget


def wrap_glass_panel(content: QWidget, *, object_name: str = "GlassPanel") -> QFrame:
    """내부 위젯을 glass 스타일 QFrame으로 감싼다."""
    frame = QFrame()
    frame.setObjectName(object_name)
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    lay.addWidget(content)
    return frame
