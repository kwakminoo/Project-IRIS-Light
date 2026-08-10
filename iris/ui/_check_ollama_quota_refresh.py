"""Ollama 할당량 즉시 갱신·표시 자검 (단계별)."""

from __future__ import annotations

import json
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from iris.infrastructure.api_quota import ApiQuota, format_quota_pair
from iris.infrastructure.ollama_usage import fetch_ollama_quotas, write_usage_cache
from iris.system.api_quota_worker import ApiQuotaWorker
from iris.ui.monitor.system_metrics_panel import SystemMetricsPanel
from iris.ui.window.main_window import MainWindow


def _assert_format() -> None:
    assert format_quota_pair(12, 100) == "12%"
    assert format_quota_pair(0.2, 100) == "0.2%"
    assert "남" not in format_quota_pair(33, 100)
    print("[ok] format used percent")


def _assert_cloud_detect() -> None:
    assert MainWindow._is_cloud_model("gemma4:31b-cloud")
    assert MainWindow._is_cloud_model("minimax-m3:cloud")
    assert not MainWindow._is_cloud_model("llama3.2:latest")
    print("[ok] cloud detect")


def _assert_stale_cache_fallback() -> None:
    path = write_usage_cache(session_pct=7.7, weekly_pct=11.1)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["updated_at"] = time.time() - (10 * 24 * 3600)
    path.write_text(json.dumps(data), encoding="utf-8")
    qs = fetch_ollama_quotas()
    assert any(q.key == "sess" and abs(float(q.used) - 7.7) < 0.01 for q in qs), qs
    print("[ok] stale cache fallback", [(q.key, q.used) for q in qs])


def _assert_worker_immediate(app: QCoreApplication) -> None:
    calls: list[int] = []
    got: list[object] = []

    import iris.infrastructure.ollama_usage as ou

    def fake_fetch() -> list[ApiQuota]:
        calls.append(1)
        return [
            ApiQuota(key="sess", label="SESS", used=3.5, total=100),
            ApiQuota(key="week", label="WEEK", used=10.0, total=100),
        ]

    orig = ou.fetch_ollama_quotas
    ou.fetch_ollama_quotas = fake_fetch  # type: ignore[assignment]
    try:
        worker = ApiQuotaWorker(interval_ms=60_000, parent=None)
        worker.quotas_ready.connect(lambda q: got.append(q))
        worker.start()
        worker.request_refresh_ollama_now()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not got:
            app.processEvents()
            time.sleep(0.05)
        worker.request_stop()
        worker.wait(2000)
    finally:
        ou.fetch_ollama_quotas = orig  # type: ignore[assignment]

    assert calls, "fetch_ollama_quotas was not called"
    assert got and isinstance(got[0], list) and len(got[0]) == 2
    print("[ok] worker immediate refresh calls=", len(calls))


def _assert_cloud_polling_flag() -> None:
    from PyQt6.QtCore import QMutexLocker

    worker = ApiQuotaWorker(interval_ms=60_000)
    worker.set_cloud_polling(True)
    with QMutexLocker(worker._mutex):
        assert worker._prefer_cloud_interval is True
    worker.set_cloud_polling(False)
    with QMutexLocker(worker._mutex):
        assert worker._prefer_cloud_interval is False
    print("[ok] cloud polling flag")


def _assert_manual_click(app: QApplication) -> None:
    panel = SystemMetricsPanel()
    hits: list[int] = []
    panel.ollama_refresh_requested.connect(lambda: hits.append(1))
    panel.apply_quotas(
        [
            ApiQuota(key="sess", label="SESS", used=1.0, total=100),
            ApiQuota(key="week", label="WEEK", used=2.0, total=100),
        ]
    )
    panel.show()
    app.processEvents()
    row = panel._api_rows["sess"]
    assert not row.isHidden()
    ev = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        row.rect().center().toPointF(),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    row.mouseReleaseEvent(ev)
    app.processEvents()
    assert hits == [1], hits
    print("[ok] manual SESS click refresh")


def main() -> int:
    _assert_format()
    _assert_cloud_detect()
    _assert_stale_cache_fallback()
    app = QApplication.instance() or QApplication(sys.argv)
    _assert_worker_immediate(app)
    _assert_cloud_polling_flag()
    _assert_manual_click(app)
    print("ollama_quota_refresh all-steps ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
