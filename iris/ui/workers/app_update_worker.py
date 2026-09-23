"""앱 업데이트 백그라운드 워커."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal


class AppUpdateCheckWorker(QThread):
    """원격 리비전 확인 — UI 스레드 금지."""

    finished_ok = pyqtSignal(object)  # UpdateStatus
    failed = pyqtSignal(str)

    def __init__(self, root: str = "", parent=None) -> None:
        super().__init__(parent)
        self._root = (root or "").strip()

    def run(self) -> None:
        try:
            from iris.system.app_update import check_for_update

            root = Path(self._root) if self._root else None
            self.finished_ok.emit(check_for_update(root=root))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc)[:240])


class AppUpdateApplyWorker(QThread):
    """Update 클릭 — git/zip 적용."""

    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, remote_sha: str = "", root: str = "", parent=None) -> None:
        super().__init__(parent)
        self._remote_sha = (remote_sha or "").strip()
        self._root = (root or "").strip()

    def run(self) -> None:
        try:
            from iris.system.app_update import apply_update

            root = Path(self._root) if self._root else None
            msg = apply_update(root=root, remote_sha=self._remote_sha)
            self.finished_ok.emit(msg)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc)[:240])


if __name__ == "__main__":
    from PyQt6.QtCore import QCoreApplication

    from iris.system.app_update import UpdateStatus

    app = QCoreApplication([])
    got: list[object] = []
    w = AppUpdateCheckWorker()
    # 네트워크 없이 시그니처만
    assert hasattr(w, "finished_ok")
    st = UpdateStatus(available=False, detail="x")
    assert not st.available
    print("app_update_worker ok")
