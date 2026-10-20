"""백그라운드 이메일 워커."""

from __future__ import annotations

import socket
import threading

from PyQt6.QtCore import QThread, pyqtSignal

from iris.infrastructure.email_client import (
    MAIL_PAGE_SIZE,
    MailMessage,
    MailSummary,
    fetch_folder,
    fetch_gmail_category,
    fetch_message,
    run_inbox_idle_session,
    send_mail,
    verify_login,
)
from iris.storage.email_accounts import EmailAccount, account_password


class EmailInboxWorker(QThread):
    finished_ok = pyqtSignal(object)  # list[MailSummary]
    failed = pyqtSignal(str)

    def __init__(
        self,
        account: EmailAccount,
        folder: str = "inbox",
        category: str = "",
        *,
        limit: int = MAIL_PAGE_SIZE,
        offset: int = 0,
        append: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._account = account
        self._folder = folder
        self._category = category
        self._limit = max(1, limit)
        self._offset = max(0, offset)
        self.append = append

    def run(self) -> None:
        try:
            addr = self._account.address
            pw = account_password(self._account)
            if self._category:
                items = fetch_gmail_category(
                    addr,
                    pw,
                    self._category,
                    limit=self._limit,
                    offset=self._offset,
                )
            else:
                items = fetch_folder(
                    addr,
                    pw,
                    self._folder,
                    limit=self._limit,
                    offset=self._offset,
                )
            self.finished_ok.emit(items)
        except Exception as e:
            self.failed.emit(str(e))


class EmailMessageWorker(QThread):
    finished_ok = pyqtSignal(object)  # MailMessage
    failed = pyqtSignal(str)

    def __init__(
        self,
        account: EmailAccount,
        uid: str,
        folder: str = "inbox",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._account = account
        self._uid = uid
        self._folder = folder

    def run(self) -> None:
        try:
            msg = fetch_message(
                self._account.address,
                account_password(self._account),
                self._uid,
                folder_key=self._folder,
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


class EmailIdleWorker(QThread):
    """INBOX IMAP IDLE — EXISTS 증가 시 new_mails(list[MailSummary])만 emit."""

    new_mails = pyqtSignal(object)  # list[MailSummary], 최신순
    failed = pyqtSignal(str)

    def __init__(self, account: EmailAccount, parent=None) -> None:
        super().__init__(parent)
        self._account = account
        self._stop = threading.Event()
        self._sock: socket.socket | None = None
        self._sock_lock = threading.Lock()

    @property
    def account_id(self) -> str:
        return self._account.id

    def request_stop(self) -> None:
        self._stop.set()
        with self._sock_lock:
            sock = self._sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def _set_sock(self, sock: socket.socket | None) -> None:
        with self._sock_lock:
            self._sock = sock

    def run(self) -> None:
        backoff = 5.0
        while not self._stop.is_set():
            try:

                def _on_new(items: list[MailSummary]) -> None:
                    if items and not self._stop.is_set():
                        self.new_mails.emit(items)

                run_inbox_idle_session(
                    self._account.address,
                    account_password(self._account),
                    self._stop,
                    on_new_mails=_on_new,
                    on_sock=self._set_sock,
                )
                if self._stop.is_set():
                    return
                # 연결이 끊긴 경우 — 잠깐 쉬고 재연결
                backoff = 5.0
                if self._stop.wait(2.0):
                    return
            except Exception as e:
                if self._stop.is_set():
                    return
                self.failed.emit(str(e)[:240])
                if self._stop.wait(backoff):
                    return
                backoff = min(backoff * 2, 120.0)
