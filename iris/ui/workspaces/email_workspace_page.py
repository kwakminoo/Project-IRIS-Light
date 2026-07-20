"""이메일 워크스페이스 — 계정 선택·본문·작성."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from iris.infrastructure.email_client import MailMessage
from iris.storage.email_accounts import EmailAccount


class _ComposeDialog(QDialog):
    def __init__(
        self,
        account: EmailAccount,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("메일 작성")
        self.setMinimumWidth(520)
        self._account = account

        lay = QVBoxLayout(self)
        form = QFormLayout()
        self._from_label = QLabel(account.address)
        self._to = QLineEdit()
        self._to.setPlaceholderText("받는 사람")
        self._subject = QLineEdit()
        self._subject.setPlaceholderText("제목")
        self._body = QPlainTextEdit()
        self._body.setPlaceholderText("본문")
        self._body.setMinimumHeight(180)
        form.addRow("보내는 사람", self._from_label)
        form.addRow("받는 사람", self._to)
        form.addRow("제목", self._subject)
        form.addRow("본문", self._body)
        lay.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Send | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Send).setText("보내기")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def payload(self) -> tuple[str, str, str]:
        return (
            self._to.text().strip(),
            self._subject.text().strip(),
            self._body.toPlainText(),
        )


class EmailWorkspacePage(QWidget):
    """중앙 이메일 화면 — 상단 계정 선택 + 본문 미리보기."""

    compose_requested = pyqtSignal(str, str, str)  # to, subject, body
    account_changed = pyqtSignal(str)  # account id
    refresh_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("EmailWorkspacePage")
        self._accounts: list[EmailAccount] = []
        self._current_account: EmailAccount | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        self._account_combo = QComboBox()
        self._account_combo.setObjectName("EmailAccountCombo")
        self._account_combo.setMinimumWidth(240)
        self._account_combo.currentIndexChanged.connect(self._on_account_combo)
        self._refresh_btn = QPushButton("새로고침")
        self._refresh_btn.clicked.connect(self.refresh_requested.emit)
        self._compose_btn = QPushButton("작성")
        self._compose_btn.clicked.connect(self._open_compose)
        self._status = QLabel("프로필에서 이메일 계정을 추가하세요.")
        self._status.setObjectName("EmailStatusLabel")
        top.addWidget(self._account_combo, 1)
        top.addWidget(self._refresh_btn)
        top.addWidget(self._compose_btn)
        lay.addLayout(top)
        lay.addWidget(self._status)

        self._meta = QLabel("")
        self._meta.setObjectName("SectionTitle")
        lay.addWidget(self._meta)

        self._body = QTextBrowser()
        self._body.setObjectName("EmailPreviewBody")
        self._body.setOpenExternalLinks(True)
        self._body.setReadOnly(True)
        lay.addWidget(self._body, 1)

    def set_accounts(self, accounts: list[EmailAccount], *, selected_id: str = "") -> None:
        self._accounts = list(accounts)
        self._account_combo.blockSignals(True)
        self._account_combo.clear()
        for acc in self._accounts:
            self._account_combo.addItem(acc.display_name, acc.id)
        self._account_combo.blockSignals(False)
        if not self._accounts:
            self._current_account = None
            self._status.setText("프로필 → 이메일 계정에서 Gmail·Naver 주소와 앱 비밀번호를 추가하세요.")
            self._meta.setText("이메일")
            self._body.setPlainText("")
            return
        idx = 0
        if selected_id:
            for i, acc in enumerate(self._accounts):
                if acc.id == selected_id:
                    idx = i
                    break
        self._account_combo.setCurrentIndex(idx)
        self._current_account = self._accounts[idx]
        self._status.setText(f"{self._current_account.address} — 받은편함")

    def current_account(self) -> EmailAccount | None:
        return self._current_account

    def current_account_id(self) -> str:
        return self._current_account.id if self._current_account else ""

    def set_loading(self, loading: bool) -> None:
        self._refresh_btn.setEnabled(not loading)
        self._compose_btn.setEnabled(not loading and self._current_account is not None)
        if loading:
            self._status.setText("메일 불러오는 중…")

    def show_message(self, msg: MailMessage) -> None:
        self._meta.setText(msg.subject)
        meta = f"보낸 사람: {msg.sender}\n받는 사람: {msg.to}\n날짜: {msg.date}"
        self._body.setPlainText(f"{meta}\n\n{'—' * 40}\n\n{msg.body}")

    def show_error(self, text: str) -> None:
        self._status.setText(text)
        self._body.setPlainText("")

    def show_empty_inbox_hint(self) -> None:
        self._meta.setText("받은편함")
        self._body.setPlainText("받은 메일이 없습니다.")

    def _on_account_combo(self, index: int) -> None:
        if index < 0 or index >= len(self._accounts):
            return
        self._current_account = self._accounts[index]
        self._status.setText(f"{self._current_account.address} — 받은편함")
        self.account_changed.emit(self._current_account.id)

    def _open_compose(self) -> None:
        if not self._current_account:
            return
        dlg = _ComposeDialog(self._current_account, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        to, subject, body = dlg.payload()
        if not to:
            self._status.setText("받는 사람을 입력하세요.")
            return
        self.compose_requested.emit(to, subject, body)
