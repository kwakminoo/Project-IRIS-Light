"""기동 자가진단 — Iris Wiki · 연동 이메일 · 에뮬레이터 실행 가능 여부를 순차 확인.

동시 실행 시 (IMAP/adb/파일 IO 경합으로) 불안정할 수 있어 한 스레드에서
순서대로 돈다. UI 스레드를 막지 않도록 QThread로 분리한다.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from iris.infrastructure.email_client import fetch_inbox
from iris.knowledge.iris_wiki import IrisWiki
from iris.storage.email_accounts import EmailAccount, account_password
from iris.system.android_emulator import is_emulator_available


class BootChecksWorker(QThread):
    """모델·서버 확인 이후 실행되는 순차 부팅 점검."""

    progress = pyqtSignal(str)
    inbox_ready = pyqtSignal(object)  # list[MailSummary] — 미리 불러온 받은편지함
    finished_ok = pyqtSignal()

    def __init__(
        self,
        wiki: IrisWiki,
        account: EmailAccount | None,
        *,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._wiki = wiki
        self._account = account

    def run(self) -> None:
        self._check_wiki()
        self._check_email()
        self._check_emulator()
        self.finished_ok.emit()

    def _check_wiki(self) -> None:
        try:
            count = len(self._wiki.list_notes())
            self.progress.emit(f"Iris Wiki: 노트 {count}개 로드 완료")
        except Exception as e:  # noqa: BLE001 - 점검은 실패해도 계속 진행
            self.progress.emit(f"Iris Wiki 확인 실패: {str(e)[:120]}")

    def _check_email(self) -> None:
        if self._account is None:
            self.progress.emit("이메일: 연동된 계정 없음")
            return
        try:
            # 확인과 동시에 받은편지함 전체를 미리 불러와, 이메일 화면 진입 시
            # 로딩 없이 바로 표시되도록 한다.
            items = fetch_inbox(
                self._account.address,
                account_password(self._account),
            )
            self.inbox_ready.emit(items)
            self.progress.emit(
                f"이메일({self._account.address}): 받은편지 {len(items)}통 확인"
            )
        except Exception as e:  # noqa: BLE001
            self.progress.emit(f"이메일 확인 실패: {str(e)[:120]}")

    def _check_emulator(self) -> None:
        try:
            ok, detail = is_emulator_available()
            self.progress.emit(
                f"Android 에뮬레이터: {detail}" if ok else f"Android 에뮬레이터: 실행 불가 — {detail}"
            )
        except Exception as e:  # noqa: BLE001
            self.progress.emit(f"에뮬레이터 확인 실패: {str(e)[:120]}")
