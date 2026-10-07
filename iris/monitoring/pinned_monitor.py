"""고정된 창을 주기적으로 캡처해 모델로 분석하고 상태 변화를 보고하는 서비스.

- 분석은 데몬 스레드에서 순차 수행 (로컬 GPU에 동시 3장을 던지지 않는다)
- 상태가 '바뀌었을 때만' 보고 — 같은 상태를 반복 알림하지 않는다
- 스크린샷은 메모리에서 모델로만 전달, 디스크 저장 없음
- 화면 분석은 vision 능력이 확인된 모델로만 한다 (local_vision). 채팅 모델이
  이미지를 못 보면 창 제목만 보고 답해서 늘 '판단 불가'가 나왔다.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING, Callable, Optional, Sequence

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from iris.core.activity_sink import push_activity_line
from iris.monitoring.models import StatusCategory
from iris.monitoring.pin_store import PinnedTarget, PinStore, _app_suffix
from iris.monitoring.screen_capture import (
    CaptureResult,
    capture_result_to_png_bytes,
    capture_window_by_hwnd,
)
from iris.monitoring.state_detector import detect_window_state

if TYPE_CHECKING:
    from iris.automation.window_controller import WindowInfo
    from iris.config.settings import Settings

log = logging.getLogger("iris.monitoring.pinned")

# 1초마다 창을 캡처해(0.1초) 화면이 바뀌었을 때만 모델을 부른다 — 모델 한 번이 2~3초
# (qwen2.5vl:3b, 6GB GPU 실측)라 매초 분석은 못 하고, 안 바뀐 화면을 다시 볼 필요도 없다
_WATCH_INTERVAL_MS = 1_000
_HEARTBEAT_MS = 60_000  # 바뀐 게 없어도 가끔은 다시 본다 (캡처가 실패해 변화를 놓쳤을 때)
_MIN_ANALYZE_GAP_SEC = 3.0  # 계속 바뀌는 창(영상·스크롤)이 GPU 를 독차지하지 않게
_SIG_WIDTH = 160  # 비교용 축소 폭
_PIXEL_DELTA = 24  # 이만큼 밝기가 달라진 점을 '바뀐 점'으로
_CHANGED_FRACTION = 0.004  # 바뀐 점이 이 비율을 넘으면 화면이 바뀐 것 (커서 깜빡임은 안 넘는다)
_CAPTURE_TIMEOUT_SEC = 3.0
# 앱을 켠 직후엔 IRIS 가 Ollama 를 띄우는 중이라 첫 분석이 연결 실패로 끝난다 —
# 그동안은 heartbeat(60초) 대신 짧게 다시 시도한다
_STARTUP_RETRY_MS = 10_000
_STARTUP_WINDOW_SEC = 120.0
_ANALYZE_TIMEOUT_SEC = 180.0  # 첫 호출은 모델을 GPU에 올리느라 80초 넘게 걸린다 (qwen2.5vl:3b 실측)
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


def screen_signature(cap: CaptureResult):
    """화면 비교용 작은 흑백 그림."""
    import numpy as np

    img = np.frombuffer(cap.rgb_bytes, dtype=np.uint8).reshape(cap.height, cap.width, 3)
    step = max(1, cap.width // _SIG_WIDTH)
    return img[::step, ::step].mean(axis=2).astype(np.int16)


def screen_changed(before, after) -> bool:
    if before is None or after is None or before.shape != after.shape:
        return True
    import numpy as np

    moved = np.count_nonzero(np.abs(after - before) > _PIXEL_DELTA)
    return moved > _CHANGED_FRACTION * before.size


def status_label(status: StatusCategory) -> str:
    return _KOREAN_LABEL.get(status, status.value)


def locate_window(
    pin: PinnedTarget, windows: Sequence["WindowInfo"]
) -> Optional["WindowInfo"]:
    """고정한 창을 지금 창 목록에서 찾는다.

    1) 같은 hwnd — 탭·파일을 바꿔 제목이 달라져도 같은 창이다
    2) 고정할 때 제목 또는 마지막으로 본 제목과 똑같은 창
    3) 같은 앱(제목 끝 ' - Google Chrome' 등)의 창이 딱 하나뿐이면 그 창
    """
    if pin.hwnd:
        for w in windows:
            if w.hwnd == pin.hwnd:
                return w
    wanted = {pin.title.strip().lower()}
    if pin.current_title:
        wanted.add(pin.current_title.strip().lower())
    for w in windows:
        if w.title.strip().lower() in wanted:
            return w
    suffix = _app_suffix(pin.title)
    if suffix:
        same_app = [w for w in windows if _app_suffix(w.title) == suffix]
        if len(same_app) == 1:
            return same_app[0]
    return None


class PinnedMonitorService(QObject):
    """고정 창 감시 루프. UI는 updated 시그널로 다시 그리고, report로 알림을 띄운다."""

    updated = pyqtSignal()
    # (창 제목, category 값, 요약 한 줄, 상세)
    report = pyqtSignal(str, str, str, str)
    # 화면을 볼 수 있는 모델이 없음 (사유) — 설치를 권할 때, 세션당 한 번
    vision_missing = pyqtSignal(str)
    # 분석이 끝났는데 고정할 때 들어온 요청이 남아 있음 — 메인 스레드에서 다시 돈다
    _rerun_requested = pyqtSignal()
    # Ollama 가 아직 안 떠서 실패 — 메인 스레드에서 잠시 뒤 다시 돈다
    _retry_requested = pyqtSignal()
    # 1초 감시에서 화면이 바뀐 창 (고정 제목 목록) — 메인 스레드에서 분석을 띄운다
    _changed = pyqtSignal(list)

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
        self._rerun = False
        self._vision_prompted = False
        self._watching = False
        # 고정 제목 → 마지막으로 모델이 본 화면, 그때 시각
        self._sigs: dict[str, object] = {}
        self._analyzed_at: dict[str, float] = {}

        self._timer = QTimer(self)
        self._timer.setInterval(_HEARTBEAT_MS)
        self._timer.timeout.connect(self._tick)
        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(_WATCH_INTERVAL_MS)
        self._watch_timer.timeout.connect(self._watch_tick)
        self._rerun_requested.connect(self.analyze_soon)
        self._retry_requested.connect(
            lambda: QTimer.singleShot(_STARTUP_RETRY_MS, self._tick)
        )
        self._started_at = 0.0
        self._changed.connect(self._on_changed)

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    @property
    def store(self) -> PinStore:
        return self._store

    def start(self) -> None:
        self._started_at = time.monotonic()
        if not self._timer.isActive():
            self._timer.start()
        if not self._watch_timer.isActive():
            self._watch_timer.start()
        # 지난번에 고정해 둔 창 — heartbeat(60초)까지 기다리지 않고 바로 본다.
        # 1초 감시도 첫 분석이 남긴 화면이 있어야 돌기 시작한다.
        if self._store.list_pins():
            self.analyze_soon()

    def stop(self) -> None:
        self._shutdown = True
        self._timer.stop()
        self._watch_timer.stop()

    def analyze_soon(self) -> None:
        """고정 직후처럼 결과를 바로 보고 싶을 때 — 1초 뒤 1회.

        이미 분석 중이면 끝난 직후 한 번 더 돈다 (요청을 버리지 않는다)."""
        if self._busy:
            self._rerun = True
            return
        QTimer.singleShot(1_000, self._tick)

    def allow_vision_prompt_again(self) -> None:
        """모델을 설치했거나, 나중에 다시 물어도 될 때."""
        self._vision_prompted = False

    def status_lines(self) -> list[str]:
        """채팅·도구가 쓰는 고정 창 현황 — 한 줄에 창 하나."""
        lines: list[str] = []
        for pin in self._store.list_pins():
            name = pin.current_title or pin.title
            if pin.analyzing:
                lines.append(f"- {name}: 분석 중")
                continue
            if not pin.last_checked_at:
                lines.append(f"- {name}: 아직 분석 전")
                continue
            parts = [f"{status_label(pin.status)} ({pin.last_checked_at} 확인)"]
            if pin.summary:
                parts.append(f"화면: {pin.summary}")
            if pin.reason:
                parts.append(f"근거: {pin.reason}")
            if pin.recommended_action:
                parts.append(f"권장: {pin.recommended_action}")
            lines.append(f"- {name}: " + " / ".join(parts))
        return lines

    # ------------------------------------------------------------------
    # loop
    # ------------------------------------------------------------------

    def _tick(self, titles: Optional[list[str]] = None) -> None:
        if self._shutdown or self._busy:
            return
        if not self._store.list_pins():
            return
        chat_model = (self._model_provider() or "").strip()

        self._busy = True
        threading.Thread(
            target=self._analyze_all,
            args=(chat_model, titles),
            daemon=True,
            name="iris-pinned-monitor",
        ).start()

    def _watch_tick(self) -> None:
        if self._shutdown or self._busy or self._watching:
            return
        pins = [p for p in self._store.list_pins() if p.hwnd and p.title in self._sigs]
        if not pins:
            return
        self._watching = True
        threading.Thread(
            target=self._watch, args=(pins,), daemon=True, name="iris-pinned-watch"
        ).start()

    def _watch(self, pins: list[PinnedTarget]) -> None:
        """모델이 마지막으로 본 화면과 지금 화면을 비교만 한다."""
        import ctypes

        changed: list[str] = []
        try:
            now = time.monotonic()
            for pin in pins:
                if now - self._analyzed_at.get(pin.title, 0.0) < _MIN_ANALYZE_GAP_SEC:
                    continue
                if ctypes.windll.user32.IsIconic(pin.hwnd):
                    continue
                cap = capture_window_by_hwnd(pin.hwnd, timeout_sec=_CAPTURE_TIMEOUT_SEC)
                if cap is None:
                    continue
                if screen_changed(self._sigs.get(pin.title), screen_signature(cap)):
                    changed.append(pin.title)
        except Exception:
            log.exception("고정 창 변화 감시 실패")
        finally:
            self._watching = False
        if changed and not self._shutdown:
            try:
                self._changed.emit(changed)
            except RuntimeError:
                pass

    def _on_changed(self, titles: list) -> None:
        log.info("고정 창 화면 바뀜 → 분석: %s", ", ".join(t[:30] for t in titles))
        self._tick(list(titles))

    def _analyze_all(self, chat_model: str, titles: Optional[list[str]] = None) -> None:
        try:
            from iris.automation.window_controller import list_visible_windows
            from iris.infrastructure.local_vision import resolve_vision_model
            from iris.infrastructure.ollama_client import OllamaClient

            client = OllamaClient(self._settings.ollama_base_url)
            model, why = resolve_vision_model(client, chat_model)
            if not model:
                self._mark_all_unavailable(why)
                if "연결" in why and time.monotonic() - self._started_at < _STARTUP_WINDOW_SEC:
                    try:
                        self._retry_requested.emit()
                    except RuntimeError:
                        pass
                return

            try:
                windows = list_visible_windows()
            except Exception:
                log.exception("창 목록을 읽지 못함")
                windows = []

            for pin in self._store.list_pins():
                if self._shutdown:
                    return
                if titles is not None and pin.title not in titles:
                    continue
                try:
                    self._analyze_one(client, model, pin, windows)
                except Exception as e:  # 한 창의 실패가 나머지를 막지 않게
                    log.exception("고정 창 분석 실패: %s", pin.title)
                    self._store.update_result(
                        pin.title,
                        StatusCategory.UNKNOWN,
                        0.0,
                        f"분석 중 오류: {e}"[:200],
                        "",
                        datetime.now().strftime("%H:%M:%S"),
                    )
                    self._emit_updated()
        finally:
            self._busy = False
            if self._rerun and not self._shutdown:
                self._rerun = False
                try:
                    self._rerun_requested.emit()
                except RuntimeError:
                    pass

    def _mark_all_unavailable(self, why: str) -> None:
        now = datetime.now().strftime("%H:%M:%S")
        for pin in self._store.list_pins():
            self._store.update_result(pin.title, StatusCategory.UNKNOWN, 0.0, why, "", now)
        self._emit_updated()
        log.warning("고정 창 분석 불가: %s", why)
        if not self._vision_prompted and "설치" in why:
            self._vision_prompted = True
            try:
                self.vision_missing.emit(why)
            except RuntimeError:
                pass

    def _analyze_one(
        self, client, model: str, pin: PinnedTarget, windows: Sequence["WindowInfo"]
    ) -> None:
        title = pin.title
        win = locate_window(pin, windows)
        now = datetime.now().strftime("%H:%M:%S")

        if win is None:
            self._store.update_result(
                title,
                StatusCategory.UNKNOWN,
                0.0,
                "창을 찾을 수 없어요 — 닫혔을 수 있어요.",
                "",
                now,
            )
            self._emit_updated()
            return

        self._store.set_hwnd(title, win.hwnd, win.title)

        if win.minimized:
            # 최소화 창은 PrintWindow가 빈 화면을 주기 쉬워 모델을 부르지 않는다
            self._store.update_result(
                title, StatusCategory.UNKNOWN, 0.0, "창이 최소화되어 분석할 수 없어요.", "", now
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
                title, StatusCategory.UNKNOWN, 0.0, "화면 캡처에 실패했어요.", "", now
            )
            self._emit_updated()
            return
        # 이 화면을 기준으로 1초 감시가 '바뀌었나'를 본다
        try:
            self._sigs[title] = screen_signature(cap)
        except Exception:
            self._sigs.pop(title, None)
        self._analyzed_at[title] = time.monotonic()

        result = detect_window_state(
            client, model, win.title or title, png, timeout_sec=_ANALYZE_TIMEOUT_SEC
        )
        previous = self._store.update_result(
            title,
            result.category,
            result.confidence,
            result.reason,
            result.recommended_action,
            datetime.now().strftime("%H:%M:%S"),
            summary=result.summary,
        )
        self._emit_updated()
        log.info(
            "고정 창 [%s] %s %.2f — %s",
            title[:40],
            result.category.value,
            result.confidence,
            result.reason[:120],
        )

        push_activity_line(
            f"모니터 [{(win.title or title)[:30]}] {status_label(result.category)}"
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
