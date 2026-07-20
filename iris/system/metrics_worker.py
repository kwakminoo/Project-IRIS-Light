"""백그라운드 시스템 메트릭 수집."""

from __future__ import annotations

import time

from PyQt6.QtCore import QMutex, QMutexLocker, QThread, pyqtSignal

from iris.system.gpu_provider import read_gpu_utilization
from iris.system.metrics_snapshot import MetricsSnapshot

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore[assignment]


class MetricsWorker(QThread):
    """UI 스레드 밖에서 CPU·메모리·GPU를 주기적으로 수집."""

    snapshot_ready = pyqtSignal(object)  # MetricsSnapshot

    def __init__(
        self,
        *,
        interval_ms: int = 2000,
        slow_interval_ms: int = 5000,
        parent: object | None = None,
    ) -> None:
        super().__init__(parent)
        self._interval_ms = interval_ms
        self._slow_interval_ms = slow_interval_ms
        self._active = True
        self._stopping = False
        self._mutex = QMutex()
        self._cpu_warm = False

    def request_stop(self) -> None:
        self._stopping = True

    def set_active(self, active: bool) -> None:
        with QMutexLocker(self._mutex):
            self._active = active

    def run(self) -> None:
        while not self._stopping:
            with QMutexLocker(self._mutex):
                active = self._active
            if not active:
                time.sleep(self._slow_interval_ms / 1000.0)
                continue
            snap = self._collect()
            self.snapshot_ready.emit(snap)
            time.sleep(self._interval_ms / 1000.0)

    def _collect(self) -> MetricsSnapshot:
        cpu = 0.0
        mem = 0.0
        if psutil is not None:
            # 첫 호출은 interval=None으로 워밍업
            if not self._cpu_warm:
                psutil.cpu_percent(interval=None)
                self._cpu_warm = True
            cpu = float(psutil.cpu_percent(interval=None))
            mem = float(psutil.virtual_memory().percent)
        gpu, label = read_gpu_utilization()
        return MetricsSnapshot(
            cpu_percent=max(0.0, min(100.0, cpu)),
            memory_percent=max(0.0, min(100.0, mem)),
            gpu_percent=gpu,
            gpu_label=label,
        )
