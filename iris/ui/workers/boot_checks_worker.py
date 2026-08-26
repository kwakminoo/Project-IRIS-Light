"""기동 자가진단 — 에뮬레이터 준비 · Iris Wiki · 연동 이메일을 순차 확인.

에뮬레이터 알림이 이메일/위키 IO에 막히지 않도록 **에뮬을 먼저** 한다.
이메일 IMAP은 타임아웃으로 감싸 워커가 영원히 멈추지 않게 한다.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout

from PyQt6.QtCore import QThread, pyqtSignal

from iris.infrastructure.email_client import fetch_inbox
from iris.knowledge.iris_wiki import IrisWiki
from iris.storage.email_accounts import EmailAccount, account_password
from iris.system.android_emulator import prepare_emulator

# IMAP 무제한 대기로 에뮬 알림이 안 뜨던 회귀 방지
_EMAIL_CHECK_TIMEOUT_S = 25.0


class BootChecksWorker(QThread):
    """런타임 부팅과 함께 실행되는 순차 점검(에뮬 우선)."""

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
        # 알림이 가장 먼저 떠야 하는 항목을 앞에 둔다.
        self._check_emulator()
        self._check_wiki()
        self._check_email()
        self.finished_ok.emit()

    def _check_emulator(self) -> None:
        try:
            ok, detail = prepare_emulator()
            if ok:
                self.progress.emit(f"Android 에뮬레이터: {detail}")
            else:
                self.progress.emit(f"Android 에뮬레이터: 실행 불가 — {detail}")
        except Exception as e:  # noqa: BLE001 - 점검은 실패해도 계속 진행
            self.progress.emit(f"에뮬레이터 확인 실패: {str(e)[:120]}")

    def _check_wiki(self) -> None:
        try:
            from iris.ui.chat.skill_mcp_dialogs import hermes_root, list_hermes_mcps, list_hermes_skills

            root = str(hermes_root())
            skills = [(n, d) for n, d, _p in list_hermes_skills(limit=120)]
            mcps = list_hermes_mcps(limit=40)
            self._wiki.sync_skills_catalog(skills, hermes_root=root)
            self._wiki.sync_mcp_catalog(mcps, hermes_root=root)
            count = len(self._wiki.list_notes())
            self.progress.emit(
                f"Iris Wiki: 노트 {count}개 · 스킬 {len(skills)} · MCP {len(mcps)} 동기화"
            )
        except Exception as e:  # noqa: BLE001 - 점검은 실패해도 계속 진행
            self.progress.emit(f"Iris Wiki 확인 실패: {str(e)[:120]}")

    def _check_email(self) -> None:
        if self._account is None:
            self.progress.emit("이메일: 연동된 계정 없음")
            return
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(
                    fetch_inbox,
                    self._account.address,
                    account_password(self._account),
                )
                items = fut.result(timeout=_EMAIL_CHECK_TIMEOUT_S)
            self.inbox_ready.emit(items)
            self.progress.emit(
                f"이메일({self._account.address}): 받은편지 {len(items)}통 확인"
            )
        except FuturesTimeout:
            self.progress.emit(
                f"이메일 확인 실패: {_EMAIL_CHECK_TIMEOUT_S:.0f}초 초과 (IMAP 응답 없음)"
            )
        except Exception as e:  # noqa: BLE001
            self.progress.emit(f"이메일 확인 실패: {str(e)[:120]}")


class EmulatorLaunchWorker(QThread):
    """모바일 아이콘 — 기동/재시작을 UI 스레드 밖에서 수행."""

    finished_ok = pyqtSignal(str)
    finished_err = pyqtSignal(str)

    def run(self) -> None:
        from iris.system.android_emulator import (
            is_emulator_headless,
            is_emulator_running,
            launch_emulator,
            restart_emulator_windowed,
        )

        try:
            if is_emulator_running():
                if is_emulator_headless():
                    proc = restart_emulator_windowed()
                    self.finished_ok.emit(
                        f"Android 에뮬레이터 재시작 (PID {proc.pid}) — android-emulator/data"
                    )
                else:
                    self.finished_ok.emit("Android 에뮬레이터가 이미 실행 중입니다.")
                return
            proc = launch_emulator()
            self.finished_ok.emit(
                f"Android 에뮬레이터 시작 (PID {proc.pid}) — 부팅 후 adb 연결"
            )
        except OSError as exc:
            self.finished_err.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.finished_err.emit(str(exc))
