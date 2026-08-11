"""업무 학습 background workers — UI 스레드에서 VLM 금지."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from iris.learning.manager import LearningManager


class LearningProcessWorker(QThread):
    finished_ok = pyqtSignal(object)  # dict
    failed = pyqtSignal(str)

    def __init__(self, manager: LearningManager, parent=None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            if self._cancel:
                self.failed.emit("cancelled")
                return
            result = self._manager.finalize_and_process_payload()
            if self._cancel:
                self.failed.emit("cancelled")
                return
            self.finished_ok.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc)[:400])


class WorkflowExecuteWorker(QThread):
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        manager: LearningManager,
        *,
        workflow_id: int | None = None,
        trace_id: str = "",
        task: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._manager = manager
        self._workflow_id = workflow_id
        self._trace_id = trace_id
        self._task = task

    def run(self) -> None:
        try:
            if self._workflow_id is not None:
                run = self._manager.run_learned_workflow(self._workflow_id, self._task)
            else:
                run = self._manager.execute_workflow(self._trace_id, self._task)
            self.finished_ok.emit(run)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc)[:400])
