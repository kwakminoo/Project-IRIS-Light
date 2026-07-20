"""이메일 좌측 — 받은편함 목록."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from iris.infrastructure.email_client import MailSummary


class EmailDetailPanel(QWidget):
    """받은편함 목록 — 선택 시 본문 미리보기로 전달."""

    mail_selected = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("EmailDetailPanel")
        self._items: list[MailSummary] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        title = QLabel("받은편함")
        title.setObjectName("SectionTitle")
        lay.addWidget(title)

        self._status = QLabel("계정을 선택하세요.")
        self._status.setWordWrap(True)
        lay.addWidget(self._status)

        self._list = QListWidget(self)
        self._list.setObjectName("EmailMailList")
        self._list.itemClicked.connect(self._on_item_clicked)
        lay.addWidget(self._list, 1)

    def set_status(self, text: str) -> None:
        self._status.setText(text)

    def set_mails(self, items: list[MailSummary]) -> None:
        self._items = list(items)
        self._list.clear()
        for mail in self._items:
            row = QListWidgetItem(f"{mail.subject}\n{mail.sender} · {mail.date}")
            row.setData(256, mail.uid)
            self._list.addItem(row)
        if self._items:
            self._list.setCurrentRow(0)
            self.mail_selected.emit(self._items[0].uid)
            self.set_status(f"{len(self._items)}통")
        else:
            self.set_status("받은 메일이 없습니다.")

    def clear_mails(self) -> None:
        self._items = []
        self._list.clear()
        self.set_status("불러오는 중…")

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        uid = item.data(256)
        if uid:
            self.mail_selected.emit(str(uid))
