"""Iris Agent 업데이트 확인·적용 백그라운드 워커."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal


class IrisAgentUpdateCheckWorker(QThread):
    """origin/main 비교 — UI 스레드 금지."""

    finished_ok = pyqtSignal(object)  # IrisAgentUpdateStatus
    failed = pyqtSignal(str)

    def __init__(self, command: str = "iris-agent", parent=None) -> None:
        super().__init__(parent)
        self._command = (command or "iris-agent").strip() or "iris-agent"

    def run(self) -> None:
        try:
            from iris.system.iris_agent_update import check_iris_agent_update

            self.finished_ok.emit(check_iris_agent_update(command=self._command))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc)[:240])


class IrisAgentUpdateApplyWorker(QThread):
    """업데이트 버튼 — pin checkout only (sidecar/home; no :8642 restart)."""

    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(
        self,
        *,
        command: str = "iris-agent",
        base_url: str = "",
        api_key: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._command = (command or "iris-agent").strip() or "iris-agent"
        self._base_url = (base_url or "").strip()
        self._api_key = (api_key or "").strip()

    def run(self) -> None:
        try:
            from iris.system.iris_agent_update import apply_iris_agent_update

            msg = apply_iris_agent_update(
                command=self._command,
                base_url=self._base_url,
                api_key=self._api_key,
                on_progress=lambda line: self.progress.emit(line),
            )
            self.finished_ok.emit(msg)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc)[:400])


if __name__ == "__main__":
    from PyQt6.QtCore import QCoreApplication

    from iris.system.iris_agent_update import IrisAgentUpdateStatus, iris_agent_update_argv

    app = QCoreApplication([])
    w = IrisAgentUpdateCheckWorker()
    assert hasattr(w, "finished_ok")
    assert iris_agent_update_argv("hermes") == ["hermes", "update", "--yes"]
    st = IrisAgentUpdateStatus(available=True, detail="abc → def")
    assert st.available
    assert Path(".").exists()
    print("iris_agent_update_worker ok")
