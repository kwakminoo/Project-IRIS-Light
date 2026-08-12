"""시작 프로토콜 QThread — UI 스레드에서 설치/기동 금지."""

from __future__ import annotations

import threading

from PyQt6.QtCore import QThread, pyqtSignal

from iris.system.setup_protocol import (
    OPTIONAL_IDS,
    SetupProtocol,
    SetupStepResult,
)


class SetupProtocolWorker(QThread):
    """Core(+Optional) 오케스트레이션.

    needs_user 시 시그널 후 resume_user() 대기.
    """

    step_changed = pyqtSignal(object)  # SetupStepResult
    needs_user = pyqtSignal(object)  # SetupStepResult
    log_line = pyqtSignal(str)
    finished_ok = pyqtSignal(bool)
    failed = pyqtSignal(str)
    phase_changed = pyqtSignal(str)  # "core" | "optional" | "done"

    def __init__(
        self,
        protocol: SetupProtocol,
        *,
        run_optional: bool = True,
        optional_ids: tuple[str, ...] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._protocol = protocol
        self._run_optional = run_optional
        self._optional_ids = optional_ids if optional_ids is not None else OPTIONAL_IDS
        self._user_gate = threading.Event()
        self._user_choice = "done"
        self._abort = False

    def resume_user(self, choice: str = "done") -> None:
        """Wizard: 완료했어요 / 나중에 / 중단."""
        self._user_choice = (choice or "done").strip().lower() or "done"
        self._user_gate.set()

    def request_abort(self) -> None:
        self._abort = True
        self.resume_user("abort")

    def _on_progress(self, result: SetupStepResult) -> None:
        self.step_changed.emit(result)
        msg = (result.message or "").strip()
        if msg and result.status != "needs_user":
            # 시크릿 방지: API_SERVER_KEY / token 패턴 거르지 않고 메시지 자체에 키를 안 넣음
            self.log_line.emit(f"[{result.label}] {msg}")

    def _on_user(self, result: SetupStepResult) -> str:
        self._user_gate.clear()
        self.needs_user.emit(result)
        self._user_gate.wait()
        if self._abort:
            return "abort"
        return self._user_choice

    def run(self) -> None:
        try:
            self.phase_changed.emit("core")
            self.log_line.emit("Core 설치를 시작합니다…")
            ok = self._protocol.run_core(
                on_progress=self._on_progress,
                on_user=self._on_user,
            )
            if not ok:
                err = (self._protocol.last_error() or "Core 실패")[:240]
                self.failed.emit(err)
                self.finished_ok.emit(False)
                return

            if self._run_optional and not self._abort:
                self.phase_changed.emit("optional")
                self.log_line.emit("추가 기능(선택)…")
                for oid in self._optional_ids:
                    if self._abort:
                        break
                    self._protocol.run_optional(
                        oid,
                        on_progress=self._on_progress,
                        on_user=self._on_user,
                    )

            self.phase_changed.emit("done")
            self.log_line.emit("시작 프로토콜 완료 — Core Ready")
            self.finished_ok.emit(True)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc)[:240])
            self.finished_ok.emit(False)
