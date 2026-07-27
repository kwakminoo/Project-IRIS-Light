"""이메일 좌측 — Gmail식 폴더 내비 (편지쓰기 + 계정 + 폴더)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from iris.storage.email_accounts import EmailAccount

# ponytail: IMAP은 INBOX만 실동작. 나머지 폴더는 겉모습(선택 시 '준비 중' 힌트).
INBOX_LABEL = "받은편지함"
# 표시 라벨 → email_client 폴더 키(SPECIAL-USE 매핑).
FOLDER_KEYS = {
    INBOX_LABEL: "inbox",
    "별표편지함": "starred",
    "보낸편지함": "sent",
    "임시보관함": "drafts",
    "스팸함": "spam",
    "휴지통": "trash",
}
_FOLDERS = tuple(FOLDER_KEYS)


class EmailFolderPanel(QWidget):
    """받은편지함/폴더 내비 + 계정 선택 + 편지쓰기."""

    compose_requested = pyqtSignal()
    account_changed = pyqtSignal(str)  # account id
    folder_selected = pyqtSignal(str)  # folder label

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("EmailFolderPanel")
        self._accounts: list[EmailAccount] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        self._account_combo = QComboBox()
        self._account_combo.setObjectName("EmailAccountCombo")
        self._account_combo.currentIndexChanged.connect(self._on_account_combo)
        lay.addWidget(self._account_combo)

        self._compose_btn = QPushButton("✈  편지쓰기")
        self._compose_btn.setObjectName("EmailComposeButton")
        self._compose_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._compose_btn.setEnabled(False)
        self._compose_btn.setStyleSheet(
            """
            QPushButton#EmailComposeButton {
                background: transparent;
                color: #93c5fd;
                border: none;
                border-radius: 0;
                padding: 8px 10px;
                font-size: 14px;
                font-weight: 600;
                text-align: left;
            }
            QPushButton#EmailComposeButton:hover:enabled {
                color: #e0f2fe;
                background: rgba(56, 189, 248, 0.10);
            }
            QPushButton#EmailComposeButton:disabled { color: #475569; }
            """
        )
        self._compose_btn.clicked.connect(self.compose_requested.emit)
        lay.addWidget(self._compose_btn)

        self._folders = QListWidget(self)
        self._folders.setObjectName("EmailFolderList")
        # 사이버틱: 선택 시 위·아래 네온 라인 + 옅은 푸른 영역 (둥근 모서리 없음)
        self._folders.setStyleSheet(
            """
            QListWidget#EmailFolderList { background: transparent; border: none; outline: none; }
            QListWidget#EmailFolderList::item {
                padding: 8px 12px;
                border-radius: 0;
                color: #cbd5e1;
                border-top: 1px solid transparent;
                border-bottom: 1px solid transparent;
                outline: none;
            }
            QListWidget#EmailFolderList::item:selected {
                background: rgba(56, 189, 248, 0.12);
                color: #e0f2fe;
                border-top: 1px solid #38bdf8;
                border-bottom: 1px solid #38bdf8;
            }
            QListWidget#EmailFolderList::item:hover {
                background: rgba(148, 163, 184, 0.10);
            }
            """
        )
        for label in _FOLDERS:
            self._folders.addItem(QListWidgetItem(label))
        self._folders.setCurrentRow(0)
        self._folders.currentItemChanged.connect(self._on_folder_changed)
        lay.addWidget(self._folders, 1)

        self._status = QLabel("프로필에서 이메일 계정을 추가하세요.")
        self._status.setObjectName("PanelEmptyHint")
        self._status.setWordWrap(True)
        lay.addWidget(self._status)

    def set_status(self, text: str) -> None:
        self._status.setText(text)

    def set_accounts(self, accounts: list[EmailAccount], *, selected_id: str = "") -> None:
        self._accounts = list(accounts)
        self._account_combo.blockSignals(True)
        self._account_combo.clear()
        for acc in self._accounts:
            self._account_combo.addItem(acc.display_name, acc.id)
        self._account_combo.blockSignals(False)
        has = bool(self._accounts)
        self._compose_btn.setEnabled(has)
        if not has:
            self.set_status("프로필 → 이메일 계정에서 Gmail·Naver 주소와 앱 비밀번호를 추가하세요.")
            return
        idx = 0
        if selected_id:
            for i, acc in enumerate(self._accounts):
                if acc.id == selected_id:
                    idx = i
                    break
        self._account_combo.setCurrentIndex(idx)
        self.set_status(f"{self._accounts[idx].address}")

    def current_account_id(self) -> str:
        data = self._account_combo.currentData()
        return str(data) if data else ""

    def current_folder(self) -> str:
        item = self._folders.currentItem()
        return item.text() if item is not None else INBOX_LABEL

    def _on_account_combo(self, index: int) -> None:
        if 0 <= index < len(self._accounts):
            acc = self._accounts[index]
            self.set_status(acc.address)
            self.account_changed.emit(acc.id)

    def _on_folder_changed(self, current: QListWidgetItem | None, _prev) -> None:
        if current is not None:
            self.folder_selected.emit(current.text())
