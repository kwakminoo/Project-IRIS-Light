"""Iris Agent 업데이트 확인·적용 백그라운드 워커."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from iris.infrastructure.iris_agent_client import IrisAgentInferenceTarget


class IrisAgentUpdateCheckWorker(QThread):
    """Compare the active installation with the bundled engine."""

    finished_ok = pyqtSignal(object)  # IrisAgentUpdateStatus
    failed = pyqtSignal(str)

    def run(self) -> None:
        try:
            from iris.system.iris_agent_update import check_iris_agent_update

            self.finished_ok.emit(check_iris_agent_update())
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc)[:240])


class IrisAgentUpdateApplyWorker(QThread):
    """Stage and validate the bundled engine before selecting it."""

    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(
        self,
        *,
        target: IrisAgentInferenceTarget,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._target = target

    def run(self) -> None:
        try:
            from iris.system.iris_agent_update import apply_iris_agent_update

            msg = apply_iris_agent_update(
                target=self._target,
                on_progress=lambda line: self.progress.emit(line),
            )
            self.finished_ok.emit(msg)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc)[:400])


if __name__ == "__main__":
    from PyQt6.QtCore import QCoreApplication

    from iris.system.iris_agent_update import IrisAgentUpdateStatus

    app = QCoreApplication([])
    w = IrisAgentUpdateCheckWorker()
    assert hasattr(w, "finished_ok")
    st = IrisAgentUpdateStatus(available=True, detail="abc → def")
    assert st.available
    print("iris_agent_update_worker ok")
