"""패널 섹션 제목 + 하단 얇은 구분선."""

from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from iris.ui.theme_tokens import TOKENS

# Running Windows 기준 — 제목↔선, 선↔본문 여백 통일
SECTION_TITLE_LINE_GAP = TOKENS.spacing_sm
SECTION_CONTENT_GAP = TOKENS.spacing_xs
SECTION_PANEL_MARGINS = (
    TOKENS.spacing_xs,
    TOKENS.spacing_sm,
    TOKENS.spacing_xs,
    TOKENS.spacing_sm,
)


def make_section_header(
    text: str,
    *,
    title_object_name: str = "PanelTitle",
) -> QWidget:
    """제목 아래 1px 구분선만 표시."""
    wrap = QWidget()
    wrap.setObjectName("SectionHeader")
    lay = QVBoxLayout(wrap)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(SECTION_TITLE_LINE_GAP)

    title = QLabel(text)
    title.setObjectName(title_object_name)
    title.setStyleSheet("background: transparent; border: none;")

    line = QFrame()
    line.setObjectName("SectionUnderline")
    line.setFixedHeight(1)
    line.setStyleSheet(
        f"background: {TOKENS.panel_border}; border: none; max-height: 1px;"
    )

    lay.addWidget(title)
    lay.addWidget(line)
    return wrap


def apply_section_panel_layout(layout) -> None:
    """섹션 패널 루트 레이아웃 여백·간격 통일."""
    l, t, r, b = SECTION_PANEL_MARGINS
    layout.setContentsMargins(l, t, r, b)
    layout.setSpacing(SECTION_CONTENT_GAP)
