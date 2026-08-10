"""고정된 창을 주기적으로 캡처해 모델로 분석하고 상태 변화를 보고하는 서비스.

- 분석은 데몬 스레드에서 순차 수행 (로컬 GPU에 동시 3장을 던지지 않는다)
- 상태가 '바뀌었을 때만' 보고 — 같은 상태를 반복 알림하지 않는다
- 스크린샷은 메모리에서 모델로만 전달, 디스크 저장 없음
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import TYPE_CHECKING, Callable, Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from iris.core.activity_sink import push_activity_line
from iris.monitoring.models import StatusCategory
from iris.monitoring.pin_store import PinStore
from iris.monitoring.screen_capture import (
    capture_result_to_png_bytes,
    capture_window_by_hwnd,
)
from iris.monitoring.state_detector import detect_window_state

if TYPE_CHECKING:
    from iris.config.settings import Settings

_ANALYZE_INTERVAL_MS = 30_000  # 30초 — 모델 호출이라 썸네일 갱신(4초)보다 느리게
_CAPTURE_TIMEOUT_SEC = 3.0
_ANALYZE_TIMEOUT_SEC = 90.0
_ANALYZE_MAX_WIDTH = 1024  # 비전 토큰·지연을 줄이려 축소해서 보낸다

# 사용자에게 알릴 가치가 있는 상태 (NORMAL·UNKNOWN은 알림 대상 아님)
_ALERT_CATEGORIES = {
    StatusCategory.APPROVAL_WAITING,
    StatusCategory.ERROR_DETECTED,
    StatusCategory.GENERATION_FAILED,
    StatusCategory.TASK_STALLED,
    StatusCategory.RESPONSE_READY,
    StatusCategory.USER_ACTION_REQUIRED,
}

_KOREAN_LABEL = {
    StatusCategory.NORMAL: "정상 진행",
    StatusCategory.APPROVAL_WAITING: "승인 대기",
    StatusCategory.ERROR_DETECTED: "에러 발생",
    StatusCategory.GENERATION_FAILED: "생성 실패",
    StatusCategory.TASK_STALLED: "작업 멈춤",
    StatusCategory.RESPONSE_READY: "응답 준비됨",
    StatusCategory.BUILD_NOT_STARTED: "시작 전",
    StatusCategory.USER_ACTION_REQUIRED: "조작 필요",
    StatusCategory.UNKNOWN: "판단 불가",
}


def status_label(status: StatusCategory) -> str:
    return _KOREAN_LABEL.get(status, status.value)


class PinnedMonitorService(QObject):
    """고정 창 감시 루프. UI는 updated 시그널로 다시 그리고, report로 알림을 띄운다."""

    updated = pyqtSignal()
    # (창 제목, category 값, 요약 한 줄, 상세)
    report = pyqtSignal(str, str, str, str)

    def __init__(
        self,
        store: PinStore,
        settings: "Settings",
        model_provider: Callable[[], str],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._settings = settings
        self._model_provider = model_provider
        self._busy = False
        self._shutdown = False

        self._timer = QTimer(self)
        self._timer.setInterval(_ANALYZE_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    @property
    def store(self) -> PinStore:
        return self._store

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._shutdown = True
        self._timer.stop()

    def analyze_soon(self) -> None:
        """고정 직후처럼 결과를 바로 보고 싶을 때 — 1초 뒤 1회."""
        QTimer.singleShot(1_000, self._tick)

    # ------------------------------------------------------------------
    # loop
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        if self._shutdown or self._busy:
            return
        pins = self._store.list_pins()
        if not pins:
            return
        model = (self._model_provider() or "").strip()
        if not model:
            return  # 모델 미선택 — 조용히 건너뛴다 (다음 주기에 재시도)

        self._busy = True
        threading.Thread(
            target=self._analyze_all,
            args=(model,),
            daemon=True,
            name="iris-pinned-monitor",
        ).start()

    def _analyze_all(self, model: str) -> None:
        try:
            from iris.automation.window_controller import list_visible_windows
            from iris.infrastructure.ollama_client import OllamaClient

            try:
                windows = list_visible_windows()
            except Exception:
                windows = []
            by_title = {w.title.strip().lower(): w for w in windows}

            client = OllamaClient(self._settings.ollama_base_url)

            for pin in self._store.list_pins():
                if self._shutdown:
                    return
                self._analyze_one(client, model, pin.title, by_title)
        finally:
            self._busy = False

    def _analyze_one(self, client, model: str, title: str, by_title: dict) -> None:
        win = by_title.get(title.strip().lower())
        now = datetime.now().strftime("%H:%M:%S")

        if win is None:
            self._store.update_result(
                title,
                StatusCategory.UNKNOWN,
                0.0,
                "창을 찾을 수 없습니다 (닫혔거나 제목이 바뀜).",
                "",
                now,
            )
            self._emit_updated()
            return

        self._store.set_hwnd(title, win.hwnd)

        if win.minimized:
            # 최소화 창은 PrintWindow가 빈 화면을 주기 쉬워 모델을 부르지 않는다
            self._store.update_result(
                title, StatusCategory.UNKNOWN, 0.0, "창이 최소화되어 분석할 수 없습니다.", "", now
            )
            self._emit_updated()
            return

        self._store.set_analyzing(title, True)
        self._emit_updated()

        cap = capture_window_by_hwnd(win.hwnd, timeout_sec=_CAPTURE_TIMEOUT_SEC)
        png = (
            capture_result_to_png_bytes(cap, max_width=_ANALYZE_MAX_WIDTH)
            if cap
            else None
        )
        if not png:
            self._store.update_result(
                title, StatusCategory.UNKNOWN, 0.0, "화면 캡처에 실패했습니다.", "", now
            )
            self._emit_updated()
            return

        result = detect_window_state(
            client, model, title, png, timeout_sec=_ANALYZE_TIMEOUT_SEC
        )
        previous = self._store.update_result(
            title,
            result.category,
            result.confidence,
            result.reason,
            result.recommended_action,
            datetime.now().strftime("%H:%M:%S"),
        )
        self._emit_updated()

        push_activity_line(
            f"모니터 [{title[:30]}] {status_label(result.category)}"
            f" ({result.confidence:.0%})"
        )

        # 상태가 '바뀌어서' 주의가 필요해진 순간에만 알린다
        if result.category in _ALERT_CATEGORIES and previous != result.category:
            detail = result.reason
            if result.recommended_action:
                detail = f"{detail}\n권장: {result.recommended_action}" if detail else result.recommended_action
            try:
                self.report.emit(
                    title, result.category.value, status_label(result.category), detail
                )
            except RuntimeError:
                pass  # 창이 닫히는 중

    def _emit_updated(self) -> None:
        try:
            self.updated.emit()
        except RuntimeError:
            pass
