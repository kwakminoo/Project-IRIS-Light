"""수신 전화 감시 — adb 상태를 폴링해 상태 변화를 시그널로 알린다.

`pinned_monitor` 와 같은 모양이다: 데몬 스레드에서 느린 I/O(adb)를 돌리고,
결과만 Qt 시그널로 메인 스레드에 넘긴다.

폴링 주기가 짧은 이유는 **전화벨이 짧기 때문**이다. 30초에 한 번 보면
전화가 다 끊긴 뒤에 알게 된다. adb `dumpsys` 한 번은 수십 ms라 1초 주기도
부담이 없지만, 통화 중이 아닐 때는 주기를 늘려 배터리/CPU를 아낀다.
"""

from __future__ import annotations

import threading
from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from iris.core.activity_sink import push_activity_line
from iris.system.phone_control import (
    CallSnapshot,
    CallState,
    answer_call,
    end_call,
    read_call_state,
    read_caller_name,
    silence_ringer,
)

# 벨이 울릴 수 있는 평상시 — 전화가 오면 이 주기 안에 알아챈다
_IDLE_POLL_MS = 1_500
# 이미 벨이 울리거나 통화 중이면 상태 전환을 더 촘촘히 본다
_ACTIVE_POLL_MS = 800
# adb 가 아예 없을 때(에뮬레이터 미실행) 계속 두드리지 않도록 물러선다
_BACKOFF_MS = 15_000


class CallMonitorService(QObject):
    """연결된 Android 기기의 통화 상태를 감시한다."""

    # 벨이 울리기 시작함 — (표시용 이름, 번호)
    ringing_started = pyqtSignal(str, str)
    # 통화가 연결됨
    call_answered = pyqtSignal()
    # 벨/통화가 끝남 (받았든 못 받았든)
    call_ended = pyqtSignal()
    # 상태가 바뀔 때마다 — UI 힌트 갱신용
    state_changed = pyqtSignal(str)  # CallState.value

    def __init__(self, parent: QObject | None = None, *, enabled: bool = True) -> None:
        super().__init__(parent)
        self._enabled = bool(enabled)
        self._state = CallState.UNKNOWN
        self._snapshot = CallSnapshot()
        self._polling = False
        self._stopped = False
        self._last_error = ""
        self._timer = QTimer(self)
        self._timer.setInterval(_IDLE_POLL_MS)
        self._timer.timeout.connect(self._poll_soon)

    # ------------------------------------------------------------------
    # 수명 주기
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._stopped or not self._enabled:
            return
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._stopped = True
        self._timer.stop()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        if not self._enabled:
            self._timer.stop()
            if self._state is not CallState.IDLE:
                self._apply(CallSnapshot(state=CallState.IDLE))
        elif not self._stopped:
            self._timer.start()

    # ------------------------------------------------------------------
    # 상태
    # ------------------------------------------------------------------

    @property
    def state(self) -> CallState:
        return self._state

    @property
    def snapshot(self) -> CallSnapshot:
        return self._snapshot

    def is_ringing(self) -> bool:
        return self._state is CallState.RINGING

    def is_in_call(self) -> bool:
        return self._state in (CallState.RINGING, CallState.ACTIVE)

    # ------------------------------------------------------------------
    # 동작 — UI 스레드에서 부른다. adb 한 번이라 수십 ms.
    # ------------------------------------------------------------------

    def answer(self) -> tuple[bool, str]:
        ok, message = answer_call(self._snapshot.serial or None)
        push_activity_line(f"CALL answer ok={ok} {message}")
        if ok:
            self._poll_soon()
        return ok, message

    def reject(self) -> tuple[bool, str]:
        ok, message = end_call(self._snapshot.serial or None)
        push_activity_line(f"CALL end ok={ok} {message}")
        if ok:
            self._poll_soon()
        return ok, message

    def silence(self) -> tuple[bool, str]:
        ok, message = silence_ringer(self._snapshot.serial or None)
        push_activity_line(f"CALL silence ok={ok} {message}")
        return ok, message

    # ------------------------------------------------------------------
    # 폴링
    # ------------------------------------------------------------------

    def _poll_soon(self) -> None:
        """adb 호출은 느릴 수 있으므로 데몬 스레드로 던진다."""
        if self._stopped or self._polling or not self._enabled:
            return
        self._polling = True
        threading.Thread(target=self._poll, daemon=True, name="iris-call-monitor").start()

    def _poll(self) -> None:
        try:
            snapshot = read_call_state()
            # 벨이 막 울리기 시작했을 때만 UI 덤프로 이름을 건진다(느린 호출)
            if snapshot.state is CallState.RINGING and self._state is not CallState.RINGING:
                name = read_caller_name(snapshot.serial or None)
                if name:
                    snapshot = CallSnapshot(
                        state=snapshot.state,
                        number=snapshot.number,
                        caller=name,
                        serial=snapshot.serial,
                    )
        except Exception as exc:  # 폴링이 앱을 죽이면 안 된다
            snapshot = CallSnapshot(state=CallState.UNKNOWN, error=repr(exc))
        finally:
            self._polling = False

        # 시그널은 메인 스레드에서 — QTimer.singleShot(0) 으로 넘긴다
        QTimer.singleShot(0, lambda snap=snapshot: self._apply(snap))

    def _apply(self, snapshot: CallSnapshot) -> None:
        if self._stopped:
            return

        # adb 자체가 안 되는 상황이면 폴링 간격을 늘린다.
        # 에뮬레이터를 안 켠 채로 쓰는 게 기본 상태일 수 있다.
        if snapshot.error:
            if snapshot.error != self._last_error:
                self._last_error = snapshot.error
                push_activity_line(f"CALL adb 사용 불가 — {snapshot.error}")
            self._timer.setInterval(_BACKOFF_MS)
            return
        if self._last_error:
            self._last_error = ""
            push_activity_line("CALL adb 복구 — 전화 감시 재개")

        previous = self._state
        self._snapshot = snapshot
        self._state = snapshot.state
        self._timer.setInterval(
            _ACTIVE_POLL_MS if snapshot.state in (CallState.RINGING, CallState.ACTIVE)
            else _IDLE_POLL_MS
        )

        if snapshot.state is previous:
            return

        self.state_changed.emit(snapshot.state.value)

        if snapshot.state is CallState.RINGING:
            push_activity_line(f"CALL 수신 — {snapshot.display_name}")
            self.ringing_started.emit(snapshot.display_name, snapshot.number)
        elif snapshot.state is CallState.ACTIVE:
            push_activity_line("CALL 통화 연결됨")
            self.call_answered.emit()
        elif snapshot.state is CallState.IDLE and previous in (
            CallState.RINGING,
            CallState.ACTIVE,
        ):
            push_activity_line("CALL 통화 종료")
            self.call_ended.emit()
