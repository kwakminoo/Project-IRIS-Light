"""시작 프로토콜 QThread — UI 스레드에서 설치/기동 금지."""

from __future__ import annotations

import threading

from PyQt6.QtCore import QThread, pyqtSignal

from iris.system.setup_protocol import (
    OPTIONAL_IDS,
    SetupProtocol,
    SetupStepResult,
    redact_secrets,
)


class SetupProtocolWorker(QThread):
    """Core(+Optional) 오케스트레이션.

    needs_user 시 시그널 후 resume_user() 대기.
    """

    step_changed = pyqtSignal(object)  # SetupStepResult
    needs_user = pyqtSignal(object)  # SetupStepResult
    log_line = pyqtSignal(str)
    install_chunk = pyqtSignal(str, object, bool)  # text, percent|None, replace
    finished_ok = pyqtSignal(bool)
    failed = pyqtSignal(str)
    phase_changed = pyqtSignal(str)  # "core" | "optional" | "done"
    # Optional k / N (1-based index, total, step_id)
    optional_progress = pyqtSignal(int, int, str)

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

    def is_install_running(self) -> bool:
        return self._protocol.is_busy()

    def request_abort(self) -> None:
        """중단 — protocol.abort()가 자식 프로세스 트리를 kill한다."""
        self._abort = True
        self._protocol.abort()
        self.resume_user("abort")

    def _emit_log(self, text: str) -> None:
        """log_line / failed 단일 관문 — redact_secrets 강제."""
        self.log_line.emit(redact_secrets(text or ""))

    def _on_stream(self, text: str, percent: int | None, replace: bool) -> None:
        safe = redact_secrets(text) if text else text
        self.install_chunk.emit(safe, percent, replace)

    def _on_progress(self, result: SetupStepResult) -> None:
        self.step_changed.emit(result)
        msg = (result.message or "").strip()
        if msg and result.status != "needs_user":
            self._emit_log(f"[{result.label}] {msg}")

    def _on_user(self, result: SetupStepResult) -> str:
        self._user_gate.clear()
        self.needs_user.emit(result)
        self._user_gate.wait()
        if self._abort:
            return "abort"
        return self._user_choice

    def run(self) -> None:
        self._protocol.bind_stream(self._on_stream)
        try:
            self.phase_changed.emit("core")
            self._emit_log("Core 설치를 시작합니다…")
            ok = self._protocol.run_core(
                on_progress=self._on_progress,
                on_user=self._on_user,
            )
            if not ok:
                err = (self._protocol.last_error() or "Core 실패")[:240]
                self.failed.emit(redact_secrets(err))
                self.finished_ok.emit(False)
                return

            if self._run_optional and not self._abort:
                self.phase_changed.emit("optional")
                self._emit_log("추가 기능(선택)…")
                total = len(self._optional_ids)
                for idx, oid in enumerate(self._optional_ids, start=1):
                    if self._abort:
                        break
                    self.optional_progress.emit(idx, total, oid)
                    self._protocol.run_optional(
                        oid,
                        on_progress=self._on_progress,
                        on_user=self._on_user,
                    )

            self.phase_changed.emit("done")
            self._emit_log("시작 프로토콜 완료 — Core Ready")
            self.finished_ok.emit(True)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(redact_secrets(str(exc)[:240]))
            self.finished_ok.emit(False)
        finally:
            self._protocol.bind_stream(None)
