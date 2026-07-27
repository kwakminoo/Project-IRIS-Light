"""백그라운드 API 할당량 수집."""

from __future__ import annotations

import time

from PyQt6.QtCore import QMutex, QMutexLocker, QThread, pyqtSignal

from iris.infrastructure.api_quota import ApiQuota, fetch_api_quotas


class ApiQuotaWorker(QThread):
    """SerpApi·Firecrawl 월 할당량을 주기적으로 조회."""

    quotas_ready = pyqtSignal(object)  # list[ApiQuota]

    def __init__(
        self,
        *,
        interval_ms: int = 60_000,
        slow_interval_ms: int = 120_000,
        parent: object | None = None,
    ) -> None:
        super().__init__(parent)
        self._interval_ms = interval_ms
        self._slow_interval_ms = slow_interval_ms
        self._active = True
        self._stopping = False
        self._mutex = QMutex()

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
            try:
                quotas: list[ApiQuota] = fetch_api_quotas()
            except Exception:
                quotas = []
            self.quotas_ready.emit(quotas)
            time.sleep(self._interval_ms / 1000.0)
