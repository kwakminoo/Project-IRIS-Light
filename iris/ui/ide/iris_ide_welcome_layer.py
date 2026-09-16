"""IDE Empty Home — Cursor 스타일 웰컴 (폴더 미열림)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from iris.storage.ide_recent_folders import (
    list_recent_folders,
    next_iris_project_dir,
    record_opened_folder,
    truncate_path_middle,
)
from iris.ui.ide.ide_welcome_icons import WelcomeOutlineIcon
from iris.ui.shared.theme_tokens import TOKENS

_WELCOME_MAX_WIDTH = 920
_BTN_MIN_WIDTH = 148
_BTN_MIN_HEIGHT = 88
_SECTION_GAP = 15
_TITLE_FONT_PX = 50
_ACTIVITY_BAR_W = 48

_BTN_BG = "rgba(5, 12, 26, 0.25)"
_BTN_BORDER = TOKENS.border_subtle


class _WelcomeActionButton(QPushButton):
    def __init__(self, icon_kind: str, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("IdeWelcomeActionButton")
        self.setMinimumSize(_BTN_MIN_WIDTH, _BTN_MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 12)
        lay.setSpacing(10)
        lay.addWidget(WelcomeOutlineIcon(icon_kind, self), 0, Qt.AlignmentFlag.AlignHCenter)
        lbl = QLabel(label, self)
        lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lbl.setStyleSheet(
            f"color: {TOKENS.text_primary}; font-size: 13px; background: transparent;"
        )
        lay.addWidget(lbl)

        self.setStyleSheet(
            f"QPushButton#IdeWelcomeActionButton {{"
            f" background: {_BTN_BG};"
            f" border: 1px solid {_BTN_BORDER};"
            f" border-radius: 8px;"
            f"}}"
            f"QPushButton#IdeWelcomeActionButton:hover {{"
            f" background: {TOKENS.panel_hover};"
            f" border-color: {TOKENS.border_color};"
            f"}}"
            f"QPushButton#IdeWelcomeActionButton:pressed {{"
            f" background: rgba(37, 99, 235, 0.28);"
            f" border-color: {TOKENS.neon_cyan};"
            f"}}"
        )


class _RecentRow(QWidget):
    clicked = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path = ""
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(8)
        self._name = QLabel("")
        self._name.setStyleSheet(
            f"color: {TOKENS.text_primary}; font-size: 13px; background: transparent;"
        )
        self._path_lbl = QLabel("")
        self._path_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._path_lbl.setStyleSheet(
            f"color: {TOKENS.text_muted}; font-size: 12px; background: transparent;"
        )
        lay.addWidget(self._name, 0)
        lay.addStretch(1)
        lay.addWidget(self._path_lbl, 0)

    def set_entry(self, name: str, path: str) -> None:
        self._path = path
        self._name.setText(name)
        self._path_lbl.setText(truncate_path_middle(path) if path else "")
        self.setVisible(bool(path))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._path:
            self.clicked.emit(self._path)
            event.accept()
            return
        super().mousePressEvent(event)


class IrisIdeWelcomeLayer(QWidget):
    """폴더 미열림 중앙 웰컴 — Iris Companion과 동일 void_black 배경."""

    folder_opened = pyqtSignal(str)
    folder_created = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("IrisIdeWelcomeLayer")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # ponytail: Companion 우측(IdeCompanionPage)과 동일 — 그라데이션 쓰면 색이 갈라짐
        self.setStyleSheet(
            f"QWidget#IrisIdeWelcomeLayer {{ background-color: {TOKENS.void_black}; }}"
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        activity = QWidget(self)
        activity.setFixedWidth(_ACTIVITY_BAR_W)
        activity.setStyleSheet("background: transparent;")
        root.addWidget(activity, 0)

        panel = QWidget(self)
        panel.setObjectName("IrisIdeWelcomePanel")
        panel.setStyleSheet("background: transparent;")
        root.addWidget(panel, 1)

        panel_lay = QVBoxLayout(panel)
        panel_lay.setContentsMargins(32, 48, 32, 32)
        panel_lay.setSpacing(0)
        panel_lay.addStretch(2)

        content = QWidget(panel)
        content.setMaximumWidth(_WELCOME_MAX_WIDTH)
        content.setStyleSheet("background: transparent;")
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(0)

        self._title = QLabel("IRIS IDE", content)
        self._title.setObjectName("IdeWelcomeTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._title.setStyleSheet(
            f"color: {TOKENS.text_accent};"
            f" font-size: {_TITLE_FONT_PX}px;"
            " font-weight: 400;"
            " letter-spacing: 4px;"
            " background: transparent;"
        )
        content_lay.addWidget(self._title)
        content_lay.addSpacing(_SECTION_GAP)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self.btn_open_folder = _WelcomeActionButton("folder", "Open folder", content)
        self.btn_create_folder = _WelcomeActionButton("folder_plus", "Create folder", content)
        self.btn_connect_ssh = _WelcomeActionButton("terminal", "Connect via SSH", content)
        self.btn_open_folder.clicked.connect(self._pick_open_folder)
        self.btn_create_folder.clicked.connect(self._pick_create_folder)
        # ponytail: SSH는 UI만 — 연결은 이후
        btn_row.addWidget(self.btn_open_folder, 1)
        btn_row.addWidget(self.btn_create_folder, 1)
        btn_row.addWidget(self.btn_connect_ssh, 1)
        content_lay.addLayout(btn_row)
        content_lay.addSpacing(_SECTION_GAP)

        recent_hdr = QHBoxLayout()
        recent_lbl = QLabel("Recent projects")
        recent_lbl.setStyleSheet(
            f"color: {TOKENS.text_secondary}; font-size: 13px; background: transparent;"
        )
        recent_hdr.addWidget(recent_lbl)
        recent_hdr.addStretch(1)
        content_lay.addLayout(recent_hdr)

        self._recent_rows: list[_RecentRow] = []
        recent_box = QVBoxLayout()
        recent_box.setSpacing(4)
        for _ in range(5):
            row = _RecentRow(content)
            row.clicked.connect(self._open_recent)
            recent_box.addWidget(row)
            self._recent_rows.append(row)
        content_lay.addLayout(recent_box)

        panel_lay.addWidget(content, 0, Qt.AlignmentFlag.AlignHCenter)
        panel_lay.addStretch(3)
        self.refresh_recent_folders()

    def _emit_folder(self, path: str) -> None:
        record_opened_folder(Path(path))
        self.refresh_recent_folders()
        self.folder_opened.emit(path)

    def _pick_open_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open folder")
        if path:
            self._emit_folder(path)

    def _pick_create_folder(self) -> None:
        parent = QFileDialog.getExistingDirectory(self, "Create folder — 상위 디렉터리 선택")
        if not parent:
            return
        new_dir = next_iris_project_dir(Path(parent))
        new_dir.mkdir(parents=True, exist_ok=False)
        resolved = str(new_dir.resolve())
        record_opened_folder(new_dir)
        self.refresh_recent_folders()
        self.folder_created.emit(resolved)
        self.folder_opened.emit(resolved)

    def _open_recent(self, path: str) -> None:
        if path and Path(path).expanduser().is_dir():
            self._emit_folder(path)

    def refresh_recent_folders(self) -> None:
        recent = list_recent_folders(5)
        for i, row in enumerate(self._recent_rows):
            if i < len(recent):
                name, path = recent[i]
                row.set_entry(name, path)
            else:
                row.set_entry("", "")
