"""항상 유지되는 좌측 사이드바."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSizePolicy, QSplitter, QStackedWidget, QVBoxLayout, QWidget

from iris.ui.knowledge.obsidian_detail_panel import ObsidianDetailPanel
from iris.ui.window_list_panel import WindowListPanel

_SIDEBAR_MIN_WIDTH = 200
_SIDEBAR_MAX_WIDTH = 300
# Obsidian 상세 패널 — 드래그로 폭 조절
_OBSIDIAN_SIDEBAR_MIN = 180
_OBSIDIAN_SIDEBAR_MAX = 480
_OBSIDIAN_SIDEBAR_DEFAULT = 260


class LeftSidebarPanel(QWidget):
    """
    상단: Running Windows 또는 Obsidian 노트 상세
    하단: CPU·GPU·메모리 + Workspace 액션
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("LeftSidebarPanel")
        self.setMinimumWidth(_SIDEBAR_MIN_WIDTH)
        self.setMaximumWidth(_SIDEBAR_MAX_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(0)

        self.window_list = WindowListPanel(self)
        self.obsidian_detail = ObsidianDetailPanel(self)

        self._top_stack = QStackedWidget(self)
        self._top_stack.setObjectName("LeftSidebarTopStack")
        self._top_stack.addWidget(self.window_list)
        self._top_stack.addWidget(self.obsidian_detail)

        from iris.ui.sidebar_utility_panel import SidebarUtilityPanel

        self.utility = SidebarUtilityPanel(self)

        self._splitter.addWidget(self._top_stack)
        self._splitter.addWidget(self.utility)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([280, 280])

        root.addWidget(self._splitter)
        self._mode = "assistant"

    @property
    def mode(self) -> str:
        return self._mode

    def set_workspace_mode(self, mode: str) -> None:
        """assistant / obsidian(상세+아이콘) / ide(사이드바 숨김)."""
        self._mode = mode
        if mode == "ide":
            self.hide()
            self.setMinimumWidth(0)
            self.setMaximumWidth(0)
            return

        self.show()
        self.utility.actions.setVisible(True)

        if mode == "obsidian":
            self._top_stack.setCurrentWidget(self.obsidian_detail)
            self.utility.metrics.hide()
            self.setMinimumWidth(_OBSIDIAN_SIDEBAR_MIN)
            self.setMaximumWidth(_OBSIDIAN_SIDEBAR_MAX)
            # 상단 상세 stretch, 하단 아이콘만 — 기본화면처럼 아이콘은 아래
            self._splitter.setStretchFactor(0, 1)
            self._splitter.setStretchFactor(1, 0)
            self._splitter.setSizes([480, 120])
            return

        self._top_stack.setCurrentWidget(self.window_list)
        self.utility.metrics.setVisible(True)
        self.setMinimumWidth(_SIDEBAR_MIN_WIDTH)
        self.setMaximumWidth(_SIDEBAR_MAX_WIDTH)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([280, 280])
