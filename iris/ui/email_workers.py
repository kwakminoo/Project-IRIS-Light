"""백그라운드 이메일 워커."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from iris.infrastructure.email_client import (
    MailMessage,
    MailSummary,
    fetch_inbox,
    fetch_message,
    send_mail,
    verify_login,
)
from iris.storage.email_accounts import EmailAccount, account_password


class EmailInboxWorker(QThread):
    finished_ok = pyqtSignal(object)  # list[MailSummary]
    failed = pyqtSignal(str)

    def __init__(self, account: EmailAccount, parent=None) -> None:
        super().__init__(parent)
        self._account = account

    def run(self) -> None:
        try:
            items = fetch_inbox(
                self._account.address,
                account_password(self._account),
            )
            self.finished_ok.emit(items)
        except Exception as e:
            self.failed.emit(str(e))


class EmailMessageWorker(QThread):
    finished_ok = pyqtSignal(object)  # MailMessage
    failed = pyqtSignal(str)

    def __init__(self, account: EmailAccount, uid: str, parent=None) -> None:
        super().__init__(parent)
        self._account = account
        self._uid = uid

    def run(self) -> None:
        try:
            msg = fetch_message(
                self._account.address,
                account_password(self._account),
                self._uid,
            )
            self.finished_ok.emit(msg)
        except Exception as e:
            self.failed.emit(str(e))


class EmailSendWorker(QThread):
    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(
        self,
        account: EmailAccount,
        to: str,
        subject: str,
        body: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._account = account
        self._to = to
        self._subject = subject
        self._body = body

    def run(self) -> None:
        try:
            send_mail(
                self._account.address,
                account_password(self._account),
                self._to,
                self._subject,
                self._body,
            )
            self.finished_ok.emit()
        except Exception as e:
            self.failed.emit(str(e))


class EmailVerifyWorker(QThread):
    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, address: str, password: str, parent=None) -> None:
        super().__init__(parent)
        self._address = address
        self._password = password

    def run(self) -> None:
        try:
            verify_login(self._address, self._password)
            self.finished_ok.emit()
        except Exception as e:
            self.failed.emit(str(e))
