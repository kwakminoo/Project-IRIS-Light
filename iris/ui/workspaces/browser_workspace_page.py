"""Browser workspace — left BrowserPanel + right Iris chat (calendar/email split)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from iris.ui.workspaces.workspace_iris_chat import mount_chat_host, shift_chat_column


class BrowserWorkspacePage(QWidget):
    """중앙 브라우저 + 우측 아이리스 채팅 (캘린더와 같은 스플리터)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("BrowserWorkspacePage")
        self._panel: QWidget | None = None
        self._chat_list_extra = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(6)
        self._splitter = splitter

        self._browser_host = QWidget()
        self._browser_host.setObjectName("BrowserWorkspaceHost")
        self._browser_lay = QVBoxLayout(self._browser_host)
        self._browser_lay.setContentsMargins(0, 0, 0, 0)
        self._browser_lay.setSpacing(0)
        splitter.addWidget(self._browser_host)

        self._chat_host = QWidget()
        self._chat_host.setObjectName("BrowserChatHost")
        self._chat_host.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._chat_host.setStyleSheet("QWidget#BrowserChatHost { background: transparent; }")
        self._chat_host.setMinimumWidth(300)
        self._chat_lay = QVBoxLayout(self._chat_host)
        self._chat_lay.setContentsMargins(0, 0, 0, 0)
        self._chat_lay.setSpacing(0)
        splitter.addWidget(self._chat_host)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([820, 420])
        outer.addWidget(splitter)

    def place_browser_panel(self, panel: QWidget) -> None:
        """addWidget reparents — panel may leave IrisIdeWindow stack."""
        if panel is None:
            return
        if self._browser_lay.indexOf(panel) < 0:
            self._browser_lay.addWidget(panel)
        panel.show()
        self._panel = panel

    def browser_panel(self) -> QWidget | None:
        return self._panel

    def place_chat_host(self, host: QWidget) -> None:
        mount_chat_host(self, host)

    def shift_chat_column(self, delta: int) -> None:
        shift_chat_column(self, delta)
