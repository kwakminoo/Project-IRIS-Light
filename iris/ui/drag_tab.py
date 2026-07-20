"""Draggable top chrome with stable window controls."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from iris.ui.top_status_header import STATUS_BLOCK_HEIGHT


def _win_ctrl_button(text: str, tooltip: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("WinCtrl")
    btn.setToolTip(tooltip)
    btn.setFixedSize(30, 26)
    btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return btn


class DragTab(QWidget):
    """Frameless title bar with drag handling and window controls."""

    profile_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    minimize_clicked = pyqtSignal()
    maximize_clicked = pyqtSignal()

    def __init__(self, parent_window: QWidget) -> None:
        super().__init__()
        self.setObjectName("DragTab")
        self._win = parent_window
        # 상태 2행 + 상하 패딩에 맞춘 고정 높이
        chrome_h = STATUS_BLOCK_HEIGHT + 12
        self.setFixedHeight(chrome_h)
        self.setMinimumHeight(chrome_h)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(10)

        self._title = QLabel("IRIS")
        self._title.setObjectName("DragTitle")
        self._title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._title.setFixedHeight(STATUS_BLOCK_HEIGHT)
        self._title.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        lay.addWidget(self._title, 0, Qt.AlignmentFlag.AlignVCenter)

        self._status_column = QWidget()
        self._status_column.setObjectName("DragTabStatusColumn")
        self._status_column.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._status_column.setFixedHeight(STATUS_BLOCK_HEIGHT)
        self._status_column_lay = QVBoxLayout(self._status_column)
        self._status_column_lay.setContentsMargins(0, 0, 0, 0)
        self._status_column_lay.setSpacing(0)
        self._status_column.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        lay.addWidget(self._status_column, 0, Qt.AlignmentFlag.AlignVCenter)

        lay.addStretch(1)

        ctrl_row = QHBoxLayout()
        ctrl_row.setContentsMargins(0, 0, 0, 0)
        ctrl_row.setSpacing(4)
        ctrl_row.setSizeConstraint(QHBoxLayout.SizeConstraint.SetFixedSize)

        self._btn_profile = _win_ctrl_button("👤", "사용자 프로필")
        self._btn_settings = _win_ctrl_button("⚙", "설정")
        self._btn_min = _win_ctrl_button("−", "창 내리기")
        self._btn_max = _win_ctrl_button("□", "전체 화면")
        self._btn_close = _win_ctrl_button("×", "닫기")

        for btn in (self._btn_profile, self._btn_settings, self._btn_min, self._btn_max, self._btn_close):
            ctrl_row.addWidget(btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        lay.addLayout(ctrl_row)

        self._btn_min.clicked.connect(self.minimize_clicked.emit)
        self._btn_max.clicked.connect(self.maximize_clicked.emit)
        self._btn_close.clicked.connect(parent_window.close)
        self._btn_profile.clicked.connect(self.profile_clicked.emit)
        self._btn_settings.clicked.connect(self.settings_clicked.emit)
        self._drag_pos = None

    def place_status_rows(self, primary: QWidget, backend: QWidget) -> None:
        """STATE/MODEL/TTS + 백엔드 — 단일 3열 그리드 또는 2행 블록."""
        while self._status_column_lay.count():
            item = self._status_column_lay.takeAt(0)
            child = item.widget()
            if child is not None:
                child.setParent(None)
        primary.setParent(self._status_column)
        self._status_column_lay.addWidget(primary)
        primary.show()
        if backend.maximumHeight() > 0 and backend.isVisible():
            backend.setParent(self._status_column)
            self._status_column_lay.addWidget(backend)
            backend.show()
        self._status_column.show()

    def place_primary_status(self, widget: QWidget) -> None:
        """레거시 호환 — primary만 넣을 때 backend 슬롯은 비움."""
        empty = QWidget()
        empty.setFixedHeight(0)
        empty.hide()
        self.place_status_rows(widget, empty)

    def set_maximized(self, maximized: bool) -> None:
        """Update maximize/restore button state."""
        if maximized:
            self._btn_max.setText("❐")
            self._btn_max.setToolTip("창 복원")
        else:
            self._btn_max.setText("□")
            self._btn_max.setToolTip("전체 화면")

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._drag_pos is not None and e.buttons() & Qt.MouseButton.LeftButton:
            if not self._win.isMaximized():
                self._win.move(e.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.maximize_clicked.emit()
        super().mouseDoubleClickEvent(e)
