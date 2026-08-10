"""백그라운드 API 할당량 수집."""

from __future__ import annotations

import time

from PyQt6.QtCore import QMutex, QMutexLocker, QThread, pyqtSignal

from iris.infrastructure.api_quota import ApiQuota, fetch_api_quotas


class ApiQuotaWorker(QThread):
    """SerpApi·Firecrawl·Ollama 할당량을 주기적으로 조회. Ollama만 즉시 갱신 가능."""

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
        self._cloud_interval_ms = 20_000  # 클라우드 모델 사용 중 짧은 폴링
        self._active = True
        self._stopping = False
        self._prefer_cloud_interval = False
        self._pending_ollama = False
        self._mutex = QMutex()

    def request_stop(self) -> None:
        self._stopping = True

    def set_active(self, active: bool) -> None:
        with QMutexLocker(self._mutex):
            self._active = active

    def set_cloud_polling(self, enabled: bool) -> None:
        """클라우드 모델 선택 시 폴링 간격을 짧게."""
        with QMutexLocker(self._mutex):
            self._prefer_cloud_interval = bool(enabled)

    def request_refresh_ollama_now(self) -> None:
        """다음 대기 루프에서 Ollama SESS/WEEK만 즉시 조회."""
        with QMutexLocker(self._mutex):
            self._pending_ollama = True

    def _sleep_interruptible(self, total_ms: int) -> None:
        """pending_ollama / stop 시 빨리 깨어남."""
        slept = 0
        chunk = 250
        while slept < total_ms and not self._stopping:
            with QMutexLocker(self._mutex):
                if self._pending_ollama:
                    return
            time.sleep(chunk / 1000.0)
            slept += chunk

    def run(self) -> None:
        while not self._stopping:
            with QMutexLocker(self._mutex):
                active = self._active
                pending = self._pending_ollama
                self._pending_ollama = False
                prefer_cloud = self._prefer_cloud_interval
                interval = (
                    self._cloud_interval_ms if prefer_cloud else self._interval_ms
                )

            if not active:
                self._sleep_interruptible(self._slow_interval_ms)
                continue

            if pending:
                try:
                    from iris.infrastructure.ollama_usage import fetch_ollama_quotas

                    quotas: list[ApiQuota] = fetch_ollama_quotas()
                except Exception:
                    quotas = []
                self.quotas_ready.emit(quotas)
                self._sleep_interruptible(interval)
                continue

            try:
                quotas = fetch_api_quotas()
            except Exception:
                quotas = []
            self.quotas_ready.emit(quotas)
            self._sleep_interruptible(interval)
